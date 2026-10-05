"""Remediate synthetic sample artifacts in workspace/ for honest sample classification.

P0-A Scope:
1. Inventory 8 synthetic sample prospects and generate dry-run manifest.
2. Back up original files with SHA256 checksums before modification.
3. Pause Google Ads Editor CSVs (Status='Paused') and prefix Campaign with '[SAMPLE] '.
4. Relabel PROSPECT_TRACKER.csv status from 'Ready to Send' to 'SAMPLE_NOT_FOR_SEND'.
5. Neutralize deceptive waste assertions in pitch files and watermarks in dossiers.
6. Provide idempotent re-execution and reversible restore from backup.
7. Preserves real/non-sample clients (e.g., el-shaddai-coffee-katowice) untouched.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any
import sys

ROOT = Path(__file__).resolve().parents[1]
ORCH = ROOT / "orchestrator"
for p in (ROOT, ORCH):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

try:
    from runtime_context import ROOT
except ImportError:
    pass

KNOWN_SAMPLE_CLIENT_IDS = [
    "texas-premier-roofing",
    "lone-star-industrial-roofs",
    "austin-commercial-roof-pros",
    "illinois-implant-institute",
    "south-florida-implant-center",
    "pacific-implant-surgeons",
    "desert-valley-commercial-hvac",
    "sunbelt-commercial-mechanical",
]
SAMPLE_CLIENT_IDS = KNOWN_SAMPLE_CLIENT_IDS

EXCLUDED_CLIENT_IDS = [
    "el-shaddai-coffee-katowice",
]
PROTECTED_CLIENT_IDS = EXCLUDED_CLIENT_IDS


def sha256_file(path: Path | str) -> str:
    """Compute hex sha256 digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def find_sample_artifacts(workspace_dir: Path) -> list[dict[str, Any]]:
    """Discover all files associated with the 8 known synthetic samples."""
    workspace_dir = workspace_dir.resolve()
    artifacts: list[dict[str, Any]] = []

    clients_dir = workspace_dir / "clients"
    pitches_dir = workspace_dir / "outbound_pitches"

    for cid in KNOWN_SAMPLE_CLIENT_IDS:
        cdir = clients_dir / cid
        if cdir.is_dir():
            for f in sorted(cdir.iterdir()):
                if f.is_file():
                    rel_ws = f"workspace/{f.relative_to(workspace_dir)}".replace("\\", "/")
                    artifacts.append({
                        "client_id": cid,
                        "path": str(f.resolve()),
                        "rel_path": rel_ws,
                        "file_name": f.name,
                        "file_type": f.suffix.lstrip("."),
                        "classification": "synthetic_sample",
                        "action": "remediate",
                    })

        pitch_file = pitches_dir / f"{cid}_pitch.txt"
        if pitch_file.is_file():
            rel_ws = f"workspace/{pitch_file.relative_to(workspace_dir)}".replace("\\", "/")
            artifacts.append({
                "client_id": cid,
                "path": str(pitch_file.resolve()),
                "rel_path": rel_ws,
                "file_name": pitch_file.name,
                "file_type": "txt",
                "classification": "synthetic_sample",
                "action": "remediate",
            })

    tracker_file = workspace_dir / "PROSPECT_TRACKER.csv"
    if tracker_file.is_file():
        artifacts.append({
            "client_id": "_tracker",
            "path": str(tracker_file.resolve()),
            "rel_path": f"workspace/{tracker_file.relative_to(workspace_dir)}".replace("\\", "/"),
            "file_name": tracker_file.name,
            "file_type": "csv",
            "classification": "shared_pipeline_tracker",
            "action": "remediate_sample_rows",
        })

    return artifacts


