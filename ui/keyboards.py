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


# --- control center (per user request) ---
def control_center_keyboard():
    """Main control center: Row1 [Docs][Help] Row2 [Templates] Row3 [Logs][Settings][Send URL]"""
    if InlineKeyboardButton and InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton("📚 Docs", callback_data="docs"),
                InlineKeyboardButton("❓ Help", callback_data="help"),
            ],
            [
                InlineKeyboardButton("🎨 Templates", callback_data="templates"),
            ],
            [
                InlineKeyboardButton("📊 Logs", callback_data="logs"),
                InlineKeyboardButton("⚙️ Settings", callback_data="settings"),
                InlineKeyboardButton("🔗 Send URL", callback_data="send_url"),
            ],
        ])
    return [
        [
            {"text": "📚 Docs", "callback_data": "docs"},
            {"text": "❓ Help", "callback_data": "help"},
        ],
        [
            {"text": "🎨 Templates", "callback_data": "templates"},
        ],
        [
            {"text": "📊 Logs", "callback_data": "logs"},
            {"text": "⚙️ Settings", "callback_data": "settings"},
            {"text": "🔗 Send URL", "callback_data": "send_url"},
        ],
    ]


def templates_list_keyboard():
    """List view for templates — each template as button + back."""
    if InlineKeyboardButton and InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton("▫️ Template 00 — Raw 9:16", callback_data="select_template_00"),
            ],
            [
                InlineKeyboardButton("✨ Template 01 — TikTok Card", callback_data="select_template_01"),
            ],
            [
                InlineKeyboardButton("⬅️ Back to Control Center", callback_data="back_menu"),
            ],
        ])
    return [
        [
            {"text": "▫️ Template 00 — Raw 9:16", "callback_data": "select_template_00"},
        ],
        [
            {"text": "✨ Template 01 — TikTok Card", "callback_data": "select_template_01"},
        ],
        [
            {"text": "⬅️ Back to Control Center", "callback_data": "back_menu"},
        ],
    ]


def docs_keyboard():
    """Docs view — optional send files + back."""
    if InlineKeyboardButton and InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton("📄 Send docs as files", callback_data="docs_send_files"),
                InlineKeyboardButton("⬅️ Back", callback_data="back_menu"),
            ]
        ])
    return [
        [
            {"text": "📄 Send docs as files", "callback_data": "docs_send_files"},
            {"text": "⬅️ Back", "callback_data": "back_menu"},
        ]
    ]


def help_keyboard():
    if InlineKeyboardButton and InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🎨 Templates", callback_data="templates"),
                InlineKeyboardButton("⬅️ Back", callback_data="back_menu"),
            ]
        ])
    return [
        [
            {"text": "🎨 Templates", "callback_data": "templates"},
            {"text": "⬅️ Back", "callback_data": "back_menu"},
        ]
    ]


def back_menu_keyboard():
    if InlineKeyboardButton and InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Back to Control Center", callback_data="back_menu")]
        ])
    return [[{"text": "⬅️ Back to Control Center", "callback_data": "back_menu"}]]
