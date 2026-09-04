"""Inline keyboards (T6 approval loop)."""
from __future__ import annotations

from ui import messages as m

try:
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup  # type: ignore
except Exception:  # pragma: no cover - for dry-run without telegram
    InlineKeyboardButton = None  # type: ignore
    InlineKeyboardMarkup = None  # type: ignore

CANCEL_KB = [[{"text": m.CANCEL_BUTTON, "callback_data": "cancel"}]]
APPROVAL_KB = [
    [
        {"text": m.ACCEPT_BUTTON, "callback_data": "approve"},
        {"text": m.RERUN_BUTTON, "callback_data": "rerun"},
        {"text": m.REJECT_BUTTON, "callback_data": "reject"},
    ]
]

# ponytail: one function covers all preview cases — job_id may be "" for generic keyboards
def approval_keyboard(job_id: str = ""):
    """Return InlineKeyboardMarkup with approve/rerun/reject for job_id."""
    suffix = f":{job_id}" if job_id else ""
    if InlineKeyboardButton and InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton(m.ACCEPT_BUTTON, callback_data=f"approve{suffix}"),
                InlineKeyboardButton(m.RERUN_BUTTON, callback_data=f"rerun{suffix}"),
                InlineKeyboardButton(m.REJECT_BUTTON, callback_data=f"reject{suffix}"),
            ]
        ])
    # fallback dicts for dry-run / no telegram
    return [
        [
            {"text": m.ACCEPT_BUTTON, "callback_data": f"approve{suffix}"},
            {"text": m.RERUN_BUTTON, "callback_data": f"rerun{suffix}"},
            {"text": m.REJECT_BUTTON, "callback_data": f"reject{suffix}"},
        ]
    ]


# alias required by task spec
def preview_keyboard(job_id: str = ""):
    return approval_keyboard(job_id)


def preview(job_id: str = ""):
    return approval_keyboard(job_id)


# --- wizard v2 keyboards ---
def wizard_preview_keyboard(job_id: str = ""):
    """[✅ Confirm to Upload] [🔁 Rerun] [❌ Revert] per spec."""
    suffix = f":{job_id}" if job_id else ""
    if InlineKeyboardButton and InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton(m.WIZARD_CONFIRM_BUTTON, callback_data=f"confirm{suffix}"),
                InlineKeyboardButton(m.RERUN_BUTTON, callback_data=f"rerun{suffix}"),
                InlineKeyboardButton(m.WIZARD_REVERT_BUTTON, callback_data=f"revert{suffix}"),
            ]
        ])
    return [
        [
            {"text": m.WIZARD_CONFIRM_BUTTON, "callback_data": f"confirm{suffix}"},
            {"text": m.RERUN_BUTTON, "callback_data": f"rerun{suffix}"},
            {"text": m.WIZARD_REVERT_BUTTON, "callback_data": f"revert{suffix}"},
        ]
    ]


def revert_choice_keyboard(job_id: str = ""):
    """[Use Last URL] [New URL]"""
    suffix = f":{job_id}" if job_id else ""
    if InlineKeyboardButton and InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton(m.WIZARD_USE_LAST_BUTTON, callback_data=f"use_last{suffix}"),
                InlineKeyboardButton(m.WIZARD_NEW_URL_BUTTON, callback_data=f"new_url{suffix}"),
            ]
        ])
    return [
        [
            {"text": m.WIZARD_USE_LAST_BUTTON, "callback_data": f"use_last{suffix}"},
            {"text": m.WIZARD_NEW_URL_BUTTON, "callback_data": f"new_url{suffix}"},
        ]
    ]


# keep approve/confirm aliases for callbacks
def confirm_keyboard(job_id: str = ""):
    return wizard_preview_keyboard(job_id)
