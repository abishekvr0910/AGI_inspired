"""Unit tests for Egress Policy Manager (Phase 1).

Tests syntax validation, risk heuristics, DNS liveness/SSRF guards, candidate
summarization, propose workflow, approve/reject lifecycle, and CLI commands.
"""
from __future__ import annotations

import json
import os
import socket
import sys
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "orchestrator"))

import policy_manager  # noqa: E402

checks = 0
failures: list[str] = []


def check(label: str, condition: bool) -> None:
    global checks
    checks += 1
    print(f"  [{'PASS' if condition else 'FAIL'}] {label}")
    if not condition:
        failures.append(label)


# ---------------------------------------------------------------------------
# Test 1: Normalization & Syntax Validation
# ---------------------------------------------------------------------------
print("\n[1] Testing Hostname Normalization & Syntax Validation...")
check("normalize strips scheme and path",
      policy_manager.normalize_hostname("https://example.com/path/foo") == "example.com")
check("normalize strips port",
      policy_manager.normalize_hostname("api.example.com:443") == "api.example.com")
check("normalize lowercases",
      policy_manager.normalize_hostname("WWW.EXAMPLE.COM") == "www.example.com")

v_valid = policy_manager.validate_hostname_syntax("sub.example.com")
check("valid hostname passes syntax", v_valid["valid"] is True and v_valid["error"] is None)

v_ip = policy_manager.validate_hostname_syntax("192.168.1.1")
check("IP literal rejected", v_ip["valid"] is False and v_ip["error"] == "ip_address_literal_prohibited")

v_single = policy_manager.validate_hostname_syntax("localhost")
check("single label without TLD rejected", v_single["valid"] is False and "insufficient_labels" in v_single["error"])

v_empty = policy_manager.validate_hostname_syntax("")
check("empty hostname rejected", v_empty["valid"] is False and v_empty["error"] == "empty_hostname")

v_invalid_char = policy_manager.validate_hostname_syntax("bad_name*.com")
check("invalid character rejected", v_invalid_char["valid"] is False and "invalid_characters" in v_invalid_char["error"])

# ---------------------------------------------------------------------------
# Test 2: Risk Heuristics (Dynamic DNS & High Risk TLDs)
# ---------------------------------------------------------------------------
print("\n[2] Testing Static Risk Heuristics...")
v_dyn = policy_manager.validate_hostname_syntax("mytest.duckdns.org")
check("dynamic DNS detected", v_dyn["valid"] is True and any("dynamic_dns" in r for r in v_dyn["risk_flags"]))

v_tld = policy_manager.validate_hostname_syntax("phish.zip")
check("high-risk TLD detected", v_tld["valid"] is True and any("high_risk_tld" in r for r in v_tld["risk_flags"]))

v_depth = policy_manager.validate_hostname_syntax("a.b.c.d.example.com")
check("excessive depth detected", v_depth["valid"] is True and "excessive_subdomain_depth" in v_depth["risk_flags"])

# ---------------------------------------------------------------------------
# Test 3: DNS Resolution & SSRF Bounds
# ---------------------------------------------------------------------------
print("\n[3] Testing DNS Resolution & SSRF Guards...")


def mock_public_resolver(host: str, port: int, **kwargs: Any) -> list[Any]:
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]


def mock_private_resolver(host: str, port: int, **kwargs: Any) -> list[Any]:
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.50", port))]


def mock_loopback_resolver(host: str, port: int, **kwargs: Any) -> list[Any]:
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", port))]


def mock_failing_resolver(host: str, port: int, **kwargs: Any) -> list[Any]:
    raise socket.gaierror(-2, "Name or service not known")


dns_pub = policy_manager.check_dns_liveness("example.com", resolver=mock_public_resolver)
check("public DNS resolvable", dns_pub["resolvable"] is True)
check("public DNS no SSRF risk", dns_pub["ssrf_risk"] is False)
check("public DNS returned IP", "93.184.216.34" in dns_pub["ips"])

dns_priv = policy_manager.check_dns_liveness("internal.local", resolver=mock_private_resolver)
check("private DNS flagged SSRF risk", dns_priv["ssrf_risk"] is True)

