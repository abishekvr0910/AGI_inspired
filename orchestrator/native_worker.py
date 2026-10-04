"""Native Agentic Research Worker for AGI_like Harness.

Pure Python, zero-external-bloat agentic research loop that executes turns
using our own tools (search, fetch, CDP browser) without any dependency on
external CLI frameworks. Directly integrates with the research notebook and
skill promotion memory loop.

Architecture & Containment Note:
Native Worker runs in-process within the Python controller runtime. It does NOT
spawn as an OS child process with a Win32 Job Object or Restricted Token (unlike
Hermes, which is launched via worker_sandbox.py in a dedicated subprocess).
Instead, its browser operations delegate out-of-process to the host-managed
browser daemon (browser_daemon.py) over loopback CDP (127.0.0.1:9222).

Zero-spend: Never executes write or mutate API calls to ad platforms.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser
import asyncio
import contextlib
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


BOT_BLOCK_SIGNATURES = (
    "just a moment...",
    "attention required! | cloudflare",
    "cf-browser-verification",
    "checking your browser before accessing",
    "please verify you are a human",
    "verify you are human",
    "access denied | cloudflare",
    "security check to access",
    "enable javascript and cookies to continue",
    "blocked by perimeterx",
    "bot detection",
    "request blocked",
    "automated access",
    "ddos-guard",
)


def detect_access_block(status: int, text: str = "", title: str = "") -> tuple[bool, str]:
    """Detect HTTP access errors or anti-bot challenge signatures."""
    if status in (403, 429, 503):
        return True, f"HTTP {status}"
    if status >= 400:
        return True, f"HTTP {status}"
    sample = (title + " " + text[:1500]).lower()
    for sig in BOT_BLOCK_SIGNATURES:
        if sig in sample:
            return True, f"bot_challenge_detected ({sig})"
    return False, ""


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
    is_blocked, block_reason = detect_access_block(status)
    if is_blocked:
        return {
            "url": current,
            "title": "",
            "content": "",
            "status": status,
            "bytes_read": 0,
            "error": f"Access blocked: {block_reason}",
            "blocked": True,
            "pivot_guidance": (
                f"Target URL {current} returned {block_reason}. "
                "DO NOT attempt to re-fetch this exact URL. Formulate alternative web_search queries "
                "targeting third-party reviews, news coverage, directory profiles (G2, Capterra, GitHub, SEC filings), "
                "or competitor comparisons."
            ),
        }

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

    is_bot, bot_reason = detect_access_block(status, text, title)
    if is_bot:
        return {
            "url": current,
            "title": title,
            "content": "",
            "status": 403,
            "bytes_read": len(body),
            "error": f"Access blocked: {bot_reason}",
            "blocked": True,
            "pivot_guidance": (
                f"Target URL {current} presented an anti-bot verification challenge ({bot_reason}). "
                "DO NOT attempt to re-fetch this exact URL. Formulate alternative web_search queries "
                "targeting third-party reviews, news coverage, directory profiles (G2, Capterra, GitHub, SEC filings), "
                "or competitor comparisons."
            ),
        }

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
        "blocked": False,
    }


def _acquire_cdp_page_target(host: str, port: int, timeout: float = 2.0) -> tuple[str, str]:
    """Acquire an isolated CDP Page target, preferring a fresh tab via PUT /json/new.

    Returns:
        (target_id, ws_url)
    Raises:
        RuntimeError if no page target can be acquired.
    """
    # 1. Try PUT /json/new to create a dedicated isolated target
    try:
        req = urllib.request.Request(f"http://{host}:{port}/json/new?about:blank", method="PUT")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            tid = data.get("id")
            ws = data.get("webSocketDebuggerUrl")
            if tid and ws:
                return tid, ws
    except Exception:
        pass

    # 2. Fallback to GET /json/list for existing page targets
    try:
        req = urllib.request.Request(f"http://{host}:{port}/json/list")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            targets = json.loads(resp.read().decode("utf-8"))
            for t in targets:
                if t.get("type") == "page" and t.get("webSocketDebuggerUrl"):
                    return t.get("id", ""), t["webSocketDebuggerUrl"]
    except Exception as exc:
        raise RuntimeError(f"Failed to query CDP targets at http://{host}:{port}: {exc}") from exc

    raise RuntimeError(f"No available Page target found on CDP endpoint http://{host}:{port}")


def _close_cdp_page_target(host: str, port: int, target_id: str, timeout: float = 1.5) -> None:
    """Close an isolated CDP Page target tab via PUT /json/close/<id>."""
    if not target_id:
        return
    try:
        req = urllib.request.Request(f"http://{host}:{port}/json/close/{target_id}", method="PUT")
        with urllib.request.urlopen(req, timeout=timeout):
            pass
    except Exception:
        pass


async def _async_cdp_extract(
    ws_url: str,
    url: str,
    selector: str = "body",
    timeout: float = 15.0,
) -> dict[str, Any]:
    """Perform CDP commands over WebSocket with strict request-ID routing and bounded timeouts."""
    async with websockets.connect(ws_url, ping_interval=None) as ws:
        next_cmd_id = 1
        pending: dict[int, asyncio.Future] = {}
        event_queue: asyncio.Queue = asyncio.Queue()

        async def send_cmd(method: str, params: dict | None = None) -> dict:
            nonlocal next_cmd_id
            cid = next_cmd_id
            next_cmd_id += 1
            fut = asyncio.get_running_loop().create_future()
            pending[cid] = fut
            await ws.send(json.dumps({"id": cid, "method": method, "params": params or {}}))
            return await fut

        async def reader_loop():
            while True:
                try:
                    raw = await ws.recv()
                except Exception:
                    break
                try:
                    msg = json.loads(raw)
                except Exception:
                    continue
                if "id" in msg and msg["id"] in pending:
                    fut = pending.pop(msg["id"])
                    if not fut.done():
                        fut.set_result(msg)
                elif "method" in msg:
                    await event_queue.put(msg)

        reader_task = asyncio.create_task(reader_loop())
        try:
            # 1. Enable Page and Runtime domains
            p_res = await send_cmd("Page.enable")
            if "error" in p_res:
                raise RuntimeError(f"Page.enable failed: {p_res['error']}")
            r_res = await send_cmd("Runtime.enable")
            if "error" in r_res:
                raise RuntimeError(f"Runtime.enable failed: {r_res['error']}")

            # 2. Navigate
            nav_res = await send_cmd("Page.navigate", {"url": url})
            if "error" in nav_res:
                raise RuntimeError(f"Page.navigate failed: {nav_res['error']}")
            nav_result = nav_res.get("result", {})
            if nav_result.get("errorText"):
                raise RuntimeError(f"Navigation error: {nav_result['errorText']}")

            # 3. Wait for load event or readyState
            nav_deadline = time.monotonic() + min(timeout, 8.0)
            while time.monotonic() < nav_deadline:
                try:
                    event = await asyncio.wait_for(event_queue.get(), timeout=0.4)
                    if event.get("method") in ("Page.loadEventFired", "Page.domContentEventFired"):
                        break
                except asyncio.TimeoutError:
                    try:
                        doc_state = await send_cmd("Runtime.evaluate", {
                            "expression": "document.readyState",
                            "returnByValue": True,
                        })
                        st_val = doc_state.get("result", {}).get("result", {}).get("value")
                        if st_val in ("interactive", "complete"):
                            break
                    except Exception:
                        pass

            # 4. Small settling delay for scripts / dynamic timers
            await asyncio.sleep(0.15)

            # 5. Extract selector and DOM text via Runtime.evaluate
            eval_expr = (
                f"(() => {{\n"
                f"    const sel = {json.dumps(selector or 'body')};\n"
                f"    const el = document.querySelector(sel);\n"
                f"    if (!el) {{\n"
                f"        return {{\n"
                f"            found: false,\n"
                f"            title: document.title || '',\n"
                f"            error: 'Selector \"' + sel + '\" not found in rendered DOM'\n"
                f"        }};\n"
                f"    }}\n"
                f"    const text = (el.innerText || el.textContent || '').trim();\n"
                f"    return {{\n"
                f"        found: true,\n"
                f"        text: text,\n"
                f"        title: document.title || '',\n"
                f"        html: el.outerHTML || ''\n"
                f"    }};\n"
                f"}})()"
            )
            eval_res = await send_cmd("Runtime.evaluate", {
                "expression": eval_expr,
                "returnByValue": True,
            })
            if "error" in eval_res:
                raise RuntimeError(f"Runtime.evaluate failed: {eval_res['error']}")

            res_val = eval_res.get("result", {}).get("result", {}).get("value")
            if not isinstance(res_val, dict):
                raise RuntimeError(f"Unexpected evaluate result: {res_val}")
            return res_val
        finally:
            reader_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await reader_task


def execute_browser_extract(
    url: str,
    selector: str = "body",
    host: str | None = None,
    port: int | None = None,
    timeout: float = 15.0,
    char_limit: int = DEFAULT_CHAR_LIMIT,
    check_estop: bool = True,
) -> dict[str, Any]:
    """Extract rendered content via headless Chrome CDP daemon.

    Uses Chrome DevTools Protocol (CDP) over WebSocket to navigate, execute JavaScript,
    and extract rendered DOM content.

    Fail-closed guarantees:
    - Never falls back silently to HTTP fetch; reports honest failure if CDP is offline.
    - Rejects execution if ESTOP is engaged (unless explicitly bypassed for offline fixtures).
    - Closes page target tab after extraction to prevent session residue.
    """
    if check_estop and pause_engaged():
        return {
            "url": url,
            "title": "",
            "content": "",
            "status": 0,
            "bytes_read": 0,
            "error": "Browser extraction refused: global ESTOP is engaged",
            "is_browser_rendered": False,
            "blocked": False,
        }

    # Check optional dependencies first
    if not WEBSOCKETS_AVAILABLE:
        return {
            "url": url,
            "title": "",
            "content": "",
            "status": 0,
            "bytes_read": 0,
            "error": "websockets library not installed - browser extraction unavailable",
            "is_browser_rendered": False,
            "blocked": False,
        }
    if not BS4_AVAILABLE:
        return {
            "url": url,
            "title": "",
            "content": "",
            "status": 0,
            "bytes_read": 0,
            "error": "beautifulsoup4 library not installed - browser extraction unavailable",
            "is_browser_rendered": False,
            "blocked": False,
        }

    # Resolve host and port
    if host is None or port is None:
        cdp_env = os.environ.get("BROWSER_CDP_URL", "")
        if cdp_env:
            try:
                parsed = urlsplit(cdp_env)
                host = host or parsed.hostname or browser_daemon.DEFAULT_CDP_HOST
                port = port or parsed.port or browser_daemon.DEFAULT_CDP_PORT
            except Exception:
                pass
    host = host or browser_daemon.DEFAULT_CDP_HOST
    port = port or browser_daemon.DEFAULT_CDP_PORT

    # Check if CDP daemon is ready
    if not browser_daemon.is_cdp_ready(host=host, port=port, timeout=1.0):
        return {
            "url": url,
            "title": "",
            "content": "",
            "status": 0,
            "bytes_read": 0,
            "error": f"CDP browser daemon is offline or not responding at http://{host}:{port}",
            "is_browser_rendered": False,
            "blocked": False,
        }

    target_id = None
    try:
        target_id, ws_url = _acquire_cdp_page_target(host=host, port=port)
    except Exception as exc:
        return {
            "url": url,
            "title": "",
            "content": "",
            "status": 0,
            "bytes_read": 0,
            "error": f"Failed to acquire CDP page target: {exc}",
            "is_browser_rendered": False,
            "blocked": False,
        }

    try:
        res_data = asyncio.run(asyncio.wait_for(
            _async_cdp_extract(ws_url=ws_url, url=url, selector=selector, timeout=timeout),
            timeout=timeout + 2.0,
        ))
    except asyncio.TimeoutError:
        return {
            "url": url,
            "title": "",
            "content": "",
            "status": 504,
            "bytes_read": 0,
            "error": f"Browser extraction timed out after {timeout:.1f}s",
            "is_browser_rendered": False,
            "blocked": False,
        }
    except Exception as exc:
        return {
            "url": url,
            "title": "",
            "content": "",
            "status": 0,
            "bytes_read": 0,
            "error": f"Browser extraction failed: {exc}",
            "is_browser_rendered": False,
            "blocked": False,
        }
    finally:
        if target_id:
            _close_cdp_page_target(host=host, port=port, target_id=target_id)

    if not res_data.get("found"):
        return {
            "url": url,
            "title": res_data.get("title", ""),
            "content": "",
            "status": 404,
            "bytes_read": 0,
            "error": res_data.get("error", f"Selector '{selector}' not found in rendered DOM"),
            "is_browser_rendered": True,
            "blocked": False,
        }

    text = res_data.get("text", "")
    title = res_data.get("title", "")

    is_bot, bot_reason = detect_access_block(200, text, title)
    if is_bot:
        return {
            "url": url,
            "title": title,
            "content": "",
            "status": 403,
            "bytes_read": len(text.encode("utf-8")),
            "error": f"Access blocked: {bot_reason}",
            "blocked": True,
            "is_browser_rendered": True,
            "pivot_guidance": (
                f"Target URL {url} presented an anti-bot verification challenge ({bot_reason}). "
                "DO NOT attempt to re-fetch this exact URL. Formulate alternative web_search queries "
                "targeting third-party reviews, news coverage, directory profiles (G2, Capterra, GitHub, SEC filings), "
                "or competitor comparisons."
            ),
        }

    if len(text) > char_limit:
        head = char_limit * 2 // 3
        tail = char_limit - head
        text = text[:head] + "\n\n[...TRUNCATED FOR LENGTH...]\n\n" + text[-tail:]

    return {
        "url": url,
        "title": title,
        "content": text,
        "status": 200,
        "bytes_read": len(text.encode("utf-8")),
        "error": "",
        "is_browser_rendered": True,
        "blocked": False,
    }


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
            failed_fetches = [e for e in fetched_evidence if e.get("classification") != "OK"]
            verified_fetches = [e for e in fetched_evidence if e.get("classification") == "OK"]

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
            elif enforce_active_research and failed_fetches and not verified_fetches and turn_idx < max_turns - 1:
                # Model attempted tool fetches, but all were blocked or failed.
                # Do NOT allow shallow one-shot completion; force model to re-plan alternative queries.
                blocked_urls = ", ".join(e["url"] for e in failed_fetches)
                messages.append(msg)
                messages.append({
                    "role": "user",
                    "content": (
                        f"INSUFFICIENT VERIFIED EVIDENCE: All attempted URL fetches failed or were blocked ({blocked_urls}). "
                        "You must NOT draft a deliverable without verified evidence. "
                        "DO NOT retry the blocked URLs. Formulate an alternative web_search query targeting third-party reviews, "
                        "news coverage, directory profiles, or competitor comparisons, then fetch those working sources. "
                        "Execute your alternative search tool call now."
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
                    st = res_data.get("status", 0)
                    content = str(res_data.get("content") or "").strip()
                    is_blocked = bool(res_data.get("blocked"))
                    has_error = bool(res_data.get("error"))
                    # Verified evidence requires: valid 2xx/3xx HTTP status, not blocked, no error, and non-empty content
                    is_ok = (200 <= st < 400) and not is_blocked and not has_error and bool(content)
                    is_err = not is_ok
                    fetched_evidence.append({
                        "url": args["url"],
                        "http_status": 403 if is_blocked else (st if st > 0 else 500),
                        "classification": "OK" if is_ok else ("BLOCKED" if is_blocked else "ERROR"),
                        "reachable_on_host": is_ok,
                        "worker_policy_permitted": True,
                        "content_length": len(content),
                    })
                    if is_err:
                        import policy_manager
                        r_dir = Path(usage_path).parent if usage_path else (Path(notebook_path).parent if notebook_path else None)
                        target_host = urlsplit(args["url"]).hostname or ""
                        if target_host:
                            policy_manager.record_candidate(
                                host=target_host,
                                url=args["url"],
                                task_id=task_id,
                                attempt=1,
                                runs_dir=r_dir,
                            )
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
        ok_evidence = [e for e in fetched_evidence if e.get("classification") == "OK"]
        dead_evidence = [
            {"url": e["url"], "http_status": e.get("http_status", 400)}
            for e in fetched_evidence
            if e.get("classification") != "OK"
        ]
        notebook.merge_preflight(
            evidence=ok_evidence,
            dead_urls=dead_evidence,
            schema_issues=[],
            task_id=task_id or 0,
            attempt=1,
        )
        notebook.save(Path(notebook_path))

    return deliverable, usage
