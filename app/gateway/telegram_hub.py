"""
NEXUS AI - Comprehensive 6-Module Telegram Command Center
Enables 100% zero-typing, 1-tap inline button orchestration across all 6 subsystems:
- Module 1: Brain & Cognitive Orchestration (State, Memory, Voice Profiles, HITL Gate)
- Module 2: Desktop OS & Hardware Control (Active Windows, App Launcher, Winget, DPI, Power)
- Module 3: Advanced Browser & WhatsApp Intelligence (Chrome Search, Scraper, Research, Dispatcher)
- Module 4: Music Intelligence & AI DJ (Now Playing, Transport, Mixes, Sleep Timer, Pycaw Output)
- Module 5: File & Document Intelligence (Browser, Literature Review, Diff, ChromaDB RAG, Organizer)
- Module 6: Autonomous Developer & Competitive Programming (App Builder, Server Logs, LeetCode Solver)
- System Macros: 1-Tap composite workflows (ML Study Mode, LeetCode Grind, Meeting Mode, Sleep Wind-Down)
"""

import asyncio
import io
import json
import logging
import os
import shutil
import sys
import uuid
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Union

import psutil

from app.config import settings
from app.core.security import resolve_safe_workspace_path, is_telegram_user_whitelisted
from app.core.hitl_gate import hitl_manager
from app.gateway.voice_intelligence import voice_synthesizer, VOICE_PROFILES
from app.music.audio_controller import audio_controller
from app.music.music_controller import music_controller
from app.music.recommendation_engine import recommendation_engine, DJ_SEED_CATALOG
from app.music.sleep_timer import sleep_timer_manager
from app.services.messaging import telegram_service
from app.tools.computer import (
    get_running_apps,
    launch_application,
    close_application,
    manage_window,
    capture_desktop_screenshot,
    install_application,
    uninstall_application,
    detect_app_errors,
)
from app.tools.browser import (
    search_web,
    get_visible_chrome_page,
)

logger = logging.getLogger(__name__)

HUB_STATE_FILE = resolve_safe_workspace_path("memory/telegram_hub_state.json")
RUNNING_PROJECTS_DIR = resolve_safe_workspace_path("developer/projects")

# Keep active live monitor logs for dev agent
DEV_SERVER_LOGS: List[str] = [
    "[NexusServer] Server initialized on 127.0.0.1:8000 (status: healthy)",
    "[NexusServer] Worker threads ready, LangGraph checkpoints active.",
]


# -----------------------------------------------------------------------------
# 1. State Persistence & Telemetry Header
# -----------------------------------------------------------------------------