dns_loop = policy_manager.check_dns_liveness("local.test", resolver=mock_loopback_resolver)
check("loopback DNS flagged SSRF risk", dns_loop["ssrf_risk"] is True)

dns_fail = policy_manager.check_dns_liveness("nonexistent.test", resolver=mock_failing_resolver)
check("failing DNS resolvable is False", dns_fail["resolvable"] is False)
check("failing DNS returns error string", "gaierror" in dns_fail["error"])

# ---------------------------------------------------------------------------
# Test 4: Candidate Summarization, Propose, Approve, and Reject Lifecycle
# ---------------------------------------------------------------------------
print("\n[4] Testing Lifecycle (Summarize, Propose, Approve, Reject)...")

with tempfile.TemporaryDirectory() as tmpdir:
    t_root = Path(tmpdir)
    policy_file = t_root / "test_policy.yaml"
    candidates_file = t_root / "test_candidates.jsonl"
    approvals_file = t_root / "test_approvals.audit.jsonl"

    initial_policy_content = {
        "schema_version": 1,
        "mode": "broker_required",
        "broker": {
            "host": "127.0.0.1",
            "port": 8787,
            "connect_port": 443,
            "idle_timeout_seconds": 15,
            "max_connection_bytes": 10485760,
            "allowed_hosts": ["alpha.com", "bravo.org"],
        },
        "attestation": {
            "environment_variable": "TEST_ATTEST",
            "purpose": "test",
            "max_age_hours": 24,
            "required_evidence": ["evidence1"],
            "required_claims": ["claim1"],
        },
        "audit_log_environment_variable": "TEST_AUDIT",
    }
    policy_file.write_text(json.dumps(initial_policy_content), encoding="utf-8")

    # Write mock candidates
    raw_entries = [
        {"timestamp": "2026-09-14T01:00:00Z", "task_id": 201, "host": "charlie.net", "url": "https://charlie.net/page1"},
        {"timestamp": "2026-09-14T01:05:00Z", "task_id": 202, "host": "charlie.net", "url": "https://charlie.net/page2"},
        {"timestamp": "2026-09-14T01:10:00Z", "task_id": 203, "host": "delta.io", "url": "https://delta.io/info"},
        {"timestamp": "2026-09-14T01:15:00Z", "task_id": 204, "host": "alpha.com", "url": "https://alpha.com/allowed"},
    ]
    candidates_file.write_text("\n".join(json.dumps(e) for e in raw_entries) + "\n", encoding="utf-8")

    re_sign_called = False

    def mock_re_sign() -> bool:
        global re_sign_called
        re_sign_called = True
        return True

    mgr = policy_manager.PolicyManager(
        policy_path=policy_file,
        candidates_path=candidates_file,
        approvals_path=approvals_file,
        re_sign_runner=mock_re_sign,
    )

    # Summarize all candidates
    all_cand = mgr.summarize_candidates(unreviewed_only=False)
    check("summarize returns 3 distinct hosts", len(all_cand) == 3)
    c_map = {c["host"]: c for c in all_cand}
    check("charlie.net aggregated count is 2", c_map["charlie.net"]["count"] == 2)
    check("charlie.net has 2 task IDs", c_map["charlie.net"]["task_ids"] == [201, 202])
    check("alpha.com flagged already_allowed", c_map["alpha.com"]["already_allowed"] is True)
    check("delta.io not already_allowed", c_map["delta.io"]["already_allowed"] is False)

    # Unreviewed candidates (should exclude alpha.com)
    unreviewed = mgr.summarize_candidates(unreviewed_only=True)
    check("unreviewed candidates count is 2", len(unreviewed) == 2)
    check("alpha.com omitted from unreviewed", "alpha.com" not in [u["host"] for u in unreviewed])

    # Propose
    proposals = mgr.propose(unreviewed_only=True, resolve_dns=True, resolver=mock_public_resolver)
    check("propose returns 2 proposals", len(proposals) == 2)
    p_charlie = next(p for p in proposals if p["host"] == "charlie.net")
    check("propose recommends approval for charlie.net", "RECOMMEND APPROVAL" in p_charlie["recommendation"])

    # Approve charlie.net
    rec_app = mgr.approve("charlie.net", operator="alice", rationale="Verified research source")
    check("approve recorded action approve", rec_app["action"] == "approve")
    check("approve returned policy digest", len(rec_app["policy_digest"]) == 64)
    check("approve called mock re_sign", re_sign_called is True)
    check("approve recorded re_signed True", rec_app["re_signed"] is True)

    # Verify YAML updated with charlie.net in alphabetical order
    updated_hosts = mgr.get_allowed_hosts()
    check("charlie.net is now in allowed_hosts", "charlie.net" in updated_hosts)
    check("alpha.com still in allowed_hosts", "alpha.com" in updated_hosts)
    check("bravo.org still in allowed_hosts", "bravo.org" in updated_hosts)

    # Reject delta.io
    rec_rej = mgr.reject("delta.io", operator="bob", reason="Off-topic forum")
    check("reject recorded action reject", rec_rej["action"] == "reject")

    # Verify unreviewed candidates now empty
    unreviewed_after = mgr.summarize_candidates(unreviewed_only=True)
    check("unreviewed candidates now 0 after approve & reject", len(unreviewed_after) == 0)

    # Verify approval audit trail
    history = mgr.get_approval_history()
    check("audit history contains 2 records", len(history) == 2)
    check("history actions match", [h["action"] for h in history] == ["approve", "reject"])

