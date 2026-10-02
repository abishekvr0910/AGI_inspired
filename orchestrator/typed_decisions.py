"""Typed decision interface with offline and guarded TypeSafe backends.

Maps TypeSafe AI's three decision primitives (Noul, Choice, Score) to a
clean protocol-based interface with dependency-injected backends.

Backends:
- DeterministicRubricBackend: Offline, zero-spend, deterministic scoring
  using the same logic as the existing lead evaluator. This is the DEFAULT.
- JevBackend: TypeSafe HTTP client behind the ESTOP, signed egress-boundary,
  allowlist, and read-only credential gates. Network calls remain disabled by
  default and cannot pass the current repository policy.

Design Principles:
- EvidenceGate remains authoritative; model output can never authorize export.
- TypeSafe decisions are advisory for scoring/routing until independently calibrated.
- No secrets in repository files, logs, exceptions, fixtures, or output.
- The module is named 'typed_decisions' (not 'Jev') because it is a generic
  contract until a live Jev integration is authorized.

Official TypeSafe Primitives (per https://docs.typesafe.ai/):
- Noul: Boolean classification with confidence
- Choice: Categorical selection with probability distribution
- Score: Bounded numeric scale with confidence
"""
from __future__ import annotations

import json
import math
import re
import time
import ipaddress
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol, runtime_checkable
from urllib.parse import urlsplit


# ─── Decision Result Types ───────────────────────────────────────────────────

@dataclass(frozen=True)
class NoulDecision:
    """Boolean classification decision (TypeSafe 'Noul' primitive).

    In TypeSafe's API specification, a Noul answer is a single probability scalar in [0.0, 1.0]
    ('noul') representing the likelihood that the answer is yes. TypeSafe returns NO separate
    confidence field for Noul; outcome and confidence are strictly derived from probability:
    - outcome: probability >= threshold
    - confidence: round(abs(probability - 0.5) * 2.0, 4)

    To guarantee mathematical integrity, contradictory inputs (e.g. probability=0.1 with outcome=True,
    or probability=0.5 with high confidence) are explicitly rejected with ValueError.

    Attributes:
        probability: The raw TypeSafe 'noul' probability in [0.0, 1.0].
        threshold: The decision boundary threshold (default 0.5).
        backend: Identifier of the backend that produced this decision.
        latency_ms: Wall-clock latency in milliseconds.
    """
    probability: float = 1.0
    threshold: float = 0.5
    backend: str = "deterministic"
    latency_ms: float = 0.0

    def __init__(
        self,
        probability: float | None = None,
        threshold: float = 0.5,
        backend: str = "deterministic",
        latency_ms: float = 0.0,
        outcome: bool | None = None,
        confidence: float | None = None,
    ):
        if probability is None:
            if outcome is not None:
                probability = 1.0 if outcome else 0.0
            else:
                probability = 1.0

        if not (0.0 <= probability <= 1.0):
            raise ValueError(f"Probability must be in [0.0, 1.0], got {probability}")
        if not (0.0 <= threshold <= 1.0):
            raise ValueError(f"Threshold must be in [0.0, 1.0], got {threshold}")

        derived_outcome = probability >= threshold
        if outcome is not None and outcome != derived_outcome:
            raise ValueError(
                f"Contradictory outcome: outcome={outcome} contradicts probability={probability} at threshold={threshold}"
            )

        derived_confidence = round(abs(probability - 0.5) * 2.0, 4)
        if confidence is not None:
            if not (0.0 <= confidence <= 1.0):
                raise ValueError(f"Confidence must be in [0.0, 1.0], got {confidence}")
            if abs(confidence - derived_confidence) > 0.15:
                raise ValueError(
                    f"Contradictory confidence: confidence={confidence} contradicts probability={probability} (expected ~{derived_confidence})"
                )

        object.__setattr__(self, "probability", float(probability))
        object.__setattr__(self, "threshold", float(threshold))
        object.__setattr__(self, "backend", str(backend))
        object.__setattr__(self, "latency_ms", float(latency_ms))

    @property
    def noul(self) -> float:
        """Direct 1:1 alias matching TypeSafe API answer field ('noul')."""
        return self.probability

    @property
    def outcome(self) -> bool:
        """Derived Boolean classification: True if probability >= threshold."""
        return self.probability >= self.threshold

    @property
    def confidence(self) -> float:
        """Derived certainty from probability distance from uncertainty (0.5): |p - 0.5| * 2."""
        return round(abs(self.probability - 0.5) * 2.0, 4)