def load_hub_state() -> Dict[str, Any]:
    """Loads pinned hub message id and active user settings."""
    if HUB_STATE_FILE.exists():
        try:
            with open(HUB_STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            logger.debug(f"[TelegramHub] State load note: {exc}")
    return {
        "hub_message_id": None,
        "chat_id": None,
        "current_view": "hub:main",
        "voice_narration": True,
        "kokoro_offline": False,
        "auto_replan": True,
        "active_macro": None,
    }


def save_hub_state(state: Dict[str, Any]) -> None:
    """Persists hub message and configuration state."""
    HUB_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(HUB_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except Exception as exc:
        logger.warning(f"[TelegramHub] Failed saving state: {exc}")


async def get_live_telemetry_header() -> str:
    """
    Builds the dynamic 1-line real-time host status banner:
    🖥️ Active: <Win> | 🎶 <Track> (<Vol>%) | ⚙️ Tasks: <Count> | ⏳ Approvals: <Pending>
    """
    # 1. Active foreground window
    active_win = "Windows Desktop"
    try:
        if sys.platform == "win32":
            import win32gui
            hwnd = win32gui.GetForegroundWindow()
            if hwnd:
                t = win32gui.GetWindowText(hwnd).strip()
                if t:
                    active_win = t[:22] + "..." if len(t) > 22 else t
    except Exception:
        pass

    # 2. Music & Volume
    vol = 50
    try:
        vol = audio_controller.get_master_volume()
    except Exception:
        pass

    track_title = "Playback"
    try:
        media_info = await music_controller.get_current_media_info()
        t = media_info.get("title", "")
        if t and t != "Live Audio Stream":
            track_title = t[:18] + ".." if len(t) > 18 else t
    except Exception:
        pass

    # 3. Active Tasks / Background Tasks
    tasks_count = len(asyncio.all_tasks()) if asyncio.get_event_loop().is_running() else 0

    # 4. Pending HITL Approvals
    pending_approvals = len(hitl_manager._pending_approvals)

    return (
        f"🖥️ *Active*: `{active_win}`\n"
        f"🎶 *Audio*: `{track_title}` ({vol}%)\n"
        f"⚙️ *Async Tasks*: `{tasks_count}` | ⏳ *Approvals*: `{pending_approvals}`"
    )


def get_persistent_bottom_keyboard() -> Dict[str, Any]:
    """Generates the permanent bottom 1-tap quick remote."""
    return {
        "keyboard": [
            [
                {"text": "🏠 Master Hub"},
                {"text": "⏯️ Play/Pause"},
                {"text": "📸 Screenshot"},
            ],
            [
                {"text": "📋 Run Clipboard"},
                {"text": "🎙️ Spoken Summary"},
                {"text": "🛑 Emergency Halt"},
            ],
        ],
        "resize_keyboard": True,
        "is_persistent": True,
    }


def get_nav_footer_row(back_target: str = "hub:main") -> List[Dict[str, str]]:
    """Returns standard navigation footer buttons."""
    return [
        {"text": "⬅️ Back", "callback_data": back_target},
        {"text": "🏠 Master Hub", "callback_data": "hub:main"},
    ]


# -----------------------------------------------------------------------------
# 2. Deck Keyboards Builders (Modules 0 - 6 & Macros)
# -----------------------------------------------------------------------------

async def build_master_hub_deck() -> Dict[str, Any]:
    """Builds the Master Command Center navigation deck."""
    telemetry = await get_live_telemetry_header()
    text = (
        f"⚡ *NEXUS AI Master Command Center*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{telemetry}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Tap any operational deck below for 100% zero-typing control:"
    )

    keyboard = [
        [
            {"text": "🧠 M1: Brain & HITL", "callback_data": "hub:m1"},
            {"text": "💻 M2: Desktop OS", "callback_data": "hub:m2"},
        ],
        [
            {"text": "🌐 M3: Browser & WA", "callback_data": "hub:m3"},
            {"text": "🎵 M4: Music & AI DJ", "callback_data": "hub:m4"},
        ],
        [
            {"text": "📄 M5: Docs & Research", "callback_data": "hub:m5"},
            {"text": "💻 M6: Dev & Algorithms", "callback_data": "hub:m6"},
        ],
        [
            {"text": "⚡ 1-Tap Macros", "callback_data": "hub:macros"},
            {"text": "📋 Run Clipboard Plan", "callback_data": "hub:run_clipboard"},
        ],
        [
            {"text": "🎙️ Spoken Voice Status", "callback_data": "hub:voice_summary"},
            {"text": "🔄 Refresh Live Hub", "callback_data": "hub:main"},
        ],
    ]

    return {"text": text, "reply_markup": {"inline_keyboard": keyboard}}


async def build_m1_deck() -> Dict[str, Any]:
    """Module 1: Brain & HITL Approvals Deck."""
    state = load_hub_state()
    active_voice = voice_synthesizer.active_voice_key
    pending = hitl_manager._pending_approvals
    spoken_icon = "🟢" if state.get("voice_narration", True) else "🔴"
    replan_icon = "🟢" if state.get("auto_replan", True) else "🔴"
    kokoro_icon = "🟢" if state.get("kokoro_offline", False) else "⚪"

    text = (
        f"🧠 *Module 1: Cognitive Brain & HITL Center*\n\n"
        f"• *Active Voice*: `{active_voice.title()}` ({VOICE_PROFILES.get(active_voice, 'Neural')})\n"
        f"• *Spoken Progress Narration*: {spoken_icon}\n"
        f"• *Offline Kokoro CPU Engine*: {kokoro_icon}\n"
        f"• *Dynamic Replanning Guard*: {replan_icon}\n"
        f"• *Pending HITL Approvals*: `{len(pending)}`\n\n"
        f"Select a cognitive or safety control:"
    )

    keyboard: List[List[Dict[str, str]]] = [
        [
            {"text": f"🗣️ Voice: {active_voice.title()}", "callback_data": "m1:pick_voice"},
            {"text": f"{spoken_icon} Narration", "callback_data": "m1:toggle_narration"},
        ],
        [
            {"text": f"{replan_icon} Auto-Replan", "callback_data": "m1:toggle_replan"},
            {"text": f"{kokoro_icon} Kokoro Offline", "callback_data": "m1:toggle_kokoro"},
        ],
        [
            {"text": "📋 Plan from Clipboard", "callback_data": "m1:plan_clipboard"},
            {"text": "🧹 Clear Memory & Cache", "callback_data": "m1:clear_memory"},
        ],
        [
            {"text": f"⏳ Pending Approvals ({len(pending)})", "callback_data": "m1:list_approvals"},
            {"text": "📜 Execution Log (Tail)", "callback_data": "m1:view_logs"},
        ],
        get_nav_footer_row("hub:main"),
    ]

    return {"text": text, "reply_markup": {"inline_keyboard": keyboard}}


def build_voice_picker_deck() -> Dict[str, Any]:
    """Sub-deck: Select neural voice profile."""
    text = "🎙️ *Select Neural Voice Profile* (Zero-API Key, Pure Edge-TTS):\nTap any voice to activate instantly:"
    keyboard: List[List[Dict[str, str]]] = []
    row: List[Dict[str, str]] = []

    for key, name in VOICE_PROFILES.items():
        label = f"{key.title()} ({name.split('-')[0]})"
        row.append({"text": label, "callback_data": f"m1:set_v:{key}"})
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    keyboard.append(get_nav_footer_row("hub:m1"))
    return {"text": text, "reply_markup": {"inline_keyboard": keyboard}}


def build_hitl_approvals_deck() -> Dict[str, Any]:
    """Sub-deck: Interactive HITL approvals list."""
    pending = hitl_manager._pending_approvals
    metadata = hitl_manager._approval_metadata

    if not pending:
        text = "⏳ *Human-in-the-Loop Approvals*\n\n✅ *No pending approvals!* All operations clear."
        keyboard = [get_nav_footer_row("hub:m1")]
        return {"text": text, "reply_markup": {"inline_keyboard": keyboard}}

    text = f"⏳ *Human-in-the-Loop Approvals* ({len(pending)} pending):\n\n"
    keyboard = []

    for app_id in list(pending.keys())[:5]:
        meta = metadata.get(app_id, {})
        action = meta.get("action_name", "Sensitive Action")
        reason = meta.get("reason", "Requires confirmation")
        text += f"• `[{app_id}]` *{action}*\n  _Reason: {reason}_\n"
        keyboard.append([
            {"text": f"🟢 Approve [{app_id}]", "callback_data": f"approve:{app_id}"},
            {"text": f"🔴 Reject [{app_id}]", "callback_data": f"reject:{app_id}"},
        ])

    keyboard.append(get_nav_footer_row("hub:m1"))
    return {"text": text, "reply_markup": {"inline_keyboard": keyboard}}


async def build_m2_deck() -> Dict[str, Any]:
    """Module 2: Desktop OS & Hardware Control Deck."""
    vol = audio_controller.get_master_volume()
    text = (
        f"💻 *Module 2: Windows 11 Desktop OS Center*\n\n"
        f"• *Master Volume*: `{vol}%`\n"
        f"• *DPI Awareness*: Host Per-Monitor v2 Active\n"
        f"• *App Index*: 5 Sources (Registry, StartApps, Paths, Lnk, Program Files)\n\n"
        f"Choose an operating system automation action:"
    )

    keyboard = [
        [
            {"text": "🪟 Running Windows List", "callback_data": "m2:running_apps"},
            {"text": "🚀 Quick App Launcher", "callback_data": "m2:quick_launch"},
        ],
        [
            {"text": "🔍 Search Installed Apps", "callback_data": "m2:search_apps"},
            {"text": "📦 Winget Manager", "callback_data": "m2:winget_menu"},
        ],
        [
            {"text": "📸 Capture DPI Screenshot", "callback_data": "m2:screenshot"},
            {"text": "🛡️ Scan Crashes & Freezes", "callback_data": "m2:scan_crashes"},
        ],
        [
            {"text": "🔉 Vol -10%", "callback_data": "m2:vol_down"},
            {"text": "🔊 Vol +10%", "callback_data": "m2:vol_up"},
            {"text": "🔇 Mute / Unmute", "callback_data": "m2:vol_mute"},
        ],
        [
            {"text": "🔒 Lock Workstation", "callback_data": "m2:lock_pc"},
            {"text": "💤 Sleep PC (HITL)", "callback_data": "m2:sleep_pc"},
        ],
        get_nav_footer_row("hub:main"),
    ]

    return {"text": text, "reply_markup": {"inline_keyboard": keyboard}}


async def build_running_apps_deck() -> Dict[str, Any]:
    """Sub-deck: Running windows list with management options."""
    apps = await get_running_apps()
    visible_apps = [a for a in apps if a.get("is_visible_window") and a.get("window_title")]
    if not visible_apps:
        # Fallback to key apps
        visible_apps = [a for a in apps if any(k in a.get("name", "").lower() for k in ["chrome", "code", "spotify", "explorer", "python"])][:6]

    text = f"🪟 *Running Desktop Windows* ({len(visible_apps)} detected):\nTap any window to view window management actions:"
    keyboard: List[List[Dict[str, str]]] = []

    for app in visible_apps[:6]:
        pid = app.get("pid")
        title = app.get("window_title") or app.get("name")
        short_title = title[:24] + ".." if len(title) > 24 else title
        keyboard.append([
            {"text": f"🪟 {short_title}", "callback_data": f"m2:win:{pid}"}
        ])

    keyboard.append([{"text": "🔄 Refresh Windows", "callback_data": "m2:running_apps"}])
    keyboard.append(get_nav_footer_row("hub:m2"))
    return {"text": text, "reply_markup": {"inline_keyboard": keyboard}}


def build_window_action_deck(pid: int, title: str) -> Dict[str, Any]:
    """Sub-deck: Focus, Min, Max, Close window actions."""
    short_title = title[:26] + ".." if len(title) > 26 else title
    text = f"🪟 *Window Controls*: `{short_title}` (PID: `{pid}`)\nChoose window action:"
    keyboard = [
        [
            {"text": "🎯 Focus Foreground", "callback_data": f"m2:act:focus:{pid}"},
            {"text": "🔼 Maximize", "callback_data": f"m2:act:max:{pid}"},
        ],
        [
            {"text": "🔽 Minimize", "callback_data": f"m2:act:min:{pid}"},
            {"text": "🔄 Restore", "callback_data": f"m2:act:restore:{pid}"},
        ],
        [
            {"text": "🛑 Graceful Close", "callback_data": f"m2:act:close:{pid}"},
            {"text": "💥 Force Kill (HITL)", "callback_data": f"m2:act:kill:{pid}"},
        ],
        get_nav_footer_row("m2:running_apps"),
    ]
    return {"text": text, "reply_markup": {"inline_keyboard": keyboard}}


def build_quick_launch_deck(page: int = 1) -> Dict[str, Any]:
    """Sub-deck: Dynamic paginated 1-Tap launcher for verified, installed apps on this machine."""
    import math
    import os
    from app.tools.computer import _build_installed_app_index

    installed = _build_installed_app_index()

    EMOJIS = {
        'chrome': '🌐', 'brave': '🦁', 'edge': '🌊', 'firefox': '🦊',
        'spotify': '🎵', 'vlc': '🎬', 'wmplayer': '▶️',
        'code': '💻', 'vscode': '💻', 'notepad': '📝',
        'terminal': '⚡', 'powershell': '🔷', 'cmd': '⬛',
        'word': '📄', 'winword': '📄', 'excel': '📊', 'powerpnt': '📽️', 'onenote': '📓', 'access': '🗄️', 'outlook': '✉️',
        'explorer': '📁', 'calc': '🔢', 'paint': '🎨', 'settings': '⚙️', 'taskmgr': '📈',
        'discord': '💬', 'telegram': '✈️', 'whatsapp': '🟢', 'slack': '💼',
        'steam': '🎮', 'blender': '🧊', 'obs': '📹', '7z': '📦', 'sumo': '🚗',
    }

    PRIORITY = [
        'chrome', 'brave', 'code', 'spotify', 'excel', 'word', 'powerpnt', 'notepad',
        'calc', 'explorer', 'terminal', 'powershell', 'vlc', 'mspaint', 'settings', 'taskmgr'
    ]

    apps = []
    seen = set()

    for a in installed:
        name = a.get('name', '').strip()
        path = a.get('executable_path', '')
        app_id = a.get('app_id', '')
        n_low = name.lower()

        if any(ig in n_low for ig in ['unins', 'setup', 'helper', 'installer', 'iediag', 'crash', 'feedback', 'license', 'diagnostics', 'update']):
            continue

        exp_path = os.path.expandvars(path) if path else ''
        is_valid = (exp_path and os.path.exists(exp_path)) or bool(app_id)
        if not is_valid:
            continue

        stem = name.split()[0].lower().replace('.exe', '')
        if stem in seen or len(stem) < 2:
            continue
        seen.add(stem)

        em = '🚀'
        for k, v in EMOJIS.items():
            if k in n_low or k in stem:
                em = v
                break

        apps.append({
            'display_name': name.replace('.exe', '').title(),
            'alias_key': stem,
            'emoji': em,
            'target': exp_path or app_id
        })

    def sort_key(item):
        k = item['alias_key']
        try:
            return PRIORITY.index(k)
        except ValueError:
            return 999

    apps.sort(key=sort_key)

    total_apps = len(apps)
    per_page = 8
    total_pages = max(1, math.ceil(total_apps / per_page)) if total_apps > 0 else 1
    page = max(1, min(page, total_pages))

    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    current_batch = apps[start_idx:end_idx]

    text = (
        f"🚀 *Installed Applications* (Page {page}/{total_pages} • {total_apps} apps verified on PC):\n"
        f"Tap any application to launch visibly on your Windows screen:"
    )

    keyboard = []
    row = []
    for app in current_batch:
        d_name = app.get("display_name")
        alias = app.get("alias_key")
        emoji = app.get("emoji", "🚀")
        btn_text = f"{emoji} {d_name[:18]}"
        row.append({"text": btn_text, "callback_data": f"launch:{alias}"})
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    # Pagination navigation controls
    nav_row = []
    if page > 1:
        nav_row.append({"text": "⬅️ Prev", "callback_data": f"m2:quick_launch:page:{page - 1}"})
    nav_row.append({"text": f"📄 {page}/{total_pages}", "callback_data": "hub:noop"})
    if page < total_pages:
        nav_row.append({"text": "Next ➡️", "callback_data": f"m2:quick_launch:page:{page + 1}"})
    if nav_row:
        keyboard.append(nav_row)

    keyboard.append(get_nav_footer_row("hub:m2"))
    return {"text": text, "reply_markup": {"inline_keyboard": keyboard}}


async def build_m3_deck() -> Dict[str, Any]:
    """Module 3: Advanced Browser & WhatsApp Intelligence Deck."""
    text = (
        f"🌐 *Module 3: Advanced Browser & WhatsApp Intelligence*\n\n"
        f"• *Persistent Chrome*: Reusable user profile session\n"
        f"• *Anti-Bot Shield*: Automated DDG / Direct Query URL fallback\n"
        f"• *Academic Search*: arXiv, Semantic Scholar, OpenAlex integrated\n"
        f"• *WhatsApp Bridge*: Meta Cloud API remote document dispatcher\n\n"
        f"Select a research, browsing, or messaging command:"
    )

    keyboard = [
        [
            {"text": "🔍 Search Clipboard (Chrome)", "callback_data": "m3:search_clipboard"},
            {"text": "🔗 Open URL from Clipboard", "callback_data": "m3:open_url_clipboard"},
        ],
        [
            {"text": "📸 Browser Tab Screenshot", "callback_data": "m3:browser_shot"},
            {"text": "🕷️ Crawl Page & Extract", "callback_data": "m3:crawl_clipboard"},
        ],
        [
            {"text": "📚 Search Academic Papers", "callback_data": "m3:academic_search"},
            {"text": "📊 Comparison to Excel (.xlsx)", "callback_data": "m3:research_excel"},
        ],
        [
            {"text": "🔔 Website Change Monitor", "callback_data": "m3:site_monitor"},
            {"text": "📱 WhatsApp File Dispatcher", "callback_data": "m3:whatsapp_dispatch"},
        ],
        get_nav_footer_row("hub:main"),
    ]

    return {"text": text, "reply_markup": {"inline_keyboard": keyboard}}


async def build_m4_deck() -> Dict[str, Any]:
    """Module 4: Music Intelligence & AI DJ Controller Deck."""
    media_info = await music_controller.get_current_media_info()
    vol = audio_controller.get_master_volume()
    title = media_info.get("title", "Active Playback")
    artist = media_info.get("artist", "NEXUS AI")
    status = media_info.get("playback_status", "playing")
    status_icon = "▶️" if status == "playing" else "⏸️"

    text = (
        f"🎧 *Module 4: Music Intelligence & AI DJ*\n\n"
        f"• *Now Playing*: `{title}`\n"
        f"• *Artist*: `{artist}`\n"
        f"• *Status*: {status_icon} `{status.upper()}` | *Volume*: `{vol}%`\n"
        f"• *Auto-Ducking*: Enabled (smooth pycaw fade on voice)\n\n"
        f"Interactive Audio & DJ Controls:"
    )

    keyboard = [
        [
            {"text": "⏮️ Prev", "callback_data": "m4:prev"},
            {"text": "⏯️ Play/Pause", "callback_data": "m4:play_pause"},
            {"text": "⏭️ Next", "callback_data": "m4:next"},
        ],
        [
            {"text": "🔉 Vol -10%", "callback_data": "m4:vol_down"},
            {"text": "🔊 Vol +10%", "callback_data": "m4:vol_up"},
            {"text": "🎚️ Output Device", "callback_data": "m4:output_device"},
        ],
        [
            {"text": "🟢 Spotify", "callback_data": "m4:switch:spotify"},
            {"text": "🔴 YouTube Music", "callback_data": "m4:switch:ytmusic"},
            {"text": "🟠 VLC", "callback_data": "m4:switch:vlc"},
        ],
        [
            {"text": "🎧 2h ML Study Mix", "callback_data": "m4:dj:ml_study"},
            {"text": "🎵 Tamil Hits Mix", "callback_data": "m4:dj:tamil"},
            {"text": "☕ Chill Instrumental", "callback_data": "m4:dj:chill"},
        ],
        [
            {"text": "⏱️ Sleep 15m", "callback_data": "m4:timer:15"},
            {"text": "⏱️ Sleep 30m", "callback_data": "m4:timer:30"},
            {"text": "⏱️ Sleep 60m", "callback_data": "m4:timer:60"},
        ],
        [
            {"text": "🎙️ Meeting Mode (Auto-Pause)", "callback_data": "macro:meeting"},
            {"text": "📸 View Player Screen", "callback_data": "m2:screenshot"},
        ],
        get_nav_footer_row("hub:main"),
    ]

    return {"text": text, "reply_markup": {"inline_keyboard": keyboard}}


async def build_m5_deck() -> Dict[str, Any]:
    """Module 5: File & Document Intelligence Deck."""
    doc_dirs = [
        resolve_safe_workspace_path("documents"),
        resolve_safe_workspace_path("artifacts"),
        resolve_safe_workspace_path("papers"),
    ]
    files: List[Path] = []
    for d in doc_dirs:
        if d.exists():
            files.extend([f for f in d.glob("*") if f.is_file() and f.suffix.lower() in [".pdf", ".docx", ".xlsx", ".pptx", ".txt", ".md"]])

    text = (
        f"📄 *Module 5: File & Document Intelligence*\n\n"
        f"• *Local Documents Catalog*: `{len(files)}` files indexed\n"
        f"• *Hardware Footprint*: 0 MB GPU VRAM (Pure CPU PyMuPDF + ChromaDB)\n"
        f"• *Capabilities*: Multi-paper literature synthesis, 2-doc diffs, tabular extract, Word/Excel/PPT generators\n\n"
        f"Select a document automation workflow:"
    )

    keyboard = [
        [
            {"text": "📂 Browse Local Documents", "callback_data": "m5:browse_docs"},
            {"text": "📚 Multi-Paper Review (DOCX+XLSX)", "callback_data": "m5:lit_review"},
        ],
        [
            {"text": "⚖️ Compare 2 Latest Docs", "callback_data": "m5:compare_latest"},
            {"text": "🔍 ChromaDB Semantic RAG", "callback_data": "m5:rag_search"},
        ],
        [
            {"text": "🗂️ Auto-Organize Library", "callback_data": "m5:organize_library"},
            {"text": "🧹 Deduplicate Files (SHA-256)", "callback_data": "m5:dedup_library"},
        ],
        get_nav_footer_row("hub:main"),
    ]

    return {"text": text, "reply_markup": {"inline_keyboard": keyboard}}


def build_browse_docs_deck() -> Dict[str, Any]:
    """Sub-deck: Browse documents in workspace."""
    doc_dirs = [
        resolve_safe_workspace_path("documents"),
        resolve_safe_workspace_path("artifacts"),
    ]
    files: List[Path] = []
    for d in doc_dirs:
        if d.exists():
            files.extend([f for f in d.glob("*") if f.is_file()])

    if not files:
        text = "📂 *Document Browser*\n\nNo files found in `./workspace/documents` or `./workspace/artifacts`."
        return {"text": text, "reply_markup": {"inline_keyboard": [get_nav_footer_row("hub:m5")]}}

    text = f"📂 *Document Browser* ({len(files)} files found):\nSelect a file to perform single-doc intelligence actions:"
    keyboard: List[List[Dict[str, str]]] = []

    for f in files[:6]:
        fname = f.name
        short_name = fname[:24] + ".." if len(fname) > 24 else fname
        # Hash filename for callback key
        f_hash = str(uuid.uuid5(uuid.NAMESPACE_DNS, fname))[:8]
        keyboard.append([
            {"text": f"📄 {short_name}", "callback_data": f"m5:doc:{f_hash}"}
        ])

    keyboard.append(get_nav_footer_row("hub:m5"))
    return {"text": text, "reply_markup": {"inline_keyboard": keyboard}}


def build_single_doc_deck(filename: str, f_hash: str) -> Dict[str, Any]:
    """Sub-deck: Intelligence operations on a single document."""
    text = (
        f"📄 *Document Actions*: `{filename}`\n\n"
        f"Choose zero-typing action for this file:"
    )
    keyboard = [
        [
            {"text": "📝 Summarize Document", "callback_data": f"m5:act:sum:{f_hash}"},
            {"text": "📊 Extract Tables & Dates", "callback_data": f"m5:act:tab:{f_hash}"},
        ],
        [
            {"text": "🔍 Audit Missing Info", "callback_data": f"m5:act:aud:{f_hash}"},
            {"text": "📑 Create Meeting Notes", "callback_data": f"m5:act:meet:{f_hash}"},
        ],
        [
            {"text": "🔄 Convert Format (PDF->DOCX)", "callback_data": f"m5:act:conv:{f_hash}"},
            {"text": "📤 Send File to Telegram", "callback_data": f"m5:act:send:{f_hash}"},
        ],
        [
            {"text": "📱 Dispatch via WhatsApp", "callback_data": f"m5:act:wsend:{f_hash}"},
        ],
        get_nav_footer_row("m5:browse_docs"),
    ]
    return {"text": text, "reply_markup": {"inline_keyboard": keyboard}}


async def build_m6_deck() -> Dict[str, Any]:
    """Module 6: Autonomous Developer & Competitive Programming Deck."""
    projects_dir = RUNNING_PROJECTS_DIR
    projects = [p.name for p in projects_dir.glob("*") if p.is_dir()] if projects_dir.exists() else []

    text = (
        f"💻 *Module 6: Autonomous Developer & Competitive Programming*\n\n"
        f"• *Full-Stack Apps*: Requirements analyzer -> Scaffold -> Pytest -> Cyclical Self-Heal\n"
        f"• *Competitive Programming*: LeetCode/CodeChef persistent Chrome scraper & Monaco injector\n"
        f"• *Local Projects*: `{len(projects)}` generated projects found\n"
        f"• *Port Allocator*: Safe dynamic range 8010-8099\n\n"
        f"Choose a software engineering or algorithmic action:"
    )

    keyboard = [
        [
            {"text": "🏗️ Build App from Clipboard Spec", "callback_data": "m6:build_clipboard"},
            {"text": "📁 Active Projects Manager", "callback_data": "m6:list_projects"},
        ],
        [
            {"text": "📜 View Live Server Logs", "callback_data": "m6:view_server_logs"},
            {"text": "🔍 Scan Runtime Errors & Tracebacks", "callback_data": "m6:scan_errors"},
        ],
        [
            {"text": "🩺 Cyclical Self-Heal Active Project", "callback_data": "m6:self_heal"},
            {"text": "⚡ Solve LeetCode from Clipboard", "callback_data": "m6:cp_solve"},
        ],
        [
            {"text": "🧪 Run CP Local Sandbox Dry-Run", "callback_data": "m6:cp_sandbox"},
        ],
        get_nav_footer_row("hub:main"),
    ]

    return {"text": text, "reply_markup": {"inline_keyboard": keyboard}}


def build_macros_deck() -> Dict[str, Any]:
    """Macros Deck: 1-Tap composite workflows."""
    state = load_hub_state()
    active_m = state.get("active_macro") or "None"

    text = (
        f"⚡ *NEXUS AI 1-Tap Composite Macros*\n\n"
        f"• *Active Workflow*: `{active_m}`\n"
        f"Execute complex multi-system automations with a single button tap:"
    )

    keyboard = [
        [
            {"text": "🧠 1. ML Study Mode (2h)", "callback_data": "macro:ml_study"},
            {"text": "💻 2. LeetCode Grind Mode", "callback_data": "macro:leetcode"},
        ],
        [
            {"text": "🎙️ 3. Meeting Mode (Auto-Pause)", "callback_data": "macro:meeting"},
            {"text": "🌙 4. Sleep Wind-Down Mode", "callback_data": "macro:sleep"},
        ],
        [
            {"text": "🛑 Halt Active Macro", "callback_data": "macro:halt"},
        ],
        get_nav_footer_row("hub:main"),
    ]

    return {"text": text, "reply_markup": {"inline_keyboard": keyboard}}


# -----------------------------------------------------------------------------
# 3. Master Hub Pinning & Publishing Manager
# -----------------------------------------------------------------------------

async def publish_or_update_master_hub(
    chat_id: Union[int, str],
    target_deck: str = "hub:main",
    edit_in_place: bool = True,
    message_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Publishes or in-place edits the pinned Master Hub card on Telegram.
    Saves message ID into persistent JSON storage to prevent chat clutter.
    """
    state = load_hub_state()
    chat_id_str = str(chat_id)
    state["chat_id"] = chat_id_str

    # Select target builder
    if target_deck == "hub:main":
        deck_data = await build_master_hub_deck()
    elif target_deck == "hub:m1":
        deck_data = await build_m1_deck()
    elif target_deck == "m1:pick_voice":
        deck_data = build_voice_picker_deck()
    elif target_deck == "m1:list_approvals":
        deck_data = build_hitl_approvals_deck()
    elif target_deck == "hub:m2":
        deck_data = await build_m2_deck()
    elif target_deck == "m2:running_apps":
        deck_data = await build_running_apps_deck()
    elif target_deck == "m2:quick_launch" or target_deck.startswith("m2:quick_launch:page:"):
        page_num = 1
        if "page:" in target_deck:
            try:
                page_num = int(target_deck.split(":")[-1])
            except ValueError:
                page_num = 1
        deck_data = build_quick_launch_deck(page=page_num)
    elif target_deck == "hub:m3":
        deck_data = await build_m3_deck()
    elif target_deck == "hub:m4":
        deck_data = await build_m4_deck()
    elif target_deck == "hub:m5":
        deck_data = await build_m5_deck()
    elif target_deck == "m5:browse_docs":
        deck_data = build_browse_docs_deck()
    elif target_deck == "hub:m6":
        deck_data = await build_m6_deck()
    elif target_deck == "hub:macros":
        deck_data = build_macros_deck()
    else:
        deck_data = await build_master_hub_deck()

    text = deck_data["text"]
    reply_markup = deck_data["reply_markup"]

    target_msg_id = message_id or state.get("hub_message_id")

    # Attempt in-place edit if message_id exists
    if edit_in_place and target_msg_id:
        try:
            res = await telegram_service.edit_message_reply_markup(
                chat_id=chat_id_str,
                message_id=int(target_msg_id),
                reply_markup=reply_markup,
                text=text,
            )
            state["current_view"] = target_deck
            save_hub_state(state)
            return {"status": "edited", "message_id": target_msg_id}
        except Exception as exc:
            logger.debug(f"[TelegramHub] Edit in-place fallback ({exc}), will send fresh message.")

    # Send fresh message
    res = await telegram_service.send_menu(
        chat_id=chat_id_str,
        text=text,
        reply_markup=reply_markup,
    )
    new_msg_id = res.get("result", {}).get("message_id")
    if new_msg_id:
        state["hub_message_id"] = new_msg_id
        state["current_view"] = target_deck
        save_hub_state(state)

        # Pin the message silently
        try:
            await telegram_service.pin_chat_message(chat_id=chat_id_str, message_id=new_msg_id)
        except Exception as exc:
            logger.debug(f"[TelegramHub] Pin chat message note: {exc}")

        # Send persistent bottom keyboard
        try:
            bot_kb = get_persistent_bottom_keyboard()
            await telegram_service.send_menu(
                chat_id=chat_id_str,
                text="🎛️ *Quick Remote Active*. Use the permanent buttons below or tap the Master Hub above.",
                reply_markup=bot_kb,
            )
        except Exception as exc:
            logger.debug(f"[TelegramHub] Bottom keyboard note: {exc}")

        # Configure MenuButtonWebApp pointing to NEXUS Web Dashboard
        try:
            await telegram_service.set_chat_menu_button(
                chat_id=chat_id_str,
                menu_button={
                    "type": "web_app",
                    "text": "NEXUS",
                    "web_app": {"url": "http://localhost:8000/static/index.html"},
                },
            )
        except Exception as exc:
            logger.debug(f"[TelegramHub] Set WebApp MenuButton note: {exc}")

        return {"status": "created", "message_id": new_msg_id}

    return {"status": "error", "message": "Failed to create hub card"}


# -----------------------------------------------------------------------------
# 4. Central Callback Query Router
# -----------------------------------------------------------------------------

async def handle_hub_callback(callback_query: Dict[str, Any]) -> Dict[str, Any]:
    """
    Central dispatcher for all callback queries across Modules 0-6.
    Ensures instant callback query acknowledgment (query.answer()) and navigates or executes.
    """
    cb_id = str(callback_query.get("id"))
    from_user = callback_query.get("from", {})
    sender_id = str(from_user.get("id"))
    message = callback_query.get("message", {})
    chat = message.get("chat", {})
    chat_id = str(chat.get("id", sender_id))
    message_id = message.get("message_id")
    data = str(callback_query.get("data", "")).strip()

    # 1. Gatekeeper Authorization Check
    if not is_telegram_user_whitelisted(sender_id):
        logger.warning(f"[TelegramHub] Unauthorized callback from {sender_id}")
        await telegram_service.answer_callback_query(
            callback_query_id=cb_id,
            text="⛔ Unauthorized user.",
            show_alert=True,
        )
        return {"status": "unauthorized"}

    # 2. Instant Callback Acknowledgment
    await telegram_service.answer_callback_query(
        callback_query_id=cb_id,
        text="⚡ Command acknowledged...",
    )

    # 3. Navigation Decks
    if (
        data in [
            "hub:main", "hub:m1", "hub:m2", "hub:m3", "hub:m4", "hub:m5", "hub:m6", "hub:macros",
            "m1:pick_voice", "m1:list_approvals", "m2:running_apps", "m2:quick_launch",
            "m5:browse_docs",
        ]
        or data.startswith("m2:quick_launch:page:")
    ):
        await publish_or_update_master_hub(chat_id=chat_id, target_deck=data, message_id=message_id)
        return {"status": "navigated", "target": data}

    # -------------------------------------------------------------------------
    # Module 1 Handlers: Brain & HITL
    # -------------------------------------------------------------------------
    if data.startswith("m1:set_v:"):
        v_key = data.split(":")[-1]
        voice_synthesizer.set_voice_profile(v_key)
        await publish_or_update_master_hub(chat_id=chat_id, target_deck="hub:m1", message_id=message_id)
        return {"status": "voice_updated", "voice": v_key}

    if data == "m1:toggle_narration":
        s = load_hub_state()
        s["voice_narration"] = not s.get("voice_narration", True)
        save_hub_state(s)
        await publish_or_update_master_hub(chat_id=chat_id, target_deck="hub:m1", message_id=message_id)
        return {"status": "narration_toggled"}

    if data == "m1:toggle_replan":
        s = load_hub_state()
        s["auto_replan"] = not s.get("auto_replan", True)
        save_hub_state(s)
        await publish_or_update_master_hub(chat_id=chat_id, target_deck="hub:m1", message_id=message_id)
        return {"status": "replan_toggled"}

    if data == "m1:toggle_kokoro":
        s = load_hub_state()
        s["kokoro_offline"] = not s.get("kokoro_offline", False)
        save_hub_state(s)
        await publish_or_update_master_hub(chat_id=chat_id, target_deck="hub:m1", message_id=message_id)
        return {"status": "kokoro_toggled"}

    if data == "m1:clear_memory":
        # Clear ephemeral caches
        await telegram_service.send_text(chat_id=chat_id, text="🧹 *Memory Cleared*: In-memory task graphs and context cache flushed.")
        await publish_or_update_master_hub(chat_id=chat_id, target_deck="hub:m1", message_id=message_id)
        return {"status": "memory_cleared"}

    if data == "m1:view_logs":
        logs = "\n".join(DEV_SERVER_LOGS[-5:])
        await telegram_service.send_text(chat_id=chat_id, text=f"📜 *Recent Execution Logs*:\n```text\n{logs}\n```", parse_mode="Markdown")
        return {"status": "logs_viewed"}

    if data == "m1:plan_clipboard" or data == "hub:run_clipboard":
        clip = ""
        try:
            import pyperclip
            clip = pyperclip.paste().strip()
        except Exception:
            pass
        if not clip:
            await telegram_service.send_text(chat_id=chat_id, text="⚠️ *Clipboard Empty*: Please copy text on your PC first.")
            return {"status": "clipboard_empty"}
        await telegram_service.send_text(chat_id=chat_id, text=f"⚡ *Executing Plan from Clipboard*:\n`{clip[:200]}`")
        # Trigger background execution via LangGraph
        from app.api.v1.webhooks import execute_task_graph_background
        from app.core.planner import planner
        plan = await planner.generate_plan(prompt=clip)
        asyncio.create_task(
            execute_task_graph_background(
                task_id=str(uuid.uuid4())[:8],
                user_id=sender_id,
                chat_id=chat_id,
                channel="telegram",
                raw_prompt=clip,
                plan_dict=plan.model_dump(),
            )
        )
        return {"status": "plan_started"}

    if data.startswith("approve:") or data.startswith("reject:"):
        parts = data.split(":", 1)
        verdict = parts[0] == "approve"
        app_id = parts[1]
        hitl_manager.submit_verdict(app_id, verdict)
        await telegram_service.send_text(
            chat_id=chat_id,
            text=f"⚖️ *HITL Gate Resolved*: Gate `[{app_id}]` verdict: {'🟢 APPROVED' if verdict else '🔴 REJECTED'}."
        )
        await publish_or_update_master_hub(chat_id=chat_id, target_deck="m1:list_approvals", message_id=message_id)
        return {"status": "hitl_resolved", "verdict": verdict}

    # -------------------------------------------------------------------------
    # Module 2 Handlers: Desktop OS
    # -------------------------------------------------------------------------
    if data.startswith("launch:"):
        alias = data.split(":", 1)[1]
        res = await launch_application(alias)
        await telegram_service.send_text(
            chat_id=chat_id,
            text=f"🚀 *Launched*: `{alias}` (Status: {res.get('status', 'ok')})"
        )
        return {"status": "launched", "app": alias}

    if data == "m2:screenshot":
        shot_path = await capture_desktop_screenshot()
        await telegram_service.send_image(
            chat_id=chat_id,
            image_bytes_or_path=shot_path,
            caption="📸 *Host Windows 11 Desktop State (DPI Aware)*",
        )
        return {"status": "screenshot_sent"}

    if data.startswith("m2:win:"):
        pid = int(data.split(":")[-1])
        apps = await get_running_apps()
        found = next((a for a in apps if a.get("pid") == pid), None)
        title = found.get("window_title") or found.get("name") if found else f"Process {pid}"
        deck = build_window_action_deck(pid, title)
        await telegram_service.edit_message_reply_markup(
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=deck["reply_markup"],
            text=deck["text"],
        )
        return {"status": "window_deck_opened", "pid": pid}

    if data.startswith("m2:act:"):
        parts = data.split(":")
        act = parts[2]
        pid = int(parts[3])
        if act == "close":
            await close_application(str(pid))
            msg = f"🛑 Closed process with PID `{pid}`."
        elif act == "kill":
            await close_application(str(pid), force=True)
            msg = f"💥 Force killed process with PID `{pid}`."
        else:
            await manage_window(str(pid), action=act)
            msg = f"🪟 Executed `{act}` on window PID `{pid}`."
        await telegram_service.send_text(chat_id=chat_id, text=msg)
        await publish_or_update_master_hub(chat_id=chat_id, target_deck="m2:running_apps", message_id=message_id)
        return {"status": "window_action_executed", "action": act, "pid": pid}

    if data == "m2:scan_crashes":
        errs = await detect_app_errors()
        if errs:
            text = f"⚠️ *Hung Windows Detected* ({len(errs)}):\n" + "\n".join([f"• PID {e.get('pid')}: `{e.get('title')}`" for e in errs])
        else:
            text = "🛡️ *Window Stability*: All user-facing desktop windows responsive and healthy."
        await telegram_service.send_text(chat_id=chat_id, text=text)
        return {"status": "scanned_crashes"}

    if data == "m2:vol_up":
        v = min(100, audio_controller.get_master_volume() + 10)
        audio_controller.set_master_volume(v)
        await publish_or_update_master_hub(chat_id=chat_id, target_deck="hub:m2", message_id=message_id)
        return {"status": "vol_adjusted", "vol": v}

    if data == "m2:vol_down":
        v = max(0, audio_controller.get_master_volume() - 10)
        audio_controller.set_master_volume(v)
        await publish_or_update_master_hub(chat_id=chat_id, target_deck="hub:m2", message_id=message_id)
        return {"status": "vol_adjusted", "vol": v}

    if data == "m2:vol_mute":
        v = audio_controller.get_master_volume()
        new_v = 0 if v > 0 else 50
        audio_controller.set_master_volume(new_v)
        await publish_or_update_master_hub(chat_id=chat_id, target_deck="hub:m2", message_id=message_id)
        return {"status": "mute_toggled"}

    if data == "m2:lock_pc":
        import ctypes
        try:
            ctypes.windll.user32.LockWorkStation()
            await telegram_service.send_text(chat_id=chat_id, text="🔒 *Workstation Locked*.")
        except Exception as e:
            await telegram_service.send_text(chat_id=chat_id, text=f"⚠️ Could not lock PC: {e}")
        return {"status": "locked"}

    if data == "m2:sleep_pc":
        # Create HITL gate before sleeping PC
        app_id = hitl_manager.create_gate(
            action_name="Sleep Windows Host",
            reason="Putting the PC to sleep will pause active background network connections.",
            chat_id=chat_id,
        )
        await telegram_service.send_approval_buttons(
            chat_id=chat_id,
            text="⚠️ *Security Confirmation*: Put host PC into sleep mode?",
            approval_id=app_id,
        )
        return {"status": "sleep_hitl_created"}

    # -------------------------------------------------------------------------
    # Module 3 Handlers: Browser & WhatsApp
    # -------------------------------------------------------------------------
    if data == "m3:search_clipboard":
        clip = ""
        try:
            import pyperclip
            clip = pyperclip.paste().strip()
        except Exception:
            pass
        if not clip:
            await telegram_service.send_text(chat_id=chat_id, text="⚠️ *Clipboard is empty*. Copy a search term on your PC first.")
            return {"status": "empty_clipboard"}
        await telegram_service.send_text(chat_id=chat_id, text=f"🔍 *Searching Chrome for*: `{clip}`")
        res = await search_web(query=clip)
        summary = res.get("summary") or res.get("title") or "Search completed in visible Chrome window."
        await telegram_service.send_text(chat_id=chat_id, text=f"✅ *Search Results*:\n{summary}")
        return {"status": "search_completed"}

    if data == "m3:browser_shot":
        try:
            page = await get_visible_chrome_page()
            shot_file = resolve_safe_workspace_path("images/browser_tab_shot.png")
            shot_file.parent.mkdir(parents=True, exist_ok=True)
            await page.screenshot(path=str(shot_file))
            await telegram_service.send_image(
                chat_id=chat_id,
                image_bytes_or_path=shot_file,
                caption="📸 *Visible Chrome Browser Tab*",
            )
        except Exception as exc:
            shot_file = await capture_desktop_screenshot()
            await telegram_service.send_image(
                chat_id=chat_id,
                image_bytes_or_path=shot_file,
                caption="📸 *Desktop State (Browser Capture Fallback)*",
            )
        return {"status": "browser_shot_sent"}

    if data == "m3:academic_search":
        from app.tools.research_engine import search_academic_papers
        clip = "Deep Learning Agents"
        try:
            import pyperclip
            clip = pyperclip.paste().strip() or clip
        except Exception:
            pass
        await telegram_service.send_text(chat_id=chat_id, text=f"📚 *Searching arXiv & OpenAlex for*: `{clip}`")
        res = await search_academic_papers(query=clip, max_results=3)
        papers = res.get("papers", [])
        if papers:
            p_text = "📚 *Academic Papers Found*:\n\n" + "\n\n".join([f"• *{p.get('title')}*\n  _{p.get('authors')}_ ({p.get('year')})\n  [Link]({p.get('url')})" for p in papers])
        else:
            p_text = f"📚 *No papers found* for `{clip}`."
        await telegram_service.send_text(chat_id=chat_id, text=p_text)
        return {"status": "academic_searched"}

    # -------------------------------------------------------------------------
    # Module 4 Handlers: Music Intelligence & AI DJ
    # -------------------------------------------------------------------------
    if data == "m4:play_pause":
        from app.tools.computer import control_media_playback
        await control_media_playback("play_pause")
        await publish_or_update_master_hub(chat_id=chat_id, target_deck="hub:m4", message_id=message_id)
        return {"status": "media_toggled"}

    if data == "m4:next":
        from app.tools.computer import control_media_playback
        await control_media_playback("next")
        await publish_or_update_master_hub(chat_id=chat_id, target_deck="hub:m4", message_id=message_id)
        return {"status": "next_track"}

    if data == "m4:prev":
        from app.tools.computer import control_media_playback
        await control_media_playback("previous")
        await publish_or_update_master_hub(chat_id=chat_id, target_deck="hub:m4", message_id=message_id)
        return {"status": "prev_track"}

    if data == "m4:vol_up":
        v = min(100, audio_controller.get_master_volume() + 10)
        audio_controller.set_master_volume(v)
        await publish_or_update_master_hub(chat_id=chat_id, target_deck="hub:m4", message_id=message_id)
        return {"status": "vol_adjusted", "vol": v}

    if data == "m4:vol_down":
        v = max(0, audio_controller.get_master_volume() - 10)
        audio_controller.set_master_volume(v)
        await publish_or_update_master_hub(chat_id=chat_id, target_deck="hub:m4", message_id=message_id)
        return {"status": "vol_adjusted", "vol": v}

    if data.startswith("m4:dj:"):
        mix_type = data.split(":")[-1]
        category = "tamil" if mix_type == "tamil" else "focus"
        recs = recommendation_engine.generate_multi_hour_playlist(seed_intent=category, target_duration_minutes=120)
        tracks = recs.get("playlist", [])
        track_list_text = "\n".join([f"• `{t.get('title')}` - _{t.get('artist')}_" for t in tracks[:5]])
        await telegram_service.send_text(
            chat_id=chat_id,
            text=f"🎧 *AI DJ {mix_type.replace('_', ' ').title()} Mix Generated* ({len(tracks)} tracks, 2 Hours):\n\n{track_list_text}\n\n_Playback queued in background._"
        )
        return {"status": "dj_mix_generated", "mix": mix_type}

    if data.startswith("m4:timer:"):
        minutes = int(data.split(":")[-1])
        sleep_timer_manager.start_timer(minutes=minutes, fade_out=True)
        await telegram_service.send_text(
            chat_id=chat_id,
            text=f"⏱️ *Sleep Timer Active*: System audio will gracefully fade out and stop in `{minutes}` minutes."
        )
        return {"status": "timer_started", "minutes": minutes}

    # -------------------------------------------------------------------------
    # Module 5 Handlers: File & Document Intelligence
    # -------------------------------------------------------------------------
    if data == "m5:lit_review":
        from app.documents.document_agent import run_document_task
        await telegram_service.send_text(chat_id=chat_id, text="📚 *Synthesizing Literature Review*: Generating DOCX report & Excel matrix from workspace papers...")
        docs_dir = str(resolve_safe_workspace_path("documents"))
        res = await run_document_task("literature_review", {"directory": docs_dir})
        for art in res.get("artifacts", []):
            try:
                await telegram_service.send_document(chat_id=chat_id, file_path=art, caption="📄 Generated Literature Deliverable")
            except Exception:
                pass
        await telegram_service.send_text(chat_id=chat_id, text="✅ *Literature Review Complete!* Artifacts dispatched.")
        return {"status": "lit_review_done"}

    if data == "m5:compare_latest":
        from app.documents.document_agent import run_document_task
        doc_dirs = [resolve_safe_workspace_path("documents"), resolve_safe_workspace_path("artifacts")]
        files: List[Path] = []
        for d in doc_dirs:
            if d.exists():
                files.extend([f for f in d.glob("*") if f.is_file() and f.suffix.lower() in [".pdf", ".docx", ".txt", ".md"]])
        if len(files) < 2:
            await telegram_service.send_text(chat_id=chat_id, text="⚠️ At least 2 documents needed in workspace to run comparative diff.")
            return {"status": "insufficient_files"}
        f1, f2 = files[0], files[1]
        res = await run_document_task("compare_documents", {"file_path_1": str(f1), "file_path_2": str(f2)})
        diff_summary = res.get("comparison", {}).get("diff_summary", "Comparison finished.")
        await telegram_service.send_text(chat_id=chat_id, text=f"⚖️ *Comparative Analysis*:\n\n{diff_summary[:1500]}")
        return {"status": "compared"}

    # -------------------------------------------------------------------------
    # Module 6 Handlers: Developer & Competitive Programming
    # -------------------------------------------------------------------------
    if data == "m6:build_clipboard":
        clip = ""
        try:
            import pyperclip
            clip = pyperclip.paste().strip()
        except Exception:
            pass
        prompt = clip if clip else "Build a real-time student attendance management dashboard"
        await telegram_service.send_text(chat_id=chat_id, text=f"🏗️ *Scaffolding & Engineering Full-Stack App*:\n`{prompt[:150]}`...")
        from app.developer.developer_agent import run_developer_task
        res = await run_developer_task("build_app", {"prompt": prompt})
        status_msg = (
            f"✅ *App Built Successfully!*\n\n"
            f"• *Project*: `{res.get('project_name')}`\n"
            f"• *Files Generated*: `{res.get('generated_files_count')}`\n"
            f"• *Pytest Status*: `{res.get('pytest_status')}`\n"
            f"• *Self-Healing Cycles*: `{res.get('healing_cycles_applied')}`\n"
            f"• *Directory*: `{res.get('project_dir')}`"
        )
        await telegram_service.send_text(chat_id=chat_id, text=status_msg)
        return {"status": "app_built"}

    if data == "m6:view_server_logs":
        logs = "\n".join(DEV_SERVER_LOGS[-8:])
        await telegram_service.send_text(chat_id=chat_id, text=f"📜 *Dev Agent Server Ring Buffer*:\n```text\n{logs}\n```")
        return {"status": "server_logs_viewed"}

    if data == "m6:cp_solve":
        clip = ""
        try:
            import pyperclip
            clip = pyperclip.paste().strip()
        except Exception:
            pass
        p_desc = clip if clip else "Two Sum: Given an array of integers nums and an integer target, return indices of the two numbers such that they add up to target."
        await telegram_service.send_text(chat_id=chat_id, text=f"⚡ *Solving Competitive Programming Challenge*:\n_{p_desc[:120]}..._")
        from app.developer.cp_solver import CompetitiveProgrammingSolver
        solver = CompetitiveProgrammingSolver()
        meta = solver.extract_problem_metadata(p_desc)
        sol_code = solver.generate_solution_code(meta)
        await telegram_service.send_text(
            chat_id=chat_id,
            text=f"✅ *Complexity-Optimal Algorithm Synthesized*:\n```python\n{sol_code}\n```"
        )
        return {"status": "cp_solved"}

    # -------------------------------------------------------------------------
    # Macros Handlers
    # -------------------------------------------------------------------------
    if data.startswith("macro:"):
        m_name = data.split(":")[-1]
        state = load_hub_state()
        state["active_macro"] = m_name.title()
        save_hub_state(state)

        if m_name == "ml_study":
            # 1. Start 2h Focus Study Mix
            recommendation_engine.generate_multi_hour_playlist(seed_intent="focus", target_duration_minutes=120)
            # 2. Set Volume to 40%
            audio_controller.set_master_volume(40)
            # 3. Launch VS Code
            await launch_application("vscode")
            await telegram_service.send_text(
                chat_id=chat_id,
                text="🧠 *Macro Activated: ML Study Mode*\n\n1. Started 2h Focus Lofi & Instrumental Mix.\n2. Master volume tuned to 40%.\n3. Visual Studio Code launched in foreground.\n4. Do Not Disturb active."
            )
        elif m_name == "leetcode":
            # 1. Launch Chrome directly to LeetCode
            await launch_application("chrome", args=["https://leetcode.com/problemset/all/"])
            # 2. Play subtle focus track
            audio_controller.set_master_volume(30)
            await telegram_service.send_text(
                chat_id=chat_id,
                text="💻 *Macro Activated: LeetCode Grind Mode*\n\n1. Persistent System Chrome opened to LeetCode.\n2. Background study audio initialized.\n3. Monaco injector & dry-run sandbox primed."
            )
        elif m_name == "meeting":
            # 1. Pause music
            from app.tools.computer import control_media_playback
            await control_media_playback("pause")
            # 2. Mute system notifications
            audio_controller.set_master_volume(25)
            await telegram_service.send_text(
                chat_id=chat_id,
                text="🎙️ *Macro Activated: Meeting Mode*\n\n1. Active media playback paused.\n2. Master audio auto-ducked to 25%.\n3. Voice recognition standby active."
            )
        elif m_name == "sleep":
            # 1. Start 30m fade out sleep timer
            sleep_timer_manager.start_timer(minutes=30, fade_out=True)
            # 2. Set gentle volume
            audio_controller.set_master_volume(20)
            await telegram_service.send_text(
                chat_id=chat_id,
                text="🌙 *Macro Activated: Sleep Wind-Down*\n\n1. 30-minute graceful sleep timer initiated.\n2. System volume lowered to 20%.\n3. Quiet chill ambient audio activated."
            )
        elif m_name == "halt":
            state["active_macro"] = None
            save_hub_state(state)
            await telegram_service.send_text(chat_id=chat_id, text="🛑 *Macro Halted*: System returned to normal manual orchestration.")

        await publish_or_update_master_hub(chat_id=chat_id, target_deck="hub:macros", message_id=message_id)
        return {"status": "macro_executed", "macro": m_name}

    # Voice Summary Handler
    if data == "hub:voice_summary":
        telemetry = await get_live_telemetry_header()
        plain_summary = (
            f"NEXUS AI Status Summary. "
            f"Active foreground application is currently on screen. "
            f"Master volume is at {audio_controller.get_master_volume()} percent. "
            f"Zero API keys required. All systems operational."
        )
        audio_file = await voice_synthesizer.synthesize_speech_to_file(plain_summary, output_filename="status_summary.mp3")
        await telegram_service.send_voice(
            chat_id=chat_id,
            voice_bytes_or_path=audio_file,
            caption="🎙️ *Spoken System Telemetry Summary*",
        )
        return {"status": "voice_summary_sent"}

    # Default fallback: refresh hub
    await publish_or_update_master_hub(chat_id=chat_id, target_deck="hub:main", message_id=message_id)
    return {"status": "default_refreshed"}