# ---------------------------------------------------------------------------
# Test 5: CLI Subcommands
# ---------------------------------------------------------------------------
print("\n[5] Testing CLI subcommands...")
with tempfile.TemporaryDirectory() as tmpdir:
    t_root = Path(tmpdir)
    p_file = t_root / "cli_policy.yaml"
    c_file = t_root / "cli_candidates.jsonl"
    a_file = t_root / "cli_approvals.audit.jsonl"

    p_file.write_text(json.dumps(initial_policy_content), encoding="utf-8")
    c_file.write_text(json.dumps({"timestamp": "2026-09-14T02:00:00Z", "task_id": 99, "host": "testcli.org"}) + "\n")

    base_args = ["--policy", str(p_file), "--candidates", str(c_file), "--approvals", str(a_file)]

    code_list = policy_manager.main(base_args + ["list"])
    check("CLI list returns 0", code_list == 0)

    code_prop = policy_manager.main(base_args + ["propose"])
    check("CLI propose returns 0", code_prop == 0)

    code_app = policy_manager.main(base_args + ["approve", "testcli.org", "--no-attest", "--rationale", "CLI test"])
    check("CLI approve returns 0", code_app == 0)

    code_rej = policy_manager.main(base_args + ["reject", "badsite.com", "--reason", "Dangerous"])
    check("CLI reject returns 0", code_rej == 0)

# ---------------------------------------------------------------------------
# Test 6: Candidate Domain Recording & Fixture Segregation Guard
# ---------------------------------------------------------------------------
print("\n[6] Testing Candidate Recording & Fixture Segregation...")
with tempfile.TemporaryDirectory() as tmpdir:
    t_root = Path(tmpdir)
    p_file = t_root / "policy.yaml"
    runs_tmp = t_root / "runs"
    p_file.write_text(json.dumps(initial_policy_content), encoding="utf-8")

    # Record valid candidate
    rec = policy_manager.record_candidate(
        host="new-research-lead.org",
        url="https://new-research-lead.org/pricing",
        task_id=101,
        attempt=1,
        runs_dir=runs_tmp,
        policy_path=p_file,
    )
    check("record_candidate records valid candidate", rec is not None and rec["host"] == "new-research-lead.org")
    c_log = runs_tmp / "policy_expansion_candidates.jsonl"
    check("candidate written to jsonl", c_log.is_file())
    lines = [json.loads(line) for line in c_log.read_text(encoding="utf-8").splitlines() if line.strip()]
    check("jsonl content matches", len(lines) == 1 and lines[0]["host"] == "new-research-lead.org")

    # Record already-allowed host is skipped
    rec_allowed = policy_manager.record_candidate(
        host="alpha.com",
        url="https://alpha.com/docs",
        runs_dir=runs_tmp,
        policy_path=p_file,
    )
    check("already-allowed host is skipped", rec_allowed is None)

    # Record invalid syntax host is skipped
    rec_invalid = policy_manager.record_candidate(
        host="invalid..host",
        runs_dir=runs_tmp,
        policy_path=p_file,
    )
    check("invalid syntax host is skipped", rec_invalid is None)

    # Fixture-segregation guard check
    with patch.dict(os.environ, {"AGI_TEST_TIER": "unit"}):
        prod_runs = (ROOT / "runs").resolve()
        rec_guard = policy_manager.record_candidate(
            host="dangerous-polluter.com",
            runs_dir=prod_runs,
            policy_path=p_file,
        )
        check("fixture-segregation prevents polluting prod runs", rec_guard is None)

