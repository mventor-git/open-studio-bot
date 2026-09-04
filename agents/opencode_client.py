"""opencode serve client (T4).

Talks to a running `opencode serve` over HTTP. Resilient by design:

- repeating tries on connection errors (server restarting / not yet up),
  exponential backoff, interrupt-aware (stops if the job is cancelled)
- create session -> send prompt -> poll messages until the assistant
  message carries a `finish` (stop|error) -> return its text

The montage agent gets a fresh session per job, so the prompt must carry ALL
context (video path, template, prompt, output expectations), and the session
location is pinned to the Open Studio Bot repo so it reads the pipeline skills.
"""
from __future__ import annotations

import time
from typing import Any, Callable, Optional

import httpx

from config import config

SERVE_BASE = config.opencode_server_url

# --- resilient HTTP ---------------------------------------------------------

def _try_request(
    method: str,
    path: str,
    *,
    json: Optional[dict] = None,
    params: Optional[dict] = None,
    timeout: float = 15.0,
    interrupt: Optional[Callable[[], bool]] = None,
    base_retry: float = 2.0,
    max_backoff: float = 30.0,
) -> httpx.Response:
    """Retry forever (interrupt-aware) on transport errors; back off between tries.

    Only retries *connection* failures — a 4xx/5xx response is returned as-is
    (it is a real answer, not a disconnect).
    """
    delay = base_retry
    url = f"{SERVE_BASE}{path}"
    while True:
        if interrupt is not None and interrupt():
            raise InterruptedError("job cancelled while waiting for opencode serve")
        try:
            return httpx.request(method, url, json=json, params=params, timeout=timeout)
        except (httpx.ConnectError, httpx.ReadError, httpx.RemoteProtocolError, httpx.TimeoutException) as exc:
            if interrupt is not None and interrupt():
                raise InterruptedError("job cancelled while waiting for opencode serve")
            print(f"  serve unreachable ({type(exc).__name__}); retrying in {delay:.0f}s ...")
            time.sleep(delay)
            delay = min(delay * 2, max_backoff)


# --- session lifecycle ------------------------------------------------------

def _map_message(msg: dict[str, Any]) -> dict[str, Any]:
    """Normalize an assistant message to {finish, text, error}."""
    finish = msg.get("finish", "")
    text = ""
    for part in msg.get("content", []) or []:
        if part.get("type") == "text":
            text += part.get("text", "")
    err = msg.get("error") or {}
    return {"finish": finish, "text": text, "error": err.get("message", "") if err else ""}


def wait_for_completion(
    session_id: str,
    *,
    interrupt: Optional[Callable[[], bool]] = None,
    poll_interval: float = 4.0,
    hard_timeout: float = 1800.0,
) -> dict[str, Any]:
    """Poll /message until an assistant message reaches a terminal finish."""
    deadline = time.time() + hard_timeout
    while True:
        if interrupt is not None and interrupt():
            raise InterruptedError("job cancelled while waiting for render")
        resp = _try_request("GET", f"/api/session/{session_id}/message", interrupt=interrupt)
        if resp.status_code == 200:
            for msg in reversed(resp.json().get("data", [])):
                if msg.get("type") == "assistant":
                    norm = _map_message(msg)
                    if norm["finish"] in ("stop", "error", "aborted"):
                        return norm
        if time.time() > deadline:
            raise TimeoutError(f"render did not finish within {hard_timeout:.0f}s")
        time.sleep(poll_interval)


def run_job(
    prompt: str,
    *,
    agent: str = "mventor",
    model: str = "Claude-Free",
    location_dir: Optional[str] = None,
    interrupt: Optional[Callable[[], bool]] = None,
    hard_timeout: float = 1800.0,
) -> dict[str, Any]:
    """Create a session, send the prompt, wait, return {text, session_id, finish, error}."""
    # provider id and model id are both "Claude-Free" in opencode's config
    body = {"agent": agent, "model": {"providerID": model, "id": model}}
    if location_dir:
        body["location"] = {"directory": location_dir}

    resp = _try_request("POST", "/api/session", json=body, interrupt=interrupt)
    if resp.status_code != 200:
        return {"text": "", "session_id": "", "finish": "error", "error": f"session create {resp.status_code}: {resp.text[:300]}"}
    session_id = resp.json()["data"]["id"]

    resp = _try_request(
        "POST", f"/api/session/{session_id}/prompt",
        json={"prompt": {"text": prompt}}, interrupt=interrupt,
    )
    if resp.status_code != 200:
        return {"text": "", "session_id": session_id, "finish": "error", "error": f"prompt {resp.status_code}: {resp.text[:300]}"}

    try:
        norm = wait_for_completion(session_id, interrupt=interrupt, hard_timeout=hard_timeout)
    except InterruptedError as exc:
        return {"text": "", "session_id": session_id, "finish": "aborted", "error": str(exc)}
    except TimeoutError as exc:
        return {"text": "", "session_id": session_id, "finish": "error", "error": str(exc)}

    return {"text": norm["text"], "session_id": session_id, "finish": norm["finish"], "error": norm["error"]}


def abort_session(session_id: str) -> None:
    """Best-effort abort (used by /interrupt)."""
    try:
        httpx.post(f"{SERVE_BASE}/session/{session_id}/abort", timeout=10)
    except Exception:
        pass