@dataclass(frozen=True)
class ChoiceDecision:
    """Categorical selection decision (TypeSafe 'Choice' primitive).

    Attributes:
        selected: The chosen category.
        allowed_choices: The set of valid choices.
        distribution: Probability distribution over allowed_choices.
        confidence: Overall confidence in [0.0, 1.0].
        backend: Identifier of the backend.
        latency_ms: Wall-clock latency in milliseconds.
    """
    selected: str
    allowed_choices: tuple[str, ...]
    distribution: dict[str, float] = field(default_factory=dict)
    confidence: float = 1.0
    backend: str = "deterministic"
    latency_ms: float = 0.0

    def __post_init__(self):
        if self.selected not in self.allowed_choices:
            raise ValueError(
                f"Selected '{self.selected}' not in allowed choices: {self.allowed_choices}"
            )
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(f"Confidence must be in [0.0, 1.0], got {self.confidence}")
        if self.distribution:
            for k in self.distribution:
                if k not in self.allowed_choices:
                    raise ValueError(f"Distribution key '{k}' not in allowed choices")
            total = sum(self.distribution.values())
            if abs(total - 1.0) > 0.01:
                raise ValueError(
                    f"Distribution must sum to ~1.0, got {total}"
                )


@dataclass(frozen=True)
class ScoreDecision:
    """Bounded numeric score decision (TypeSafe 'Score' primitive).

    Attributes:
        score: The numeric score within [min_score, max_score].
        min_score: Lower bound of the scale.
        max_score: Upper bound of the scale.
        confidence: Calibrated confidence in [0.0, 1.0].
        backend: Identifier of the backend.
        latency_ms: Wall-clock latency in milliseconds.
    """
    score: float
    min_score: float = 0.0
    max_score: float = 100.0
    confidence: float = 1.0
    backend: str = "deterministic"
    latency_ms: float = 0.0

    def __post_init__(self):
        if not (self.min_score <= self.score <= self.max_score):
            raise ValueError(
                f"Score {self.score} outside bounds [{self.min_score}, {self.max_score}]"
            )
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(f"Confidence must be in [0.0, 1.0], got {self.confidence}")


# ─── Backend Protocol ────────────────────────────────────────────────────────

@runtime_checkable
class DecisionBackend(Protocol):
    """Protocol for typed decision backends.

    Implementations must provide methods for each TypeSafe primitive type.
    All methods accept a context dict for decision-specific parameters and
    return the corresponding Decision result type.
    """

    @property
    def backend_id(self) -> str:
        """Unique identifier for this backend."""
        ...

    def decide_noul(self, context: dict) -> NoulDecision:
        """Make a Boolean classification decision."""
        ...

    def decide_choice(self, context: dict, allowed_choices: tuple[str, ...]) -> ChoiceDecision:
        """Make a categorical selection decision."""
        ...

    def decide_score(self, context: dict, min_score: float = 0.0, max_score: float = 100.0) -> ScoreDecision:
        """Make a bounded numeric score decision."""
        ...


# ─── Deterministic Rubric Backend (DEFAULT) ──────────────────────────────────

