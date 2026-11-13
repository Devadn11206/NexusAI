"""
NEXUS AI - Dynamic Telegram Menu Builder
Generates multi-column interactive InlineKeyboardMarkup layouts for application launching,
desktop screenshots, and real-time repository re-scanning.
"""

import math
from typing import Dict, Any, List, Optional
from app.core.repo_scanner import RepoAppScanner


def build_dynamic_control_center(
    page: int = 1,
    per_page: int = 6,
    columns: int = 2,
    custom_apps: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Constructs a Telegram InlineKeyboardMarkup structure for registered applications.

    Args:
        page: Current pagination index (1-based).
        per_page: Number of applications to display per page.
        columns: Grid columns count (typically 2).
        custom_apps: Optional injected apps list (useful for tests and custom filters).

    Returns:
        dict: {"inline_keyboard": [[{"text": "...", "callback_data": "..."}, ...], ...]}
    """
    apps = custom_apps if custom_apps is not None else RepoAppScanner.get_all_registered_apps()
    total_apps = len(apps)

    total_pages = max(1, math.ceil(total_apps / per_page)) if total_apps > 0 else 1
    page = max(1, min(page, total_pages))

    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    current_page_apps = apps[start_idx:end_idx]

    inline_keyboard: List[List[Dict[str, str]]] = []

    # 1. Build Multi-Column Application Buttons
    row: List[Dict[str, str]] = []
    for app in current_page_apps:
        emoji = app.get("emoji", "🚀")
        name = app.get("display_name", app.get("alias_key", "App"))
        alias = app.get("alias_key", "app")

        btn_text = f"{emoji} {name}"
        # Telegram callback_data limit is 64 bytes
        callback_data = f"launch:{alias}"[:64]

        row.append({"text": btn_text, "callback_data": callback_data})

        if len(row) == columns:
            inline_keyboard.append(row)
            row = []

    if row:
        inline_keyboard.append(row)

    # 2. Pagination Navigation Bar (if more than 1 page)
    nav_row: List[Dict[str, str]] = []
    if total_pages > 1:
        if page > 1:
            nav_row.append({"text": "⬅️ Prev", "callback_data": f"menu:page:{page - 1}"})
        else:
            nav_row.append({"text": "⏹️", "callback_data": "menu:noop"})

        nav_row.append({"text": f"📄 {page}/{total_pages}", "callback_data": f"menu:page:{page}"})

        if page < total_pages:
            nav_row.append({"text": "Next ➡️", "callback_data": f"menu:page:{page + 1}"})
        else:
            nav_row.append({"text": "⏹️", "callback_data": "menu:noop"})

        inline_keyboard.append(nav_row)

    # 3. Quick System Actions
    inline_keyboard.append([
        {"text": "📸 Desktop Screenshot", "callback_data": "action:screenshot"},
        {"text": "🔄 Re-Scan Repo Apps", "callback_data": "action:rescan"},
    ])

    return {"inline_keyboard": inline_keyboard}


def get_music_control_keyboard() -> Dict[str, Any]:
    """
    Builds specialized Telegram inline keyboard for media and music playback.
    """
    return {
        "inline_keyboard": [
            [
                {"text": "⏯️ Play/Pause", "callback_data": "music:play_pause"},
                {"text": "⏭️ Next Track", "callback_data": "music:next"},
            ],
            [
                {"text": "🔉 Vol Down", "callback_data": "music:vol_down"},
                {"text": "🔊 Vol Up", "callback_data": "music:vol_up"},
            ],
            [
                {"text": "🟢 Spotify", "callback_data": "music:launch:spotify"},
                {"text": "🔴 YouTube Music", "callback_data": "music:launch:ytmusic"},
            ],
            [
                {"text": "🎵 Now Playing", "callback_data": "music:now_playing"},
                {"text": "📸 Player View", "callback_data": "action:screenshot"},
            ],
        ]
    }


def get_music_control_message_text(now_playing: str = "Active Audio Stream") -> str:
    """Returns formatted markdown text for the Music Control Center."""
    return (
        f"🎧 *NEXUS AI Music & Media Controller*\n\n"
        f"• **Current Track**: `{now_playing}`\n"
        f"• **Status**: Interactive playback active\n\n"
        f"Tap any button below to command your laptop audio:"
    )


def get_control_center_message_text(total_apps: int = 0) -> str:
    """Returns the standard markdown header for the Telegram Control Center."""
    return (
        "🎛️ *NEXUS AI Laptop Control Center*\n\n"
        "All applications detected from repository configurations and local shortcuts are listed below.\n"
        "Tap any button to launch it directly on your laptop screen in the visual foreground:"
    )