# ---------------------------------------------------------------------------
# Test 7: Batch Pre-Screening & Approve-Safe (Method & CLI)
# ---------------------------------------------------------------------------
print("\n[7] Testing Batch Pre-Screening & Approve-Safe...")
with tempfile.TemporaryDirectory() as tmpdir:
    t_root = Path(tmpdir)
    p_file = t_root / "safe_policy.yaml"
    c_file = t_root / "safe_candidates.jsonl"
    a_file = t_root / "safe_approvals.audit.jsonl"

    p_file.write_text(json.dumps(initial_policy_content), encoding="utf-8")
    mgr_safe = policy_manager.PolicyManager(
        policy_path=p_file,
        candidates_path=c_file,
        approvals_path=a_file,
        re_sign_runner=lambda: True,
    )

    # Seed candidates: safe vs risky
    candidates_data = [
        {"timestamp": "2026-10-04T05:00:00Z", "task_id": 201, "host": "safe-capterra-review.org"},
        {"timestamp": "2026-10-04T05:01:00Z", "task_id": 202, "host": "dangerous-tld.zip"},
        {"timestamp": "2026-10-04T05:02:00Z", "task_id": 203, "host": "internal-service.localho.st"},
    ]
    with c_file.open("w", encoding="utf-8") as f:
        for c in candidates_data:
            f.write(json.dumps(c) + "\n")

    def mock_safe_resolver(host, port, proto=socket.IPPROTO_TCP):
        if host == "safe-capterra-review.org":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
        if host == "dangerous-tld.zip":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("198.51.100.1", 443))]
        if "localho.st" in host:
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))]
        raise socket.gaierror(-2, "Name or service not known")

    # Dry-run test: returns safe candidates without modifying policy
    dry_approved = mgr_safe.approve_safe_candidates(
        operator="test_operator",
        resolver=mock_safe_resolver,
        dry_run=True,
    )
    check("dry-run returns safe candidate", len(dry_approved) == 1 and dry_approved[0]["host"] == "safe-capterra-review.org")
    check("dry-run did not modify allowed_hosts", "safe-capterra-review.org" not in mgr_safe.get_allowed_hosts())

    # Live approve-safe batch execution
    approved = mgr_safe.approve_safe_candidates(
        operator="test_operator",
        resolver=mock_safe_resolver,
        dry_run=False,
    )
    check("approve_safe_candidates approved exactly 1 safe candidate", len(approved) == 1)
    check("approved candidate host matches", approved[0]["host"] == "safe-capterra-review.org")
    check("safe-capterra-review.org now in allowed_hosts", "safe-capterra-review.org" in mgr_safe.get_allowed_hosts())
    check("dangerous-tld.zip not in allowed_hosts", "dangerous-tld.zip" not in mgr_safe.get_allowed_hosts())
    check("internal-service.localho.st not in allowed_hosts", "internal-service.localho.st" not in mgr_safe.get_allowed_hosts())

    # Verify audit history
    audit_history = mgr_safe.get_approval_history()
    check("audit history recorded approve-safe record", len(audit_history) == 1 and audit_history[0]["host"] == "safe-capterra-review.org")
    check("rationale indicates pre-screened safe", "Pre-screened safe candidate" in audit_history[0]["rationale"])

    # Test CLI approve-safe subcommand
    base_args = ["--policy", str(p_file), "--candidates", str(c_file), "--approvals", str(a_file)]
    code_safe_cli = policy_manager.main(base_args + ["approve-safe", "--dry-run", "--no-attest"])
    check("CLI approve-safe --dry-run returns 0", code_safe_cli == 0)

print(f"\n{checks - len(failures)}/{checks} checks passed")
if failures:
    raise SystemExit("FAILURES: " + ", ".join(failures))

