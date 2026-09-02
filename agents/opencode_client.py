"""opencode serve client (T4).

Contract: create session -> POST prompt built from job inputs -> poll
events -> return final result. Read opencode's actual server API at
implementation time (T4); do not guess endpoints in code.
"""
from __future__ import annotations

from typing import Any


def run_montage_job(job: dict[str, Any]) -> dict[str, Any]:
    """Dispatch a montage job to opencode serve. T4 implements."""
    raise NotImplementedError("T4: opencode serve client")


def abort_session(session_id: str) -> None:
    """Abort a running session (used by /interrupt). T4 implements."""
    raise NotImplementedError("T4: abort")