class DeterministicRubricBackend:
    """Offline, zero-spend, deterministic decision backend.

    Reproduces the exact scoring logic from scripts/evaluate_leads_typesafe.py.
    This is the production default. No API calls, no credentials, no spend.
    """

    @property
    def backend_id(self) -> str:
        return "deterministic_rubric"

    def decide_noul(self, context: dict) -> NoulDecision:
        """Boolean classification: is this a high-ticket commercial fit?

        Context keys:
            score (int): The ICP fit score (0-100).
            threshold (int, optional): Minimum score for True. Default 75.
        """
        t0 = time.perf_counter_ns()
        score = context.get("score", 0)
        threshold = context.get("threshold", 75)
        outcome = score >= threshold

        # Calibrate raw TypeSafe 'noul' probability in [0.0, 1.0] based on score distance
        # Derived confidence = round(abs(p - 0.5) * 2.0, 4)
        diff = score - threshold
        if diff > 15:
            probability = 0.975  # confidence = 0.95
        elif diff > 5:
            probability = 0.925  # confidence = 0.85
        elif diff >= 0:
            probability = 0.850  # confidence = 0.70
        elif diff > -10:
            probability = 0.150  # confidence = 0.70
        elif diff > -20:
            probability = 0.075  # confidence = 0.85
        else:
            probability = 0.025  # confidence = 0.95

        latency = (time.perf_counter_ns() - t0) / 1_000_000
        return NoulDecision(
            probability=probability,
            threshold=0.5,
            backend=self.backend_id,
            latency_ms=latency,
        )

    def decide_choice(self, context: dict, allowed_choices: tuple[str, ...]) -> ChoiceDecision:
        """Categorical waste vector classification.

        Context keys:
            vertical (str): The industry vertical.
            notes (str, optional): Additional context notes.
        """
        t0 = time.perf_counter_ns()
        vertical = context.get("vertical", "")

        # Map vertical to choice key
        if "Dental" in vertical:
            slug = "broad_match_non_converting"
        elif "Roofing" in vertical:
            slug = "residential_spillage"
        elif "HVAC" in vertical:
            slug = "residential_ac_drainage"
        else:
            slug = "unfiltered_broad_match"

        if slug in allowed_choices:
            selected = slug
        else:
            # Match by semantic keyword in allowed choices (handles descriptive phrases)
            matched = None
            for c in allowed_choices:
                c_low = c.lower()
                if "Dental" in vertical and ("dental" in c_low or "clinic" in c_low or "non-converting" in c_low):
                    matched = c
                    break
                elif "Roofing" in vertical and ("roof" in c_low or "shingle" in c_low or "spillage" in c_low):
                    matched = c
                    break
                elif "HVAC" in vertical and ("hvac" in c_low or "ac" in c_low or "drainage" in c_low):
                    matched = c
                    break
            selected = matched if matched else (allowed_choices[-1] if allowed_choices else slug)

        # Deterministic distribution: 1.0 for selected, 0.0 for others
        distribution = {c: (1.0 if c == selected else 0.0) for c in allowed_choices}

        latency = (time.perf_counter_ns() - t0) / 1_000_000
        return ChoiceDecision(
            selected=selected,
            allowed_choices=allowed_choices,
            distribution=distribution,
            confidence=0.95,
            backend=self.backend_id,
            latency_ms=latency,
        )

    def decide_score(self, context: dict, min_score: float = 0.0, max_score: float = 100.0) -> ScoreDecision:
        """ICP fit scoring rubric.

        Context keys:
            vertical (str): Industry vertical.
            role (str): Decision-maker role.
            waste_str (str): Estimated monthly waste string.
            email (str, optional): Contact email for confidence calibration.
        """
        t0 = time.perf_counter_ns()
        score = 0

        vertical = context.get("vertical", "")
        role = context.get("role", "")
        waste_str = context.get("waste_str", "")
        email = context.get("email", "")

        # Vertical weight (Max 40)
        high_ticket = {"Commercial Roofing": 40, "Dental Implants": 38, "Commercial HVAC": 39}
        score += high_ticket.get(vertical, 20)

        # Role weight (Max 35)
        role_lower = role.lower()
        if any(k in role_lower for k in ["owner", "president", "founder", "managing partner"]):
            score += 35
        elif any(k in role_lower for k in ["vp", "director", "administrator", "chief"]):
            score += 28
        else:
            score += 15

        # Waste weight (Max 25)
        import re
        nums = re.findall(r"\d+", waste_str.replace(",", ""))
        waste_val = int(nums[0]) if nums else 0
        if waste_val >= 15000:
            score += 25
        elif waste_val >= 10000:
            score += 20
        else:
            score += 12

        # Clamp to bounds
        score = max(min_score, min(score, max_score))

        # Confidence calibration
        has_contact = bool(email and "@" in email and "." in email)
        has_role = bool(role and role.strip())
        has_waste = waste_val > 0
        if has_contact and has_role and has_waste:
            confidence = 0.95
        elif has_role and (has_contact or has_waste):
            confidence = 0.85
        else:
            confidence = 0.65

        latency = (time.perf_counter_ns() - t0) / 1_000_000
        return ScoreDecision(
            score=score,
            min_score=min_score,
            max_score=max_score,
            confidence=confidence,
            backend=self.backend_id,
            latency_ms=latency,
        )


