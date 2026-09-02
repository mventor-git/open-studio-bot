"""Inline keyboards (T6 implements the approval keyboard wiring)."""
from __future__ import annotations

from ui import messages as m

CANCEL_KB = [[{"text": m.CANCEL_BUTTON, "callback_data": "cancel"}]]
APPROVAL_KB = [
    [
        {"text": m.ACCEPT_BUTTON, "callback_data": "approve"},
        {"text": m.RERUN_BUTTON, "callback_data": "rerun"},
        {"text": m.CANCEL_BUTTON, "callback_data": "cancel"},
    ]
]