def create_backup(workspace_dir: Path, backup_dir: Path, artifacts: list[dict[str, Any]]) -> dict[str, Any]:
    """Copy all target artifacts into backup_dir preserving structure and recording checksums.
    
    Baseline Preservation (R8): If an artifact already exists in backup_dir, the existing
    baseline is preserved and never overwritten by subsequent passes.
    """
    backup_dir.mkdir(parents=True, exist_ok=True)
    manifest_file = backup_dir / "manifest.json"
    existing_files: dict[str, dict[str, Any]] = {}
    if manifest_file.is_file():
        try:
            with open(manifest_file, "r", encoding="utf-8") as f:
                old_m = json.load(f)
                existing_files = {e["rel_path"]: e for e in old_m.get("files", [])}
        except Exception:
            existing_files = {}

    manifest: dict[str, Any] = {
        "created_at": "2026-10-04T14:00:00Z",
        "workspace_root": str(workspace_dir.resolve()),
        "files": [],
    }

    for art in artifacts:
        src = Path(art["path"])
        if not src.is_file():
            continue
        rel = art["rel_path"]
        if rel.startswith("workspace/"):
            rel_in_ws = Path(rel[len("workspace/"):])
        else:
            rel_in_ws = Path(rel)
        dest = backup_dir / rel_in_ws

        # If already present in backup baseline, preserve original baseline!
        if dest.is_file() and rel in existing_files:
            manifest["files"].append(existing_files[rel])
            continue

        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        checksum = sha256_file(dest)
        manifest["files"].append({
            "rel_path": rel,
            "dest_path": str(dest).replace("\\", "/"),
            "sha256": checksum,
            "client_id": art["client_id"],
        })

    with open(manifest_file, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    return manifest


def restore_backup(workspace_dir: Path, backup_dir: Path) -> int:
    """Restore all artifacts from backup manifest into workspace_dir."""
    manifest_file = backup_dir / "manifest.json"
    if not manifest_file.is_file():
        raise FileNotFoundError(f"Backup manifest not found: {manifest_file}")

    with open(manifest_file, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    ws_resolved = workspace_dir.resolve()
    backup_resolved = backup_dir.resolve()

    restored_count = 0
    for entry in manifest["files"]:
        rel = entry["rel_path"]
        if rel.startswith("workspace/"):
            rel_in_ws = Path(rel[len("workspace/"):])
        else:
            rel_in_ws = Path(rel)

        backup_src = (backup_dir / rel_in_ws).resolve()
        target_dest = (workspace_dir / rel_in_ws).resolve()

        # Path traversal guard (R8): verify resolved target is strictly contained inside workspace_dir
        if not target_dest.is_relative_to(ws_resolved):
            raise ValueError(f"Path traversal detected in backup manifest target: {rel}")
        if not backup_src.is_relative_to(backup_resolved):
            raise ValueError(f"Path traversal detected in backup manifest source: {rel}")

        if not backup_src.is_file():
            raise FileNotFoundError(f"Missing backup file: {backup_src}")

        actual_hash = sha256_file(backup_src)
        if actual_hash != entry["sha256"]:
            raise ValueError(f"Checksum mismatch for backup file {backup_src}")

        target_dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup_src, target_dest)
        restored_count += 1

    return restored_count


def remediate_google_ads_csv(csv_path: Path) -> bool:
    """Pause all rows and ensure Campaign starts with '[SAMPLE] '."""
    if not csv_path.is_file():
        return False

    with open(csv_path, "r", encoding="utf-8", newline="") as f:
        reader = list(csv.reader(f))

    if not reader:
        return False

    # Filter out initial comment rows
    data_rows = [r for r in reader if r and not r[0].startswith("#")]
    if not data_rows or len(data_rows) < 2:
        return False

    headers = list(data_rows[0])
    modified = len(data_rows) != len(reader)

    # Ensure header column names are clean
    for idx, col in enumerate(headers):
        if col.endswith("Campaign"):
            if col != "Campaign":
                headers[idx] = "Campaign"
                modified = True
        elif col.endswith("Status"):
            if col != "Status":
                headers[idx] = "Status"
                modified = True

    try:
        camp_idx = headers.index("Campaign")
        stat_idx = headers.index("Status")
    except ValueError:
        return False

    new_rows = [headers]
    for row in data_rows[1:]:
        if len(row) <= max(camp_idx, stat_idx):
            new_rows.append(row)
            continue

        c_val = row[camp_idx]
        clean_c = c_val.replace("[SAMPLE] ", "").replace("SAMPLE_", "").strip()
        target_c = f"[SAMPLE] {clean_c}"
        if c_val != target_c:
            row[camp_idx] = target_c
            modified = True

        if row[stat_idx] != "Paused":
            row[stat_idx] = "Paused"
            modified = True

        new_rows.append(row)

    if modified:
        with open(csv_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerows(new_rows)

    return modified

    if modified:
        with open(csv_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerows(new_rows)

    return modified


def remediate_campaign_json(json_path: Path) -> bool:
    """Prefix campaign name with '[SAMPLE] ' and set all ad groups/ads/keywords to Paused."""
    if not json_path.is_file():
        return False

    with open(json_path, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            return False

    modified = False
    if "name" in data and not data["name"].startswith("[SAMPLE] "):
        data["name"] = f"[SAMPLE] {data['name']}"
        modified = True

    if data.get("status") != "Paused":
        data["status"] = "Paused"
        modified = True

    for ag in data.get("ad_groups", []):
        if ag.get("status") != "Paused":
            ag["status"] = "Paused"
            modified = True

    if modified:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    return modified


def remediate_strategy_dossier_md(md_path: Path) -> bool:
    """Ensure strategy dossier has sample watermark and sample title prefix."""
    if not md_path.is_file():
        return False

    content = md_path.read_text(encoding="utf-8")
    modified = False

    warning_block = (
        "> [!WARNING]\n"
        "> **SYNTHETIC SAMPLE MATERIAL — NOT FOR PRODUCTION USE**\n"
        "> This strategy dossier was generated from synthetic demonstration inputs.\n"
        "> No live client account audit has been performed.\n\n"
    )

    if not content.startswith("> [!WARNING]\n> **SYNTHETIC SAMPLE MATERIAL"):
        content = warning_block + content
        modified = True

    if "> **Confidential Client Report**" in content:
        content = content.replace("> **Confidential Client Report**", "> **[SAMPLE DEMONSTRATION MATERIAL]**")
        modified = True

    lines = content.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("# Executive Strategy & Distribution Audit:") and not line.startswith("# [SAMPLE] Executive Strategy & Distribution Audit:"):
            lines[i] = line.replace("# Executive Strategy & Distribution Audit:", "# [SAMPLE] Executive Strategy & Distribution Audit:")
            modified = True
            break

    if modified:
        md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return modified


def remediate_strategy_dossier_html(html_path: Path) -> bool:
    """Ensure strategy dossier HTML has sample banner and title prefix."""
    if not html_path.is_file():
        return False

    content = html_path.read_text(encoding="utf-8")
    modified = False

    banner = '<div style="background:#b91c1c;color:#ffffff;padding:12px;text-align:center;font-weight:bold;letter-spacing:1px;font-family:sans-serif;margin-bottom:16px;border-radius:4px;">⚠ SAMPLE DEMONSTRATION MATERIAL — GENERATED FROM SYNTHETIC DATA — NOT FOR OUTREACH</div>'
    if banner not in content:
        content = banner + "\n" + content
        modified = True

    if "<title>" in content and "<title>[SAMPLE]" not in content:
        content = content.replace("<title>", "<title>[SAMPLE] ")
        modified = True

    if modified:
        html_path.write_text(content, encoding="utf-8")

    return modified


def remediate_pitch_file(pitch_path: Path) -> bool:
    """Neutralize misleading claims of detected ad waste in pitch emails."""
    if not pitch_path.is_file():
        return False

    content = pitch_path.read_text(encoding="utf-8")
    modified = False

    banner = (
        "================================================================================\n"
        "[SAMPLE / DEMONSTRATION MATERIAL ONLY - NOT FOR OUTREACH]\n"
        "This pitch was generated from synthetic sample data. No real search audit or\n"
        "query leak analysis was performed on this domain.\n"
        "DO NOT SEND TO RECIPIENT.\n"
        "================================================================================\n"
    )
    if "[SAMPLE / DEMONSTRATION MATERIAL ONLY" not in content and "[SAMPLE DEMONSTRATION MATERIAL" not in content:
        content = banner + content
        modified = True

    old_analysis_claim = "We ran an automated query analysis on your local market footprint and noticed search ads routinely matching to queries like:"
    new_analysis_claim = "[SAMPLE SCENARIO] In an audit scenario, search ads without negative shields routinely match to queries like:"
    if old_analysis_claim in content:
        content = content.replace(old_analysis_claim, new_analysis_claim)
        modified = True

    if "ESTIMATED AD WASTE DETECTED:" in content:
        content = content.replace(
            "ESTIMATED AD WASTE DETECTED:",
            "ESTIMATED SAMPLE LEAK (ILLUSTRATIVE SYNTHETIC ESTIMATE ONLY - UNVERIFIED):"
        )
        modified = True

    old_claim = "it should instantly eliminate an estimated"
    if old_claim in content:
        lines = content.splitlines()
        new_lines = []
        for line in lines:
            if old_claim in line:
                new_lines.append(
                    "Feel free to hand this directly to your in-house marketing manager or agency to review as a demonstration—"
                    "in production this is designed to address unconvertible clicks."
                )
                modified = True
            else:
                new_lines.append(line)
        content = "\n".join(new_lines) + "\n"

    if modified:
        pitch_path.write_text(content, encoding="utf-8")

    return modified


def remediate_prospect_tracker(tracker_path: Path) -> bool:
    """Relabel sample rows in PROSPECT_TRACKER.csv from 'Ready to Send' to 'SAMPLE_NOT_FOR_SEND'."""
    if not tracker_path.is_file():
        return False

    with open(tracker_path, "r", encoding="utf-8", newline="") as f:
        reader = list(csv.reader(f))

    if not reader or len(reader) < 2:
        return False

    headers = reader[0]
    try:
        status_idx = headers.index("Outreach Status")
        waste_idx = headers.index("Est Monthly Ad Waste")
        dossier_idx = headers.index("Audit Dossier Path")
        notes_idx = headers.index("Notes")
    except ValueError:
        return False

    modified = False
    new_rows = [headers]
    for row in reader[1:]:
        if len(row) <= max(status_idx, waste_idx, dossier_idx, notes_idx):
            new_rows.append(row)
            continue

        dossier_path = row[dossier_idx]
        is_sample = any(f"clients/{cid}/" in dossier_path for cid in KNOWN_SAMPLE_CLIENT_IDS)

        if is_sample:
            if row[status_idx] != "SAMPLE_NOT_FOR_SEND":
                row[status_idx] = "SAMPLE_NOT_FOR_SEND"
                modified = True
            if not row[waste_idx].startswith("[SAMPLE]"):
                row[waste_idx] = f"[SAMPLE] {row[waste_idx]}".strip()
                modified = True
            if "DO NOT SEND" not in row[notes_idx]:
                row[notes_idx] = "Synthetic sample demonstration material - DO NOT SEND"
                modified = True

        new_rows.append(row)

    if modified:
        with open(tracker_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            writer.writerows(new_rows)

    return modified


def remediate_all(workspace_dir: Path, dry_run: bool = False, backup_dir: Path | None = None) -> dict[str, Any]:
    """Execute complete sample artifact remediation workflow."""
    workspace_dir = workspace_dir.resolve()
    artifacts = find_sample_artifacts(workspace_dir)

    for art in artifacts:
        p = Path(art["path"])
        art["sha256_before"] = sha256_file(p) if p.is_file() else None

    if dry_run:
        return {
            "status": "dry_run_complete",
            "artifact_count": len(artifacts),
            "artifacts": artifacts,
            "modified_count": 0,
        }

    # Create backup before any edits
    if backup_dir is None:
        backup_dir = workspace_dir / "backups" / "samples_pre_remediation"
    backup_manifest = create_backup(workspace_dir, backup_dir, artifacts)

    # Perform remediation per artifact
    modified_files = []
    for art in artifacts:
        p = Path(art["path"])
        file_name = art["file_name"]
        mod = False

        if file_name == "google_ads_editor_import.csv":
            mod = remediate_google_ads_csv(p)
        elif file_name == "campaign_structure.json":
            mod = remediate_campaign_json(p)
        elif file_name == "strategy_dossier.md":
            mod = remediate_strategy_dossier_md(p)
        elif file_name == "strategy_dossier.html":
            mod = remediate_strategy_dossier_html(p)
        elif file_name.endswith("_pitch.txt"):
            mod = remediate_pitch_file(p)
        elif file_name == "PROSPECT_TRACKER.csv":
            mod = remediate_prospect_tracker(p)

        if mod:
            modified_files.append(art["rel_path"])

    return {
        "status": "remediation_complete",
        "artifact_count": len(artifacts),
        "modified_count": len(modified_files),
        "modified_files": modified_files,
        "backup_dir": str(backup_dir),
        "backup_file_count": len(backup_manifest["files"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Remediate synthetic sample artifacts in workspace/")
    parser.add_argument("--dry-run", action="store_true", help="Print manifest without modifying files")
    parser.add_argument("--restore", action="store_true", help="Restore artifacts from backup directory")
    parser.add_argument("--workspace-dir", type=Path, default=ROOT / "workspace", help="Workspace root path")
    parser.add_argument("--backup-dir", type=Path, default=None, help="Backup destination or source directory")
    args = parser.parse_args()

    ws = args.workspace_dir.resolve()
    if args.restore:
        b_dir = args.backup_dir or (ws / "backups" / "samples_pre_remediation")
        count = restore_backup(ws, b_dir)
        print(f"[+] Successfully restored {count} artifacts from {b_dir}")
        return 0

    res = remediate_all(ws, dry_run=args.dry_run, backup_dir=args.backup_dir)
    print(json.dumps(res, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