# ─── Jev Backend (Gated HTTP Client; No Live Calls During Tests) ─────────────

class JevBackendNotConfigured(Exception):
    """Raised when the live Jev backend fails a configuration/safety gate."""


class JevBackendError(RuntimeError):
    """Sanitized transport, HTTP, or response-schema failure."""


@dataclass(frozen=True)
class _JevHttpResponse:
    status: int
    body: bytes
    headers: dict[str, str] = field(default_factory=dict)


_JEV_ENDPOINT = "https://api.typesafe.ai/v1/systemone"
_JEV_MODEL = "jev-latest"
_SAFE_STATE_FIELDS = frozenset({
    "industry", "role", "score", "segment", "threshold", "vertical", "waste_str",
})
_SENSITIVE_VALUE = re.compile(
    r"(?:\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b|"
    r"(?:https?://|www\.)\S+|"
    r"\b(?:[a-z0-9-]+\.)+[a-z]{2,}\b|"
    r"\b\+?\d[\d .()/-]{6,}\d\b)",
    re.IGNORECASE,
)
_RETRYABLE_HTTP = frozenset({429, 529})
_RETRYABLE_TRANSPORT = (TimeoutError, urllib.error.URLError, OSError)


def _read_typesafe_api_key() -> str | None:
    """Resolve a TypeSafe API key without persisting or exposing its value."""
    try:
        from orchestrator import secrets as credential_vault
    except ImportError:
        try:
            from . import secrets as credential_vault
        except Exception:
            return None
    try:
        return credential_vault.get_api_key("typesafe")
    except Exception:
        return None


def _default_estop_check() -> bool:
    try:
        from .execution_pause import pause_engaged
    except ImportError:  # direct-script/test import with orchestrator/ on sys.path
        from execution_pause import pause_engaged
    return bool(pause_engaged())


def _default_policy_loader():
    try:
        from .egress_policy import load_policy
    except ImportError:  # direct-script/test import with orchestrator/ on sys.path
        from egress_policy import load_policy
    return load_policy()


def _default_boundary_check():
    try:
        from .egress_policy import boundary_state
    except ImportError:  # direct-script/test import with orchestrator/ on sys.path
        from egress_policy import boundary_state
    return boundary_state()


def _stdlib_http_transport(
    endpoint: str,
    headers: dict[str, str],
    body: bytes,
    timeout_seconds: float,
    proxy_url: str,
) -> _JevHttpResponse:
    """POST only through the configured loopback egress broker."""
    class RejectRedirects(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, request, response, code, message, headers, new_url):
            return None

    proxy = urlsplit(proxy_url)
    try:
        is_loopback = ipaddress.ip_address(proxy.hostname or "").is_loopback
    except ValueError:
        is_loopback = False
    if proxy.scheme != "http" or not is_loopback or not proxy.port:
        raise JevBackendError("jev_proxy_not_loopback")
    # Disable urllib's environment-derived proxies, then set CONNECT explicitly
    # on the request. This avoids both arbitrary proxies and NO_PROXY bypass.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), RejectRedirects())
    request = urllib.request.Request(endpoint, data=body, headers=headers, method="POST")
    request.set_proxy(f"{proxy.hostname}:{proxy.port}", "https")
    try:
        with opener.open(request, timeout=timeout_seconds) as response:
            payload = response.read(1_048_577)
            return _JevHttpResponse(
                status=int(response.status), body=payload,
                headers={key.lower(): value for key, value in response.headers.items()},
            )
    except urllib.error.HTTPError as response:
        payload = response.read(1_048_577)
        return _JevHttpResponse(
            status=int(response.code), body=payload,
            headers={key.lower(): value for key, value in response.headers.items()},
        )


