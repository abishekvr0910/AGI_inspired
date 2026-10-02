"""Native Agentic Research Worker for AGI_like Harness.

Pure Python, zero-external-bloat agentic research loop that executes turns
under strict OS-level confinement, using our own tools (search, fetch, CDP browser)
without any dependency on external CLI frameworks. Directly integrates with the
research notebook and skill promotion memory loop.

Zero-spend: Never executes write or mutate API calls to ad platforms.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser
import asyncio
import json
import logging
import os
from pathlib import Path
import re
import sys
import time
from typing import Any, Callable
from urllib.parse import urljoin, urlsplit, urlunsplit
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT, ROOT / "orchestrator"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from execution_pause import pause_engaged
import browser_daemon
from research_notebook import Notebook, safe_url
import promote

# Optional dependencies for CDP browser extraction
try:
    import websockets
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False

try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False

logger = logging.getLogger(__name__)

DEFAULT_EGRESS_PROXY = "http://127.0.0.1:8787"
MAX_REDIRECTS = 5
MAX_BODY_BYTES = 400_000
DEFAULT_CHAR_LIMIT = 15_000
USER_AGENT = "Mozilla/5.0 (compatible; AGI-like-native-worker/1.0)"


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg"}:
            self.hidden += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg"} and self.hidden:
            self.hidden -= 1

    def handle_data(self, data: str) -> None:
        if not self.hidden and data.strip():
            self.parts.append(data.strip())

    def text(self) -> str:
        return re.sub(r"\s+", " ", " ".join(self.parts)).strip()


def execute_web_search(query: str, limit: int = 5, proxy: str | None = None) -> list[dict[str, Any]]:
    """Execute grounded web search via the egress broker."""
    proxy_url = proxy or os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY") or DEFAULT_EGRESS_PROXY
    safe_limit = max(1, min(limit, 10))

    # 1. Try ddgs via proxy
    try:
        from ddgs import DDGS
        with DDGS(proxy=proxy_url, timeout=12) as client:
            for backend in ["yahoo", "brave", "auto"]:
                try:
                    hits = list(client.text(query, backend=backend, max_results=safe_limit))
                    if hits:
                        results = []
                        for i, hit in enumerate(hits[:safe_limit]):
                            url = str(hit.get("href") or hit.get("url") or "")
                            results.append({
                                "title": str(hit.get("title", "")),
                                "url": url,
                                "snippet": str(hit.get("body", "")),
                                "position": i + 1,
                            })
                        return results
                except Exception:
                    continue
    except Exception:
        pass

    # 2. Fallback to direct HTML scraper via proxy
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({"https": proxy_url, "http": proxy_url})
    )
    data = urllib.parse.urlencode({"q": query}).encode("utf-8")
    req = urllib.request.Request(
        "https://html.duckduckgo.com/html/",
        data=data,
        headers={"User-Agent": USER_AGENT, "Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with opener.open(req, timeout=15) as res:
            html = res.read().decode("utf-8", errors="replace")
    except Exception as err:
        return [{"error": f"Search request failed: {err}", "url": "", "title": "", "snippet": ""}]

    results = []
    try:
        import lxml.html
        tree = lxml.html.fromstring(html)
        body_nodes = tree.xpath("//div[contains(@class, 'result__body')]")
        for i, node in enumerate(body_nodes[:safe_limit]):
            links = node.xpath(".//a[contains(@class, 'result__snippet')]")
            titles = node.xpath(".//a[contains(@class, 'result__url')]")
            url = links[0].get("href") if links else ""
            title = titles[0].text_content().strip() if titles else ""
            snippet = links[0].text_content().strip() if links else ""
            if url:
                results.append({"title": title, "url": url, "snippet": snippet, "position": i + 1})
    except Exception:
        pass
    return results


def execute_web_fetch(url: str, char_limit: int = DEFAULT_CHAR_LIMIT, proxy: str | None = None) -> dict[str, Any]:
    """Fetch and extract visible text from a URL under strict bounds and proxy routing."""
    clean_url = safe_url(url)
    if not clean_url:
        return {"url": url, "title": "", "content": "", "status": 400, "error": "Invalid or blocked URL"}

    import requests
    proxy_url = proxy or os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY") or DEFAULT_EGRESS_PROXY
    proxies = {"http": proxy_url, "https": proxy_url}

    session = requests.Session()
    current = clean_url
    response = None

    for _ in range(MAX_REDIRECTS + 1):
        try:
            response = session.get(
                current,
                headers={"User-Agent": USER_AGENT},
                timeout=20,
                allow_redirects=False,
                stream=True,
                proxies=proxies,
            )
        except Exception as exc:
            return {"url": current, "title": "", "content": "", "status": 500, "error": f"Fetch connection error: {exc}"}

        if response.is_redirect or response.is_permanent_redirect:
            loc = response.headers.get("location")
            if not loc:
                break
            target = safe_url(urljoin(current, loc))
            if not target:
                return {"url": current, "title": "", "content": "", "status": 403, "error": "Redirect to disallowed URL"}
            current = target
            continue
        break

    if response is None:
        return {"url": current, "title": "", "content": "", "status": 504, "error": "No response received"}

    status = response.status_code
    if status >= 400:
        return {"url": current, "title": "", "content": "", "status": status, "error": f"HTTP {status}"}

    body = bytearray()
    for chunk in response.iter_content(64 * 1024):
        body.extend(chunk)
        if len(body) >= MAX_BODY_BYTES:
            del body[MAX_BODY_BYTES:]
            break

    encoding = response.encoding or "utf-8"
    raw_text = bytes(body).decode(encoding, errors="replace")

    title = ""
    match = re.search(r"<title[^>]*>(.*?)</title>", raw_text, re.I | re.S)
    if match:
        title = re.sub(r"\s+", " ", match.group(1)).strip()

    parser = _VisibleTextParser()
    parser.feed(raw_text)
    text = parser.text()

    if len(text) > char_limit:
        head = char_limit * 2 // 3
        tail = char_limit - head
        text = text[:head] + "\n\n[...TRUNCATED FOR LENGTH...]\n\n" + text[-tail:]

    return {
        "url": current,
        "title": title,
        "content": text,
        "status": status,
        "bytes_read": len(body),
        "error": "",
    }


def execute_browser_extract(url: str, selector: str = "body") -> dict[str, Any]:
    """Extract rendered content via headless Chrome CDP daemon.
    
    Uses CDP (Chrome DevTools Protocol) over WebSocket to navigate and extract
    rendered DOM content. Falls back to HTTP fetch if CDP is unavailable or fails.
    """
    # Check optional dependencies first
    if not WEBSOCKETS_AVAILABLE:
        return {
            "url": url,
            "title": "",
            "content": "",
            "status": 0,
            "bytes_read": 0,
            "error": "websockets library not installed - browser extraction unavailable",
        }
    if not BS4_AVAILABLE:
        return {
            "url": url,
            "title": "",
            "content": "",
            "status": 0,
            "bytes_read": 0,
            "error": "beautifulsoup4 library not installed - browser extraction unavailable",
        }

    # Check if CDP daemon is ready
    if not browser_daemon.is_cdp_ready():
        # Fall back to HTTP fetch when CDP is not available
        return execute_web_fetch(url)

    # Get the WebSocket debugger URL
    import urllib.request
    try:
        ver_url = "http://127.0.0.1:9222/json/version"
        with urllib.request.urlopen(ver_url, timeout=2.0) as resp:
            ver_data = json.loads(resp.read().decode("utf-8"))
            ws_url = ver_data.get("webSocketDebuggerUrl")
            if not ws_url:
                return execute_web_fetch(url)
    except Exception as e:
        return execute_web_fetch(url)

    # Connect via WebSocket and execute CDP commands
    async def _cdp_extract() -> dict[str, Any]:
        async with websockets.connect(ws_url) as ws:
            # Enable Runtime domain
            await ws.send(json.dumps({"id": 1, "method": "Runtime.enable"}))
            await ws.recv()  # ack
            
            # Enable Page domain
            await ws.send(json.dumps({"id": 2, "method": "Page.enable"}))
            await ws.recv()  # ack
            
            # Navigate to URL
            await ws.send(json.dumps({
                "id": 3,
                "method": "Page.navigate",
                "params": {"url": url}
            }))
            
            # Wait for navigation to complete
            while True:
                msg = await ws.recv()
                data = json.loads(msg)
                if data.get("method") == "Page.loadEventFired":
                    break
                if data.get("id") == 3 and "error" in data:
                    raise RuntimeError(f"Navigation failed: {data['error']}")
            
            # Get document node
            await ws.send(json.dumps({
                "id": 4,
                "method": "DOM.getDocument",
                "params": {"depth": -1, "pierce": True}
            }))
            msg = await ws.recv()
            data = json.loads(msg)
            if "error" in data:
                raise RuntimeError(f"DOM.getDocument failed: {data['error']}")
            root_node_id = data["result"]["root"]["nodeId"]
            
            # Query selector
            await ws.send(json.dumps({
                "id": 5,
                "method": "DOM.querySelector",
                "params": {"nodeId": root_node_id, "selector": selector}
            }))
            msg = await ws.recv()
            data = json.loads(msg)
            if "error" in data or data.get("result", {}).get("nodeId") is None:
                # Selector not found, fall back to body
                selector = "body"
                await ws.send(json.dumps({
                    "id": 5,
                    "method": "DOM.querySelector",
                    "params": {"nodeId": root_node_id, "selector": selector}
                }))
                msg = await ws.recv()
                data = json.loads(msg)
            
            node_id = data.get("result", {}).get("nodeId")
            if node_id is None:
                raise RuntimeError(f"Selector '{selector}' not found")
            
            # Get outer HTML of selected node
            await ws.send(json.dumps({
                "id": 6,
                "method": "DOM.getOuterHTML",
                "params": {"nodeId": node_id}
            }))
            msg = await ws.recv()
            data = json.loads(msg)
            if "error" in data:
                raise RuntimeError(f"DOM.getOuterHTML failed: {data['error']}")
            outer_html = data["result"]["outerHTML"]
            
            # Also get page title
            await ws.send(json.dumps({"id": 7, "method": "Runtime.evaluate", "params": {"expression": "document.title"}}))
            msg = await ws.recv()
            data = json.loads(msg)
            title = data.get("result", {}).get("result", {}).get("value", "")
            
            # Extract text content from HTML (simple extraction)
            soup = BeautifulSoup(outer_html, "html.parser")
            text = soup.get_text(separator="\n", strip=True)
            
            return {
                "url": url,
                "title": title,
                "content": text,
                "status": 200,
                "bytes_read": len(text),
                "error": "",
            }

    # Run async function
    try:
        return asyncio.run(_cdp_extract())
    except Exception as e:
        # Fall back to HTTP fetch on any CDP error
        return execute_web_fetch(url)


NATIVE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web via the egress proxy for keywords, competitors, market data, or facts.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query string."},
                    "limit": {"type": "integer", "description": "Max results to return (1-10, default 5)."},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_fetch",
            "description": "Fetch and extract readable text content from an HTTP/HTTPS URL.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The URL to fetch."},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_extract",
            "description": "Render a dynamic JavaScript page or SPA and extract DOM text.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The URL to render."},
                    "selector": {"type": "string", "description": "CSS selector to extract (default 'body')."},
                },
                "required": ["url"],
            },
        },
    },
]


def dispatch_tool_call(name: str, args: dict[str, Any]) -> str:
    """Route tool invocation to appropriate native implementation."""
    if name == "web_search":
        q = args.get("query", "")
        limit = args.get("limit", 5)
        res = execute_web_search(q, limit=limit)
        return json.dumps(res, indent=2)
    elif name == "web_fetch":
        u = args.get("url", "")
        res = execute_web_fetch(u)
        return json.dumps(res, indent=2)
    elif name == "browser_extract":
        u = args.get("url", "")
        s = args.get("selector", "body")
        res = execute_browser_extract(u, selector=s)
        return json.dumps(res, indent=2)
    else:
        return json.dumps({"error": f"Unknown tool: {name}"})


def distill_research_skill(
    task_id: int,
    mission_id: str,
    deliverable: str,
    root: Path | str | None = None,
) -> Path | None:
    """Distill successful research technique note into skills_analyst/_candidates/ under H7 sanitization."""
    if root is None:
        root = ROOT
    root_path = Path(root)
    candidates_dir = root_path / "skills_analyst" / "_candidates"
    candidates_dir.mkdir(parents=True, exist_ok=True)

    # Apply H7 injection filtering: strip literal URLs, enforce no fatal shell tokens
    cleaned = promote._NOTE_URL_RE.sub("[VERIFIED_SOURCE]", deliverable[:500])
    for pattern, name in promote._NOTE_FATAL:
        if pattern.search(cleaned):
            return None  # Discard if code injection or shell constructs present

    note_content = (
        f"# Research Lesson: {mission_id} (Task {task_id})\n\n"
        f"Date: {time.strftime('%Y-%m-%d')}\n\n"
        f"Key grounded observation:\n{cleaned.strip()}\n"
    )
    note_path = candidates_dir / f"task{task_id}_{mission_id}_skill.md"
    note_path.write_text(note_content, encoding="utf-8")
    return note_path


def load_active_research_skills(
    root: Path | str | None = None,
    max_skills: int = 3,
    mission_id: str | None = None,
) -> str:
    """Load ONLY operator-approved research skills from skills_analyst/<mission>/.
    
    This is the HUMAN-GATED promotion path — only skills that have been
    operator-approved via `promote.py approve` are loaded. Unapproved candidates
    in _candidates/ are NEVER loaded here.
    
    Args:
        mission_id: If provided, only load skills for that specific mission.
                   If None, load from all mission directories.
    """
    if root is None:
        root = ROOT
    root_path = Path(root)
    skills: list[str] = []

    skills_dir = root_path / "skills_analyst"
    if not skills_dir.is_dir():
        return ""

    # Determine which mission directories to scan
    if mission_id:
        mission_dirs = [skills_dir / mission_id]
    else:
        mission_dirs = [d for d in skills_dir.iterdir() 
                       if d.is_dir() and not d.name.startswith("_")]

    for mission_dir in mission_dirs:
        if not mission_dir.is_dir():
            continue
        # Load all approved skill files for this mission
        for p in sorted(mission_dir.glob("*.md"), reverse=True):
            try:
                txt = p.read_text(encoding="utf-8", errors="replace")
                # Re-apply H7 sanitization at load time (defense in depth)
                cleaned = promote._NOTE_URL_RE.sub("[VERIFIED_SOURCE]", txt)
                fatal = False
                for pattern, _ in promote._NOTE_FATAL:
                    if pattern.search(cleaned):
                        fatal = True
                        break
                if not fatal:
                    for line in cleaned.splitlines():
                        line_s = line.strip()
                        if line_s and not line_s.startswith("#") and not line_s.startswith("Date:") and not line_s.startswith("Key grounded"):
                            skills.append(f"[{mission_dir.name}] {line_s[:200]}")
                            break
            except Exception:
                pass
            if len(skills) >= max_skills:
                break
        if len(skills) >= max_skills:
            break

    if not skills:
        return ""

    tactics = "\n".join(f"- {s}" for s in skills)
    return f"\n\nSelf-Improving Research Tactics (Operator-Approved Skills):\n{tactics}"


def call_provider_with_tools(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    model_cfg: dict[str, Any],
    timeout: float = 300,
) -> dict[str, Any]:
    """Execute one model turn with tool-calling schema via provider endpoint.

    Fails closed immediately if pause_engaged() is True.
    """
    if pause_engaged():
        raise RuntimeError("model execution refused: global ESTOP is engaged")

    provider = str(model_cfg.get("provider", "ollama")).lower()
    model = str(model_cfg.get("model", ""))

    if provider == "ollama":
        endpoint = model_cfg.get("endpoint") or "http://127.0.0.1:11434/api/chat"
        body = {
            "model": model,
            "messages": messages,
            "tools": tools,
            "stream": False,
        }
        req = urllib.request.Request(
            endpoint,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
            msg = payload.get("message", {})
            return {
                "message": msg,
                "input_tokens": int(payload.get("prompt_eval_count") or 0),
                "output_tokens": int(payload.get("eval_count") or 0),
            }

    elif provider in ("byteplus_coding", "openai"):
        if provider == "byteplus_coding":
            base = model_cfg.get("endpoint") or "https://ark.ap-southeast.bytepluses.com/api/coding/v3"
            ref = model_cfg.get("authentication_reference") or "env:ARK_API_KEY"
        else:
            base = model_cfg.get("endpoint") or "https://api.openai.com/v1"
            ref = model_cfg.get("authentication_reference") or "env:OPENAI_API_KEY"

        base_endpoint = base.rstrip("/") + "/chat/completions"
        import provider_chat
        api_key = provider_chat.authentication_env_from_config({"authentication_reference": ref}).get(
            ref.split(":")[-1] if ":" in ref else ref, ""
        ) or os.environ.get(ref.split(":")[-1] if ":" in ref else ref, "")

        body = {
            "model": model,
            "messages": messages,
            "tools": tools,
            "stream": False,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        req = urllib.request.Request(
            base_endpoint,
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
        )
        with urllib.request.urlopen(req, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
            choice = payload["choices"][0]
            msg = choice["message"]
            usage = payload.get("usage", {})
            return {
                "message": msg,
                "input_tokens": int(usage.get("prompt_tokens") or 0),
                "output_tokens": int(usage.get("completion_tokens") or 0),
            }
    else:
        raise ValueError(f"Unsupported provider for native tool loop: {provider}")


def run_native_research_turn(
    prompt: str,
    model_cfg: dict[str, Any],
    usage_path: Path | str | None = None,
    *,
    task_id: int | None = None,
    client_id: str | None = None,
    mission_id: str | None = None,
    notebook_path: Path | str | None = None,
    max_turns: int = 8,
    custom_caller: Callable[[list[dict[str, Any]], list[dict[str, Any]]], dict[str, Any]] | None = None,
    root: Path | str | None = None,
    enforce_active_research: bool = False,
) -> tuple[str, dict[str, Any]]:
    """Execute one autonomous research turn natively without external CLI dependencies.

    Returns:
        (deliverable_text, usage_dict)
    """
    if pause_engaged():
        raise RuntimeError("model execution refused: global ESTOP is engaged")

    notebook = None
    if notebook_path:
        nb_p = Path(notebook_path)
        notebook = Notebook.load(nb_p) or Notebook()

    direction_clause = ""
    if notebook and notebook.attempts_seen:
        direction_clause = f"\n\nPrior Research Memory:\n{notebook.direction_block()}"

    skills_clause = load_active_research_skills(root, mission_id=mission_id)

    system_prompt = (
        "You are an autonomous research analyst. You gather verified, grounded facts using "
        "the provided web search, web fetch, and browser tools. Every factual claim, statistic, "
        "or quote MUST cite the exact URL retrieved. Do not invent facts, metrics, or sources."
        + direction_clause
        + skills_clause
    )

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt},
    ]

    total_in = 0
    total_out = 0
    api_calls = 0
    tool_calls_executed = 0
    deliverable = ""
    fetched_evidence: list[dict[str, Any]] = []

    for turn_idx in range(max_turns):
        api_calls += 1
        if custom_caller is not None:
            # Deterministic/mock caller for tests & offline suites
            resp = custom_caller(messages, NATIVE_TOOLS)
        else:
            # Live caller via provider transport
            resp = call_provider_with_tools(messages, NATIVE_TOOLS, model_cfg)

        in_tok = int(resp.get("input_tokens", 0))
        out_tok = int(resp.get("output_tokens", 0))
        total_in += in_tok
        total_out += out_tok

        msg = resp.get("message", {})
        tool_calls = msg.get("tool_calls", [])

        if not tool_calls:
            if enforce_active_research and tool_calls_executed == 0 and turn_idx == 0:
                # Model attempted zero-tool completion under mandatory active research mandate:
                # Re-prompt model to execute retrieval tools before drafting deliverable.
                messages.append(msg)
                messages.append({
                    "role": "user",
                    "content": (
                        "MANDATORY REQUIREMENT: You must NOT answer immediately from internal memory without conducting active research. "
                        "You must invoke the web_search or web_fetch tools to discover and verify external "
                        "sources before drafting your deliverable. Execute your search tool call now."
                    )
                })
                continue
            # Final completion text reached
            deliverable = str(msg.get("content") or "")
            break

        messages.append(msg)
        for tc in tool_calls:
            tool_calls_executed += 1
            func = tc.get("function", {})
            name = func.get("name", "")
            raw_args = func.get("arguments", {})
            if isinstance(raw_args, str):
                try:
                    args = json.loads(raw_args)
                except Exception:
                    args = {}
            else:
                args = raw_args

            result_str = dispatch_tool_call(name, args)
            call_id = tc.get("id", f"call_{turn_idx}_{tool_calls_executed}")
            messages.append({
                "role": "tool",
                "tool_call_id": call_id,
                "name": name,
                "content": result_str,
            })

            # Record fetched source into notebook evidence
            if name in ("web_fetch", "browser_extract") and "url" in args:
                try:
                    res_data = json.loads(result_str)
                    st = res_data.get("status", 200)
                    fetched_evidence.append({
                        "url": args["url"],
                        "http_status": st,
                        "classification": "OK" if st < 400 else "ERROR",
                        "reachable_on_host": st < 400,
                        "worker_policy_permitted": True,
                    })
                except Exception:
                    pass

    usage = {
        "input_tokens": total_in,
        "output_tokens": total_out,
        "total_tokens": total_in + total_out,
        "api_calls": api_calls,
        "tool_calls_executed": tool_calls_executed,
    }

    if usage_path:
        up = Path(usage_path)
        up.parent.mkdir(parents=True, exist_ok=True)
        up.write_text(json.dumps(usage, indent=2) + "\n", encoding="utf-8")

    # Update research notebook if path provided
    if notebook and notebook_path and fetched_evidence:
        notebook.merge_preflight(
            evidence=fetched_evidence,
            dead_urls=[e["url"] for e in fetched_evidence if e.get("http_status", 200) >= 400],
            schema_issues=[],
            task_id=task_id or 0,
            attempt=1,
        )
        notebook.save(Path(notebook_path))

    return deliverable, usage