class JevBackend:
    """Guarded TypeSafe API client.

    Every outbound attempt requires ESTOP to be disengaged, a fresh valid
    signed boundary attestation, and the exact destination in the current
    broker allowlist. The API key is read from the credential bridge only
    after those local gates pass and is never stored on this instance.
    """

    def __init__(
        self,
        *,
        api_endpoint: str = _JEV_ENDPOINT,
        timeout_seconds: float = 5.0,
        max_retries: int = 3,
        transport: Callable[..., _JevHttpResponse] | None = None,
        credential_resolver: Callable[[], str | None] | None = None,
        estop_check: Callable[[], bool] | None = None,
        policy_loader: Callable[[], Any] | None = None,
        boundary_check: Callable[[], dict[str, Any]] | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ):
        parsed = urlsplit(str(api_endpoint))
        if (parsed.scheme != "https" or parsed.hostname != "api.typesafe.ai" or
                parsed.path != "/v1/systemone" or parsed.username or parsed.password or
                parsed.query or parsed.fragment or parsed.port not in (None, 443)):
            raise JevBackendNotConfigured("jev_endpoint_not_permitted")
        if not math.isfinite(float(timeout_seconds)) or not (0.1 <= timeout_seconds <= 60):
            raise ValueError("timeout_seconds must be between 0.1 and 60")
        if isinstance(max_retries, bool) or not isinstance(max_retries, int) or not (0 <= max_retries <= 5):
            raise ValueError("max_retries must be an integer between 0 and 5")
        self._endpoint = _JEV_ENDPOINT
        self._timeout = timeout_seconds
        self._max_retries = max_retries
        self._transport = transport or _stdlib_http_transport
        self._credential_resolver = credential_resolver or _read_typesafe_api_key
        self._estop_check = estop_check or _default_estop_check
        self._policy_loader = policy_loader or _default_policy_loader
        self._boundary_check = boundary_check or _default_boundary_check
        self._sleeper = sleeper
        self._requests_dispatched = 0

    @property
    def backend_id(self) -> str:
        return "jev_typesafe"

    @property
    def requests_dispatched(self) -> int:
        """Number of real HTTP attempts; injected transports are never called live."""
        return self._requests_dispatched if self.live_transport_enabled else 0

    @property
    def transport_attempts(self) -> int:
        """Total injected-or-live transport invocations; contains no payload data."""
        return self._requests_dispatched

    @property
    def live_transport_enabled(self) -> bool:
        """Only the built-in broker-bound transport qualifies as live measurement."""
        return self._transport is _stdlib_http_transport

    @staticmethod
    def _safe_state(context: dict) -> dict[str, Any]:
        if not isinstance(context, dict):
            raise JevBackendError("jev_invalid_context")
        state: dict[str, Any] = {}
        for key, value in context.items():
            normalized = str(key).strip().lower()
            if normalized not in _SAFE_STATE_FIELDS:
                continue
            if isinstance(value, bool):
                state[normalized] = value
            elif isinstance(value, (int, float)) and math.isfinite(float(value)):
                state[normalized] = value
            elif isinstance(value, str):
                clean = value.strip()[:512]
                if clean and not _SENSITIVE_VALUE.search(clean):
                    state[normalized] = clean
        if not state:
            raise JevBackendNotConfigured("jev_no_sanitized_state_fields")
        return state

    def _preflight(self) -> str:
        try:
            if self._estop_check():
                raise JevBackendNotConfigured("jev_live_blocked:estop_engaged")
            policy = self._policy_loader()
            endpoint_host = urlsplit(self._endpoint).hostname
            if endpoint_host not in policy.allowed_hosts:
                raise JevBackendNotConfigured("jev_live_blocked:host_not_allowlisted")
            boundary = self._boundary_check()
            if (not isinstance(boundary, dict) or boundary.get("ok") is not True or
                    boundary.get("policy_digest") != policy.digest):
                raise JevBackendNotConfigured("jev_live_blocked:boundary_unverified")
            return f"http://{policy.host}:{policy.port}"
        except JevBackendNotConfigured:
            raise
        except Exception as exc:
            raise JevBackendNotConfigured(
                f"jev_live_blocked:preflight_{type(exc).__name__}"
            ) from None

    @staticmethod
    def _decode_response(response: _JevHttpResponse) -> dict[str, Any]:
        if len(response.body) > 1_048_576:
            raise JevBackendError("jev_response_too_large")
        try:
            decoded = json.loads(response.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise JevBackendError("jev_invalid_json_response") from None
        if not isinstance(decoded, dict):
            raise JevBackendError("jev_invalid_response_shape")
        return decoded

    def _post(self, context: dict, question: dict[str, Any]) -> tuple[dict[str, Any], float]:
        state = self._safe_state(context)
        # Fail safety gates before touching the local credential store.
        proxy_url = self._preflight()
        api_key = self._credential_resolver()
        if not isinstance(api_key, str) or not api_key.strip():
            raise JevBackendNotConfigured("jev_api_key_missing")
        body = json.dumps({
            "state": state,
            "model": _JEV_MODEL,
            "questions": {"decision": question},
        }, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {api_key.strip()}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "AGI_like-Harness/1.0",
        }
        del api_key  # Do not retain credential material on the backend instance.
        started = time.perf_counter_ns()
        for attempt in range(self._max_retries + 1):
            # Re-check ESTOP and signed boundary immediately before every dispatch.
            proxy_url = self._preflight()
            try:
                self._requests_dispatched += 1
                response = self._transport(
                    self._endpoint, headers, body, self._timeout, proxy_url,
                )
            except _RETRYABLE_TRANSPORT as exc:
                if attempt >= self._max_retries:
                    raise JevBackendError("jev_transport_failed") from None
                self._sleeper(min(0.5 * (2 ** attempt), 30.0))
                continue
            except Exception:
                raise JevBackendError("jev_transport_failed") from None
            if response.status in _RETRYABLE_HTTP and attempt < self._max_retries:
                raw_delay = response.headers.get("retry-after", "")
                try:
                    retry_after = max(0.0, min(float(raw_delay), 30.0)) if raw_delay else 0.0
                except (TypeError, ValueError):
                    retry_after = 0.0
                backoff = min(0.5 * (2 ** attempt), 30.0)
                self._sleeper(min(max(backoff, retry_after), 30.0))
                continue
            if response.status < 200 or response.status >= 300:
                raise JevBackendError(f"jev_http_error:{response.status}")
            payload = self._decode_response(response)
            latency_ms = (time.perf_counter_ns() - started) / 1_000_000
            return payload, latency_ms
        raise JevBackendError("jev_transport_failed")

    @staticmethod
    def _answer(payload: dict[str, Any], expected_type: str) -> dict[str, Any]:
        answers = payload.get("answers")
        answer = answers.get("decision") if isinstance(answers, dict) else None
        if not isinstance(answer, dict) or answer.get("type") != expected_type:
            raise JevBackendError("jev_answer_type_mismatch")
        return answer

    def decide_noul(self, context: dict) -> NoulDecision:
        payload, latency = self._post(context, {
            "type": "noul",
            "instructions": "Does this prospect meet the supplied qualification threshold?",
            "criteria": {
                "true": "The supplied score meets or exceeds the supplied threshold.",
                "false": "The supplied score is below the supplied threshold.",
            },
        })
        answer = self._answer(payload, "noul")
        probability = answer.get("noul")
        if (isinstance(probability, bool) or not isinstance(probability, (int, float)) or
                not math.isfinite(float(probability)) or not 0.0 <= float(probability) <= 1.0):
            raise JevBackendError("jev_invalid_noul_value")
        return NoulDecision(probability=float(probability), backend=self.backend_id, latency_ms=latency)

    def decide_choice(self, context: dict, allowed_choices: tuple[str, ...]) -> ChoiceDecision:
        choices = tuple(allowed_choices)
        if (not choices or len(choices) > 255 or
                any(not isinstance(item, str) or not item.strip() for item in choices) or
                len(set(choices)) != len(choices)):
            raise ValueError("allowed_choices must contain 1-255 unique non-empty strings")
        payload, latency = self._post(context, {
            "type": "choice",
            "instructions": "Which option best matches the supplied sanitized prospect attributes?",
            "criteria": {item: None for item in choices},
        })
        answer = self._answer(payload, "choice")
        selected = answer.get("choice")
        probabilities = answer.get("probabilities")
        confidence = answer.get("confidence")
        if (not isinstance(selected, str) or not isinstance(probabilities, dict) or
                set(probabilities) != set(choices) or isinstance(confidence, bool) or
                not isinstance(confidence, (int, float)) or
                not math.isfinite(float(confidence)) or not 0.0 <= float(confidence) <= 1.0):
            raise JevBackendError("jev_invalid_choice_answer")
        if selected not in choices:
            raise JevBackendError("jev_invalid_choice_answer")
        distribution = self._validated_distribution(probabilities, choices)
        return ChoiceDecision(
            selected=selected, allowed_choices=choices, distribution=distribution,
            confidence=float(confidence), backend=self.backend_id, latency_ms=latency,
        )

    def decide_score(self, context: dict, min_score: float = 0.0, max_score: float = 100.0) -> ScoreDecision:
        if (isinstance(min_score, bool) or isinstance(max_score, bool) or
                not isinstance(min_score, (int, float)) or not isinstance(max_score, (int, float)) or
                not math.isfinite(float(min_score)) or not math.isfinite(float(max_score)) or
                float(max_score) <= float(min_score)):
            raise ValueError("max_score must be finite and greater than finite min_score")
        criteria = [
            "0: no fit; the attributes strongly conflict with the target.",
            "1: exceptionally weak fit; almost all indicators are negative.",
            "2: very weak fit; major gaps remain.",
            "3: weak fit; more negative than positive indicators.",
            "4: below-average fit; notable gaps and limited evidence.",
            "5: mixed fit; meaningful positives and negatives are balanced.",
            "6: above-average fit; most indicators are favorable.",
            "7: strong fit; clear alignment with only minor gaps.",
            "8: very strong fit; nearly all indicators are favorable.",
            "9: exceptional fit; outstanding alignment with the target.",
        ]
        payload, latency = self._post(context, {
            "type": "score",
            "instructions": "Rate prospect fit on the ordered scale. Use only the supplied sanitized attributes.",
            "criteria": criteria,
        })
        answer = self._answer(payload, "score")
        raw_score = answer.get("score")
        probabilities = answer.get("probabilities")
        confidence = answer.get("confidence")
        expected_levels = tuple(str(index) for index in range(len(criteria)))
        if (isinstance(raw_score, bool) or not isinstance(raw_score, (int, float)) or
                not isinstance(probabilities, dict) or set(probabilities) != set(expected_levels) or
                isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or
                not math.isfinite(float(confidence)) or not 0.0 <= float(confidence) <= 1.0):
            raise JevBackendError("jev_invalid_score_answer")
        self._validated_distribution(probabilities, expected_levels)
        score_value = float(raw_score)
        if not 0.0 <= score_value <= 9.0:
            raise JevBackendError("jev_score_out_of_range")
        scaled_score = float(min_score) + (score_value / 9.0) * (float(max_score) - float(min_score))
        return ScoreDecision(
            score=scaled_score, min_score=float(min_score), max_score=float(max_score),
            confidence=float(confidence), backend=self.backend_id, latency_ms=latency,
        )

    @staticmethod
    def _validated_distribution(values: dict[str, Any], keys: tuple[str, ...]) -> dict[str, float]:
        distribution: dict[str, float] = {}
        for key in keys:
            value = values.get(key)
            if (isinstance(value, bool) or not isinstance(value, (int, float)) or
                    not math.isfinite(float(value)) or not 0.0 <= float(value) <= 1.0):
                raise JevBackendError("jev_invalid_probability_distribution")
            distribution[key] = float(value)
        if abs(sum(distribution.values()) - 1.0) > 0.01:
            raise JevBackendError("jev_invalid_probability_distribution")
        return distribution


# ─── Backend Factory ─────────────────────────────────────────────────────────

def get_default_backend() -> DeterministicRubricBackend:
    """Returns the safe, zero-spend deterministic rubric backend."""
    return DeterministicRubricBackend()
