import asyncio
import ctypes
import json
import logging
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, Any, List, Optional
from PIL import Image, ImageGrab
import psutil
import pyautogui

try:
    import win32gui
    import win32con
    import win32process
    import winreg
except ImportError:
    win32gui = None
    win32con = None
    win32process = None
    winreg = None

try:
    import pywinauto
    from pywinauto import Desktop
except ImportError:
    pywinauto = None
    Desktop = None

try:
    import pygetwindow as gw
except ImportError:
    gw = None

from app.core.security import resolve_safe_workspace_path
from app.core.hitl_gate import hitl_manager

logger = logging.getLogger(__name__)

# Configure PyAutoGUI thresholds
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.05

# ----------------------------------------------------------------------------
# Initialize Windows 11 Per-Monitor DPI Awareness
# ----------------------------------------------------------------------------
def _init_dpi_awareness():
    """Sets PROCESS_PER_MONITOR_DPI_AWARE (2) so mouse coordinates never drift on scaled displays."""
    if sys.platform == "win32":
        try:
            # 2 = PROCESS_PER_MONITOR_DPI_AWARE
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
            logger.info("[ComputerEngine] Windows Per-Monitor DPI Awareness (mode 2) initialized.")
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
                logger.info("[ComputerEngine] Legacy DPI Awareness initialized.")
            except Exception as e:
                logger.debug(f"[ComputerEngine] DPI awareness init note: {e}")

_init_dpi_awareness()


# ============================================================================
# 1. Native Windows & Cross-Platform Application Launcher & Short-Form Aliases
# ============================================================================

APP_ALIASES: Dict[str, Dict[str, Any]] = {
    # Browsers
    "chrome": {"canonical_name": "Google Chrome", "exe": "chrome.exe", "protocol": "chrome"},
    "gc": {"canonical_name": "Google Chrome", "exe": "chrome.exe", "protocol": "chrome"},
    "google": {"canonical_name": "Google Chrome", "exe": "chrome.exe", "protocol": "chrome"},
    "browser": {"canonical_name": "Google Chrome", "exe": "chrome.exe", "protocol": "chrome"},
    "edge": {"canonical_name": "Microsoft Edge", "exe": "msedge.exe", "protocol": "microsoft-edge:"},
    "msedge": {"canonical_name": "Microsoft Edge", "exe": "msedge.exe", "protocol": "microsoft-edge:"},
    "brave": {"canonical_name": "Brave", "exe": "brave.exe", "protocol": "brave"},
    "firefox": {"canonical_name": "Mozilla Firefox", "exe": "firefox.exe", "protocol": "firefox"},

    # Developer & Editors
    "vs": {"canonical_name": "Visual Studio Code", "exe": "Code.exe", "protocol": "code"},
    "vscode": {"canonical_name": "Visual Studio Code", "exe": "Code.exe", "protocol": "code"},
    "code": {"canonical_name": "Visual Studio Code", "exe": "Code.exe", "protocol": "code"},
    "cursor": {"canonical_name": "Cursor", "exe": "Cursor.exe", "protocol": "cursor"},
    "np": {"canonical_name": "Notepad", "exe": "notepad.exe", "protocol": "ms-notepad:"},
    "notepad": {"canonical_name": "Notepad", "exe": "notepad.exe", "protocol": "ms-notepad:"},
    "note": {"canonical_name": "Notepad", "exe": "notepad.exe", "protocol": "ms-notepad:"},
    "notes": {"canonical_name": "Notepad", "exe": "notepad.exe", "protocol": "ms-notepad:"},

    # Utilities & Windows System Apps
    "calc": {"canonical_name": "Calculator", "exe": "CalculatorApp.exe", "protocol": "calc:"},
    "calculator": {"canonical_name": "Calculator", "exe": "CalculatorApp.exe", "protocol": "calc:"},
    "cmd": {"canonical_name": "Command Prompt", "exe": "cmd.exe", "protocol": "cmd.exe"},
    "command prompt": {"canonical_name": "Command Prompt", "exe": "cmd.exe", "protocol": "cmd.exe"},
    "ps": {"canonical_name": "Windows PowerShell", "exe": "powershell.exe", "protocol": "powershell.exe"},
    "powershell": {"canonical_name": "Windows PowerShell", "exe": "powershell.exe", "protocol": "powershell.exe"},
    "term": {"canonical_name": "Windows Terminal", "exe": "wt.exe", "protocol": "wt.exe"},
    "terminal": {"canonical_name": "Windows Terminal", "exe": "wt.exe", "protocol": "wt.exe"},
    "wt": {"canonical_name": "Windows Terminal", "exe": "wt.exe", "protocol": "wt.exe"},
    "explorer": {"canonical_name": "File Explorer", "exe": "explorer.exe", "protocol": "explorer.exe"},
    "files": {"canonical_name": "File Explorer", "exe": "explorer.exe", "protocol": "explorer.exe"},
    "file manager": {"canonical_name": "File Explorer", "exe": "explorer.exe", "protocol": "explorer.exe"},
    "exp": {"canonical_name": "File Explorer", "exe": "explorer.exe", "protocol": "explorer.exe"},
    "my computer": {"canonical_name": "File Explorer", "exe": "explorer.exe", "protocol": "shell:MyComputerFolder"},
    "downloads": {"canonical_name": "Downloads", "exe": "explorer.exe", "protocol": "shell:Downloads"},
    "documents": {"canonical_name": "Documents", "exe": "explorer.exe", "protocol": "shell:Personal"},
    "settings": {"canonical_name": "Settings", "exe": "SystemSettings.exe", "protocol": "ms-settings:"},
    "config": {"canonical_name": "Settings", "exe": "SystemSettings.exe", "protocol": "ms-settings:"},
    "taskmgr": {"canonical_name": "Task Manager", "exe": "taskmgr.exe", "protocol": "taskmgr.exe"},
    "task manager": {"canonical_name": "Task Manager", "exe": "taskmgr.exe", "protocol": "taskmgr.exe"},
    "paint": {"canonical_name": "Paint", "exe": "mspaint.exe", "protocol": "mspaint.exe"},
    "mspaint": {"canonical_name": "Paint", "exe": "mspaint.exe", "protocol": "mspaint.exe"},
    "snip": {"canonical_name": "Snipping Tool", "exe": "SnippingTool.exe", "protocol": "ms-screensketch:"},
    "snipping tool": {"canonical_name": "Snipping Tool", "exe": "SnippingTool.exe", "protocol": "ms-screensketch:"},

    # Social & Chat
    "wa": {"canonical_name": "WhatsApp", "exe": "WhatsApp.exe", "protocol": "whatsapp:"},
    "whatsapp": {"canonical_name": "WhatsApp", "exe": "WhatsApp.exe", "protocol": "whatsapp:"},
    "tg": {"canonical_name": "Telegram", "exe": "Telegram.exe", "protocol": "tg:"},
    "telegram": {"canonical_name": "Telegram", "exe": "Telegram.exe", "protocol": "tg:"},
    "dc": {"canonical_name": "Discord", "exe": "Discord.exe", "protocol": "discord:"},
    "discord": {"canonical_name": "Discord", "exe": "Discord.exe", "protocol": "discord:"},

    # Media & Entertainment
    "spot": {"canonical_name": "Spotify", "exe": "Spotify.exe", "protocol": "spotify:"},
    "spotify": {"canonical_name": "Spotify", "exe": "Spotify.exe", "protocol": "spotify:"},
    "music": {"canonical_name": "Spotify", "exe": "Spotify.exe", "protocol": "spotify:"},
    "yt": {"canonical_name": "YouTube", "exe": "chrome.exe", "protocol": "https://www.youtube.com"},
    "youtube": {"canonical_name": "YouTube", "exe": "chrome.exe", "protocol": "https://www.youtube.com"},
    "ytm": {"canonical_name": "YouTube Music", "exe": "chrome.exe", "protocol": "https://music.youtube.com"},
    "yt music": {"canonical_name": "YouTube Music", "exe": "chrome.exe", "protocol": "https://music.youtube.com"},
    "youtube music": {"canonical_name": "YouTube Music", "exe": "chrome.exe", "protocol": "https://music.youtube.com"},
    "vlc": {"canonical_name": "VLC media player", "exe": "vlc.exe", "protocol": "vlc"},
    "obs": {"canonical_name": "OBS Studio", "exe": "obs64.exe", "protocol": "obs64.exe"},

    # Office Productivity
    "word": {"canonical_name": "Microsoft Word", "exe": "WINWORD.EXE", "protocol": "winword"},
    "winword": {"canonical_name": "Microsoft Word", "exe": "WINWORD.EXE", "protocol": "winword"},
    "doc": {"canonical_name": "Microsoft Word", "exe": "WINWORD.EXE", "protocol": "winword"},
    "excel": {"canonical_name": "Microsoft Excel", "exe": "EXCEL.EXE", "protocol": "excel"},
    "xl": {"canonical_name": "Microsoft Excel", "exe": "EXCEL.EXE", "protocol": "excel"},
    "xls": {"canonical_name": "Microsoft Excel", "exe": "EXCEL.EXE", "protocol": "excel"},
    "ppt": {"canonical_name": "Microsoft PowerPoint", "exe": "POWERPNT.EXE", "protocol": "powerpnt"},
    "powerpoint": {"canonical_name": "Microsoft PowerPoint", "exe": "POWERPNT.EXE", "protocol": "powerpnt"},
}

# Legacy backwards-compatibility map
COMMON_APP_MAP_WINDOWS = {k: v["protocol"] for k, v in APP_ALIASES.items()}

# Cache for 5-source app index with 5-minute TTL
_INSTALLED_APP_CACHE: List[Dict[str, Any]] = []
_INSTALLED_APP_CACHE_TIME: float = 0.0
_APP_CACHE_TTL_SECONDS: float = 300.0  # 5 minutes


def _build_installed_app_index(force_refresh: bool = False) -> List[Dict[str, Any]]:
    """
    Builds a unified index from ALL 5 Windows 11 application discovery sources:
    1. Registry 'App Paths' (HKLM & HKCU)
    2. Registry 'Uninstall' keys (HKLM, WOW6432Node, HKCU)
    3. PowerShell Get-StartApps (UWP / Microsoft Store apps)
    4. Start Menu .lnk shortcuts (ProgramData & AppData)
    5. PATH / shutil.which & standard Program Files directories
    """
    global _INSTALLED_APP_CACHE, _INSTALLED_APP_CACHE_TIME
    now = time.time()
    if not force_refresh and _INSTALLED_APP_CACHE and (now - _INSTALLED_APP_CACHE_TIME) < _APP_CACHE_TTL_SECONDS:
        return _INSTALLED_APP_CACHE

    discovered: List[Dict[str, Any]] = []
    seen_identifiers = set()

    def _add_app(name: str, exe_path: str, app_id: str, source_type: str):
        clean_n = name.strip()
        if not clean_n:
            return
        key = clean_n.lower()
        if key not in seen_identifiers:
            seen_identifiers.add(key)
            discovered.append({
                "name": clean_n,
                "executable_path": exe_path.strip(),
                "app_id": app_id.strip(),
                "type": source_type,
            })

    if sys.platform != "win32":
        return [{"name": "Mock System App", "executable_path": "/usr/bin/mock", "app_id": "mock.app", "type": "Mock"}]

    # --- SOURCE 1: Registry 'App Paths' (HKLM & HKCU) ---
    if winreg:
        for root_hkey, root_name in [(winreg.HKEY_LOCAL_MACHINE, "HKLM"), (winreg.HKEY_CURRENT_USER, "HKCU")]:
            try:
                sub_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"
                with winreg.OpenKey(root_hkey, sub_path) as parent_key:
                    num_subkeys = winreg.QueryInfoKey(parent_key)[0]
                    for i in range(num_subkeys):
                        try:
                            exe_key_name = winreg.EnumKey(parent_key, i)
                            with winreg.OpenKey(parent_key, exe_key_name) as app_key:
                                try:
                                    val, _ = winreg.QueryValueEx(app_key, "")
                                    exe_clean = str(val).strip().strip('"')
                                    app_name = exe_key_name.rsplit(".", 1)[0]
                                    _add_app(app_name, exe_clean, exe_key_name, f"Registry/AppPaths-{root_name}")
                                except Exception:
                                    pass
                        except Exception:
                            pass
            except Exception:
                pass

    # --- SOURCE 2: Registry 'Uninstall' Keys ---
    if winreg:
        reg_roots = [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall", "HKLM"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall", "HKLM-WOW64"),
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall", "HKCU"),
        ]
        for root, key_path, r_label in reg_roots:
            try:
                with winreg.OpenKey(root, key_path) as parent_key:
                    num_subkeys = winreg.QueryInfoKey(parent_key)[0]
                    for i in range(num_subkeys):
                        try:
                            subkey_name = winreg.EnumKey(parent_key, i)
                            with winreg.OpenKey(parent_key, subkey_name) as subkey:
                                try:
                                    disp_name, _ = winreg.QueryValueEx(subkey, "DisplayName")
                                    disp_str = str(disp_name).strip()
                                    if not disp_str:
                                        continue

                                    install_loc = ""
                                    display_icon = ""
                                    try:
                                        install_loc, _ = winreg.QueryValueEx(subkey, "InstallLocation")
                                    except Exception:
                                        pass
                                    try:
                                        display_icon, _ = winreg.QueryValueEx(subkey, "DisplayIcon")
                                    except Exception:
                                        pass

                                    exe_path = str(display_icon or install_loc or "").split(",")[0].strip('"')
                                    _add_app(disp_str, exe_path, subkey_name, f"Registry/Uninstall-{r_label}")
                                except Exception:
                                    pass
                        except Exception:
                            pass
            except Exception:
                pass

    # --- SOURCE 3: PowerShell Get-StartApps (UWP & Store Apps) ---
    try:
        cmd = "powershell -NoProfile -Command \"Get-StartApps | Select-Object Name, AppID | ConvertTo-Json\""
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=8)
        if res.returncode == 0 and res.stdout.strip():
            uwp_list = json.loads(res.stdout)
            if isinstance(uwp_list, dict):
                uwp_list = [uwp_list]
            for item in uwp_list:
                name = str(item.get("Name", "")).strip()
                app_id = str(item.get("AppID", "")).strip()
                if name:
                    _add_app(name, f"shell:AppsFolder\\{app_id}", app_id, "UWP/Store")
    except Exception as ps_err:
        logger.debug(f"[ComputerEngine] Get-StartApps note: {ps_err}")

    # --- SOURCE 4: Start Menu .lnk Shortcuts ---
    start_dirs = [
        Path(os.environ.get("ProgramData", "C:\\ProgramData")) / "Microsoft\\Windows\\Start Menu\\Programs",
        Path(os.environ.get("AppData", "C:\\Users\\ddnan\\AppData\\Roaming")) / "Microsoft\\Windows\\Start Menu\\Programs",
    ]
    for s_dir in start_dirs:
        if s_dir.exists():
            try:
                for lnk in s_dir.rglob("*.lnk"):
                    shortcut_name = lnk.stem.strip()
                    if shortcut_name:
                        _add_app(shortcut_name, str(lnk.resolve()), lnk.name, "StartMenu/Shortcut")
            except Exception:
                pass

    # --- SOURCE 5: Standard Installation Folders & PATH ---
    standard_paths = [
        Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / "Google\\Chrome\\Application\\chrome.exe",
        Path(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")) / "Google\\Chrome\\Application\\chrome.exe",
        Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / "Microsoft\\Edge\\Application\\msedge.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs\\Microsoft VS Code\\Code.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs\\Cursor\\Cursor.exe",
        Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / "VideoLAN\\VLC\\vlc.exe",
        Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / "obs-studio\\bin\\64bit\\obs64.exe",
    ]
    for std_exe in standard_paths:
        if std_exe and std_exe.exists():
            _add_app(std_exe.stem, str(std_exe.resolve()), std_exe.name, "StandardProgramFiles")

    _INSTALLED_APP_CACHE = discovered
    _INSTALLED_APP_CACHE_TIME = now
    return _INSTALLED_APP_CACHE


def resolve_app_query(query: str) -> Dict[str, Any]:
    """
    Intelligently resolves short forms, slang, abbreviations, and typos
    to canonical application names, launch targets, and process names.
    Uses APP_ALIASES, substring matching, and difflib fuzzy matching across the 5-source index.
    """
    clean_q = query.strip().lower()
    if not clean_q:
        return {
            "canonical_name": "Unknown",
            "launch_target": "",
            "process_names": [],
            "matched_via": "empty",
        }

    # 1. Exact or Clean Alias Resolution
    if clean_q in APP_ALIASES:
        info = APP_ALIASES[clean_q]
        exe = info["exe"]
        proc_names = [exe.lower(), exe.lower().replace(".exe", "")]
        if clean_q in APP_PROCESS_NAME_MAP:
            proc_names.extend(p.lower() for p in APP_PROCESS_NAME_MAP[clean_q])
        return {
            "canonical_name": info["canonical_name"],
            "launch_target": info["protocol"],
            "process_names": list(set(proc_names)),
            "matched_via": "exact_alias",
            "alias_info": info,
        }

    # 2. Check alias keys with fuzzy close matches FIRST before raw app names
    import difflib
    alias_keys = list(APP_ALIASES.keys())
    alias_matches = difflib.get_close_matches(clean_q, alias_keys, n=1, cutoff=0.55)
    if alias_matches:
        matched_key = alias_matches[0]
        info = APP_ALIASES[matched_key]
        exe = info["exe"]
        return {
            "canonical_name": info["canonical_name"],
            "launch_target": info["protocol"],
            "process_names": [exe.lower(), exe.lower().replace(".exe", "")],
            "matched_via": "fuzzy_alias",
            "alias_info": info,
        }

    # 3. Check 5-source installed app index for exact or prefix matches
    apps = _build_installed_app_index()
    for app in apps:
        n_low = app["name"].lower()
        if n_low == clean_q or n_low.startswith(f"{clean_q} ") or f" {clean_q} " in f" {n_low} ":
            exe = Path(app["executable_path"]).name if app.get("executable_path") else f"{clean_q}.exe"
            return {
                "canonical_name": app["name"],
                "launch_target": app["executable_path"] or app.get("app_id", clean_q),
                "process_names": [exe.lower(), exe.lower().replace(".exe", "")],
                "matched_via": "index_exact_or_prefix",
                "app_entry": app,
            }

    # 4. Substring matching in 5-source index
    for app in apps:
        n_low = app["name"].lower()
        if clean_q in n_low or clean_q in app.get("app_id", "").lower():
            exe = Path(app["executable_path"]).name if app.get("executable_path") else f"{clean_q}.exe"
            return {
                "canonical_name": app["name"],
                "launch_target": app["executable_path"] or app.get("app_id", clean_q),
                "process_names": [exe.lower(), exe.lower().replace(".exe", "")],
                "matched_via": "index_substring",
                "app_entry": app,
            }

    # 5. Fuzzy Matching across discovered app names
    app_names_map = {app["name"].lower(): app for app in apps}
    app_matches = difflib.get_close_matches(clean_q, list(app_names_map.keys()), n=1, cutoff=0.6)
    if app_matches:
        matched_app = app_names_map[app_matches[0]]
        exe = Path(matched_app["executable_path"]).name if matched_app.get("executable_path") else f"{clean_q}.exe"
        return {
            "canonical_name": matched_app["name"],
            "launch_target": matched_app["executable_path"] or matched_app.get("app_id", clean_q),
            "process_names": [exe.lower(), exe.lower().replace(".exe", "")],
            "matched_via": "fuzzy_index",
            "app_entry": matched_app,
        }

    # 6. Fallback clean query
    return {
        "canonical_name": query.strip(),
        "launch_target": clean_q,
        "process_names": [f"{clean_q}.exe", clean_q],
        "matched_via": "fallback",
    }


def resolve_app_alias(alias: str) -> str:
    """
    Resolves shorthand slang and partial aliases (e.g. 'gc', 'vs', 'np', 'wa', 'calc')
    to executable paths or system protocol targets using resolve_app_query.
    """
    resolution = resolve_app_query(alias)
    return resolution.get("launch_target") or alias.strip()



def _ensure_input_desktop() -> None:
    """Attaches current thread to active interactive Windows desktop station."""
    if sys.platform == "win32":
        try:
            import ctypes
            u32 = ctypes.windll.user32
            # Try Default desktop first (physical screen) then OpenInputDesktop
            hdesk = u32.OpenDesktopW("Default", 0, False, 0x01FF) or u32.OpenInputDesktop(0, False, 0x01FF)
            if hdesk:
                u32.SetThreadDesktop(hdesk)
        except Exception as exc:
            logger.debug(f"[ComputerEngine] Desktop attachment non-critical note: {exc}")


def get_active_spotify_window():
    """
    Finds the active Spotify window strictly by process name (`spotify.exe`),
    ignoring browser windows like Chrome or Edge that might mention Spotify.
    """
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        import psutil
        import pygetwindow as gw
        _ensure_input_desktop()
        u32 = ctypes.windll.user32

        for win in gw.getAllWindows():
            if not win._hWnd or not win.title.strip():
                continue
            pid = ctypes.c_ulong()
            u32.GetWindowThreadProcessId(win._hWnd, ctypes.byref(pid))
            if pid.value > 0:
                try:
                    pname = psutil.Process(pid.value).name().lower()
                    if "spotify" in pname:
                        return win
                except Exception:
                    pass
    except Exception as exc:
        logger.warning(f"[ComputerEngine] Spotify window lookup error: {exc}")
    return None


def force_window_foreground(title_pattern: str) -> bool:
    """
    Finds window matching title pattern on interactive desktop and forces it over all other windows
    using Win32 SW_RESTORE and SetForegroundWindow with pygetwindow fallback.
    For Spotify, checks both title and process name since playing songs replace the title with track names.
    """
    if sys.platform != "win32":
        return False

    try:
        import ctypes
        import psutil
        import pygetwindow as gw
        _ensure_input_desktop()
        u32 = ctypes.windll.user32

        pattern_clean = title_pattern.lower().replace(".exe", "").replace(":", "").strip()

        # 1. Dedicated Spotify Window Finder
        if pattern_clean in ("spotify", "music"):
            target_win = get_active_spotify_window()
            if target_win:
                u32.ShowWindow(target_win._hWnd, 9)  # 9 = SW_RESTORE
                u32.SetForegroundWindow(target_win._hWnd)
                try:
                    target_win.restore()
                    target_win.activate()
                except Exception:
                    pass
                logger.info(f"[ComputerEngine] Brought Spotify window to foreground: '{target_win.title}'")
                return True

            # If Spotify is not running, launch it
            try:
                spotify_procs = [p for p in psutil.process_iter(['name']) if 'spotify' in p.info['name'].lower()]
                if not spotify_procs:
                    os.startfile("spotify:")
                    time.sleep(2.0)
                target_win = get_active_spotify_window()
                if target_win:
                    u32.ShowWindow(target_win._hWnd, 9)
                    u32.SetForegroundWindow(target_win._hWnd)
                    target_win.restore()
                    target_win.activate()
                    return True
            except Exception as e:
                logger.warning(f"[ComputerEngine] Spotify launch note: {e}")
            return False

        # 2. General Windows
        for win in gw.getAllWindows():
            win_title = win.title.lower().strip()
            if not win_title:
                continue

            # Skip browser tabs when user didn't ask for a browser
            if pattern_clean not in ("chrome", "browser", "google") and ("google chrome" in win_title or "gemini" in win_title):
                continue

            is_match = (
                pattern_clean in win_title
                or (pattern_clean in ("calc", "calculator") and "calc" in win_title)
                or (pattern_clean in ("notepad", "ms-notepad") and ("notepad" in win_title or "untitled" in win_title))
                or (pattern_clean in ("chrome", "browser") and ("chrome" in win_title or "google" in win_title))
                or (pattern_clean in ("vscode", "code") and ("visual studio code" in win_title or "code" in win_title))
            )

            if is_match:
                u32.ShowWindow(win._hWnd, 9)  # 9 = SW_RESTORE
                u32.SetForegroundWindow(win._hWnd)
                try:
                    win.restore()
                    win.activate()
                except Exception:
                    pass
                logger.info(f"[ComputerEngine] Brought window to foreground: '{win.title}' (HWND {win._hWnd})")
                return True

        return False
    except Exception as exc:
        logger.warning(f"[ComputerEngine] Could not bring window '{title_pattern}' to foreground: {exc}")
    return False


def _bring_window_to_foreground(pattern: str) -> bool:
    return force_window_foreground(pattern)


async def launch_application(app_name: str, args: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Launches installed desktop application visibly on the user's interactive Windows desktop.
    Resolves short forms, abbreviations, slang, and typos using resolve_app_query.
    If called with a URL or search query for browser, delegates directly to browser.search_web.
    """
    clean_app = app_name.strip()

    # Delegate web queries directly to browser search engine
    if any(b in clean_app.lower() for b in ["chrome", "browser", "google"]) and args:
        arg_str = " ".join(args).strip()
        if arg_str.startswith("http://") or arg_str.startswith("https://"):
            from app.tools.browser import get_visible_chrome_page
            try:
                page = await get_visible_chrome_page()
                await page.goto(arg_str, timeout=15000, wait_until="domcontentloaded")
                await page.bring_to_front()
                return {"status": "success", "app": "chrome", "url": arg_str}
            except Exception as e:
                logger.warning(f"[ComputerEngine] Direct browser goto note: {e}")
        else:
            from app.tools.browser import search_web
            return await search_web(query=arg_str)

    resolution = resolve_app_query(clean_app)
    target = resolution.get("launch_target") or resolve_app_alias(clean_app)
    canonical = resolution.get("canonical_name", clean_app)

    logger.info(f"[ComputerEngine] Launching desktop application: '{target}' (resolved '{clean_app}' -> '{canonical}')")

    def _sync_launch():
        try:
            if sys.platform == "win32":
                # Special handling for file explorer
                if target in ("explorer.exe", "shell:MyComputerFolder") and (not args or len(args) == 0):
                    os.startfile("shell:MyComputerFolder")
                elif target.startswith("shell:") or target.endswith(":"):
                    os.startfile(target)
                elif shutil.which(target) or os.path.exists(target):
                    try:
                        os.startfile(target)
                    except Exception:
                        subprocess.Popen(f'start "" "{target}"', shell=True)
                else:
                    # Shell execution fallback
                    cmd_str = f'start "" "{target}"'
                    if args:
                        cmd_str += " " + " ".join(f'"{a}"' for a in args)
                    subprocess.Popen(cmd_str, shell=True)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", "-a", canonical] + (args or []))
            else:
                subprocess.Popen([target] + (args or []))

            return {"status": "success", "app": app_name, "resolved": canonical}
        except Exception as exc:
            logger.error(f"[ComputerEngine] Failed to launch application '{app_name}': {exc}")
            return {"status": "failed", "app": app_name, "error": str(exc)}

    res = await asyncio.to_thread(_sync_launch)

    if res.get("status") == "success":
        # Await GUI window creation and pop directly into foreground
        await asyncio.sleep(1.5)
        focused = await asyncio.to_thread(_bring_window_to_foreground, canonical)
        if not focused:
            focused = await asyncio.to_thread(_bring_window_to_foreground, clean_app)
        res["window_focused"] = focused
        res["message"] = f"Application '{canonical}' launched and rendered on screen."

    return res

    return res


async def list_active_windows() -> List[Dict[str, Any]]:
    """
    Enumerates open desktop windows with title, PID, and geometry on the active input desktop.
    """
    def _sync_list():
        windows = []
        try:
            _ensure_input_desktop()
            import pygetwindow as gw
            for win in gw.getAllWindows():
                if win.title.strip():
                    windows.append({
                        "title": win.title,
                        "left": win.left,
                        "top": win.top,
                        "width": win.width,
                        "height": win.height,
                        "is_active": win.isActive,
                    })
        except Exception as exc:
            logger.warning(f"[ComputerEngine] pygetwindow inspection note: {exc}")

        if not windows:
            windows.append({
                "title": "Desktop Session",
                "left": 0,
                "top": 0,
                "width": 1920,
                "height": 1080,
                "is_active": True,
            })
        return windows

    return await asyncio.to_thread(_sync_list)


async def focus_window(window_title_pattern: str) -> Dict[str, Any]:
    """
    Brings target application window matching title pattern to the foreground.
    """
    def _sync_focus():
        try:
            _ensure_input_desktop()
            import pygetwindow as gw
            candidates = [w for w in gw.getAllWindows() if window_title_pattern.lower() in w.title.lower()]
            if not candidates:
                return {"status": "not_found", "pattern": window_title_pattern}
            target = candidates[0]
            target.activate()
            return {"status": "success", "title": target.title}
        except Exception as exc:
            return {"status": "failed", "error": str(exc)}

    return await asyncio.to_thread(_sync_focus)


# Process / binary name resolution for application closing
APP_PROCESS_NAME_MAP = {
    "notepad": ["notepad.exe"],
    "note": ["notepad.exe"],
    "notes": ["notepad.exe"],
    "calculator": ["calculatorapp.exe", "calculator.exe", "calc.exe"],
    "calc": ["calculatorapp.exe", "calculator.exe", "calc.exe"],
    "chrome": ["chrome.exe"],
    "google chrome": ["chrome.exe"],
    "browser": ["chrome.exe", "msedge.exe"],
    "edge": ["msedge.exe"],
    "spotify": ["spotify.exe"],
    "music": ["spotify.exe"],
    "vlc": ["vlc.exe"],
    "vscode": ["code.exe"],
    "vs code": ["code.exe"],
    "code": ["code.exe"],
    "terminal": ["windowsterminal.exe", "wt.exe"],
    "wt": ["windowsterminal.exe", "wt.exe"],
    "cmd": ["cmd.exe"],
    "command prompt": ["cmd.exe"],
    "powershell": ["powershell.exe", "pwsh.exe"],
    "paint": ["mspaint.exe"],
    "task manager": ["taskmgr.exe"],
    "taskmgr": ["taskmgr.exe"],
    "explorer": ["explorer.exe"],
    "file explorer": ["explorer.exe"],
}


# ============================================================================
# MODULE 2: COMPLETE WINDOWS 11 DESKTOP AUTOMATION ENGINE
# ============================================================================

async def search_installed_apps(query: str = "") -> List[Dict[str, Any]]:
    """
    Scans the unified 5-source Windows 11 application index (Registry App Paths,
    Registry Uninstall keys, PowerShell Get-StartApps, Start Menu Shortcuts, and PATH/Standard dirs).
    Understands all short forms, abbreviations, slang, and typos.
    """
    clean_q = query.strip().lower()

    def _sync_search():
        if sys.platform != "win32":
            return [{"name": "Mock System App", "executable_path": "/usr/bin/mock", "app_id": "mock.app", "type": "Mock"}]

        all_apps = _build_installed_app_index()
        if not clean_q:
            return all_apps[:100]

        # 1. Resolve query via intelligent alias and fuzzy resolver
        resolution = resolve_app_query(clean_q)
        canonical_low = resolution.get("canonical_name", "").lower()
        matched_results = []
        seen = set()

        # Build alias tokens to match against installed apps
        alias_tokens = {clean_q, canonical_low}
        alias_info = resolution.get("alias_info") or APP_ALIASES.get(clean_q)
        if alias_info:
            alias_tokens.add(alias_info.get("canonical_name", "").lower())
            alias_tokens.add(alias_info.get("exe", "").lower())
            alias_tokens.add(alias_info.get("exe", "").lower().replace(".exe", ""))

        for app in all_apps:
            n_low = app["name"].lower()
            app_id_low = app.get("app_id", "").lower()
            exe_low = Path(app.get("executable_path", "")).name.lower()
            exe_base = exe_low.replace(".exe", "")

            # Check if any token matches
            matches_token = any(
                t in n_low or t == exe_low or t == exe_base or t in app_id_low
                for t in alias_tokens if len(t) > 1
            )
            if matches_token and n_low not in seen:
                seen.add(n_low)
                matched_results.append(app)

        # 2. If nothing found, try difflib fuzzy close matches across all app names
        if not matched_results:
            import difflib
            app_names = [a["name"] for a in all_apps]
            close = difflib.get_close_matches(clean_q, app_names, n=5, cutoff=0.5)
            for c_name in close:
                for app in all_apps:
                    if app["name"] == c_name and c_name.lower() not in seen:
                        seen.add(c_name.lower())
                        matched_results.append(app)

        # If still empty but resolution produced an alias entry
        if not matched_results and resolution.get("alias_info"):
            alias = resolution["alias_info"]
            matched_results.append({
                "name": alias["canonical_name"],
                "executable_path": alias["protocol"],
                "app_id": alias["exe"],
                "type": "SystemAlias/Protocol",
            })

        return matched_results[:100]

    return await asyncio.to_thread(_sync_search)


async def get_running_apps() -> List[Dict[str, Any]]:
    """
    Lists running desktop processes and active user-facing windows with PID,
    window title, and memory usage.
    """
    def _sync_running():
        running_apps = []
        open_windows = {}

        # Capture open window titles
        if sys.platform == "win32" and win32gui:
            def _enum_win(hwnd, extra):
                if win32gui.IsWindowVisible(hwnd):
                    title = win32gui.GetWindowText(hwnd).strip()
                    if title:
                        _, pid = win32process.GetWindowThreadProcessId(hwnd)
                        open_windows[pid] = title
                return True
            try:
                win32gui.EnumWindows(_enum_win, None)
            except Exception:
                pass

        for proc in psutil.process_iter(["pid", "name", "memory_percent", "status"]):
            try:
                p_info = proc.info
                pid = p_info["pid"]
                name = p_info["name"] or ""
                window_title = open_windows.get(pid)

                # Prioritize user-facing GUI windows or significant apps
                if window_title or name.lower().endswith(".exe"):
                    running_apps.append({
                        "pid": pid,
                        "name": name,
                        "window_title": window_title or "",
                        "is_visible_window": bool(window_title),
                        "memory_percent": round(proc.memory_percent(), 2) if hasattr(proc, "memory_percent") else 0.0,
                    })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        return running_apps

    return await asyncio.to_thread(_sync_running)


async def manage_window(app_title: str, action: str) -> Dict[str, Any]:
    """
    Controls desktop window geometry:
    Actions: 'minimize', 'maximize', 'restore', 'switch' (bring to foreground).
    Resolves short forms, abbreviations, and process names (e.g. 'np', 'gc', 'vs', 'calc').
    """
    clean_title = app_title.strip()
    clean_action = action.strip().lower()
    resolution = resolve_app_query(clean_title)
    canonical = resolution.get("canonical_name", clean_title)
    candidate_titles = {
        clean_title.lower(),
        canonical.lower(),
        clean_title.lower().replace(".exe", ""),
        canonical.lower().replace(".exe", ""),
    }
    for proc in resolution.get("process_names", []):
        candidate_titles.add(proc.lower().replace(".exe", ""))

    def _sync_manage():
        _ensure_input_desktop()
        if sys.platform != "win32" or not win32gui:
            return {"status": "simulated", "app_title": app_title, "action": clean_action}

        target_hwnd = None
        target_title = None

        def _find_hwnd(hwnd, extra):
            nonlocal target_hwnd, target_title
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd).strip()
                t_low = title.lower()
                if any(c in t_low for c in candidate_titles if len(c) > 1):
                    target_hwnd = hwnd
                    target_title = title
                    return False
            return True

        try:
            win32gui.EnumWindows(_find_hwnd, None)
        except Exception:
            pass

        # Fallback to pygetwindow search if Win32 EnumWindows missed it
        if not target_hwnd and gw:
            try:
                for win in gw.getAllWindows():
                    w_title = (win.title or "").strip().lower()
                    if w_title and any(c in w_title for c in candidate_titles if len(c) > 1):
                        target_hwnd = win._hWnd
                        target_title = win.title
                        break
            except Exception:
                pass

        if not target_hwnd:
            return {"status": "not_found", "app_title": app_title, "message": f"Window matching '{app_title}' ({canonical}) not found"}

        try:
            if clean_action in ("minimize", "min"):
                win32gui.ShowWindow(target_hwnd, win32con.SW_MINIMIZE)
            elif clean_action in ("maximize", "max"):
                win32gui.ShowWindow(target_hwnd, win32con.SW_MAXIMIZE)
            elif clean_action in ("restore", "normal"):
                win32gui.ShowWindow(target_hwnd, win32con.SW_RESTORE)
            elif clean_action in ("switch", "focus", "foreground"):
                win32gui.ShowWindow(target_hwnd, win32con.SW_RESTORE)
                win32gui.SetForegroundWindow(target_hwnd)
            else:
                return {"status": "error", "message": f"Unsupported window action: '{action}'"}

            return {
                "status": "success",
                "app_title": target_title,
                "action": clean_action,
                "hwnd": target_hwnd,
            }
        except Exception as exc:
            return {"status": "failed", "app_title": app_title, "error": str(exc)}

    return await asyncio.to_thread(_sync_manage)


async def install_application(package_id: str, chat_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Installs software via winget with mandatory HITL interactive approval gate.
    """
    clean_pkg = package_id.strip()
    target_chat = chat_id or "6663290532"

    # 1. Require Human-In-The-Loop Approval
    gate_id = hitl_manager.create_gate(
        action_name=f"Install Software: winget install {clean_pkg}",
        reason=f"Installing system package '{clean_pkg}' modifies system software registry and files.",
        chat_id=target_chat,
        details={"package_id": clean_pkg, "tool": "winget"},
    )

    logger.info(f"[ComputerEngine] Dispatched HITL approval gate {gate_id} for package '{clean_pkg}'")
    approved = await hitl_manager.request_and_wait_for_approval(gate_id, timeout_seconds=120)

    if not approved:
        logger.warning(f"[ComputerEngine] Installation of '{clean_pkg}' was REJECTED or timed out.")
        return {
            "status": "rejected",
            "package_id": clean_pkg,
            "message": f"Installation of package '{clean_pkg}' was denied by security approval gate.",
        }

    # 2. Execute winget install asynchronously upon explicit approval
    cmd = f'winget install --id "{clean_pkg}" --silent --accept-package-agreements --accept-source-agreements'
    logger.info(f"[ComputerEngine] Executing approved install: {cmd}")

    try:
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        exit_code = proc.returncode

        return {
            "status": "success" if exit_code == 0 else "failed",
            "package_id": clean_pkg,
            "exit_code": exit_code,
            "stdout": stdout.decode(errors="replace")[-1000:],
            "stderr": stderr.decode(errors="replace")[-500:],
        }
    except Exception as exc:
        return {"status": "failed", "package_id": clean_pkg, "error": str(exc)}


async def uninstall_application(package_id: str, chat_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Uninstalls software via winget with mandatory HITL interactive approval gate.
    """
    clean_pkg = package_id.strip()
    target_chat = chat_id or "6663290532"

    gate_id = hitl_manager.create_gate(
        action_name=f"Uninstall Software: winget uninstall {clean_pkg}",
        reason=f"Removing system package '{clean_pkg}' may delete files and dependencies.",
        chat_id=target_chat,
        details={"package_id": clean_pkg, "tool": "winget"},
    )

    approved = await hitl_manager.request_and_wait_for_approval(gate_id, timeout_seconds=120)
    if not approved:
        return {
            "status": "rejected",
            "package_id": clean_pkg,
            "message": f"Uninstallation of '{clean_pkg}' was rejected by user.",
        }

    cmd = f'winget uninstall --id "{clean_pkg}" --silent'
    try:
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        return {
            "status": "success" if proc.returncode == 0 else "failed",
            "package_id": clean_pkg,
            "exit_code": proc.returncode,
            "stdout": stdout.decode(errors="replace")[-1000:],
        }
    except Exception as exc:
        return {"status": "failed", "package_id": clean_pkg, "error": str(exc)}


async def detect_app_errors() -> List[Dict[str, Any]]:
    """
    Scans active desktop dialogs for crash popups, 'Not Responding' states
    (via IsHungAppWindow), or Windows error alerts.
    """
    def _sync_detect():
        _ensure_input_desktop()
        errors = []

        if sys.platform != "win32" or not win32gui:
            return errors

        # 1. Detect Hung Windows
        is_hung_fn = getattr(ctypes.windll.user32, "IsHungAppWindow", None)

        def _check_hung(hwnd, extra):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd).strip()
                if title:
                    if is_hung_fn and is_hung_fn(hwnd):
                        errors.append({
                            "type": "Not Responding (Hung Window)",
                            "hwnd": hwnd,
                            "title": title,
                        })
                    elif any(e in title.lower() for e in ["error", "crash", "has stopped working", "not responding", "fatal"]):
                        errors.append({
                            "type": "Error/Crash Dialog",
                            "hwnd": hwnd,
                            "title": title,
                        })
            return True

        try:
            win32gui.EnumWindows(_check_hung, None)
        except Exception:
            pass

        return errors

    detected = await asyncio.to_thread(_sync_detect)
    return detected


async def control_app_ui(
    window_title: str,
    control_name: str,
    action: str = "click",
    value: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Controls desktop app UI elements (buttons, checkboxes, inputs) using pywinauto MS UI Automation.
    """
    def _sync_ui():
        _ensure_input_desktop()
        if not pywinauto or not Desktop:
            return {"status": "failed", "error": "pywinauto not available"}

        try:
            desktop = Desktop(backend="uia")
            # Connect to matching window
            win = desktop.window(title_re=f".*{window_title}.*", visible_only=True)
            if not win.exists(timeout=3):
                return {"status": "not_found", "message": f"Window matching '{window_title}' not found"}

            ctrl = win.child_window(title_re=f".*{control_name}.*", visible_only=True)
            if not ctrl.exists(timeout=3):
                return {"status": "not_found", "message": f"Control '{control_name}' not found inside '{window_title}'"}

            act_clean = action.lower()
            if act_clean in ("click", "press"):
                ctrl.click_input()
            elif act_clean in ("set_text", "type"):
                ctrl.set_text(value or "")
            elif act_clean in ("toggle", "check"):
                ctrl.toggle()
            else:
                ctrl.click_input()

            return {
                "status": "success",
                "window": window_title,
                "control": control_name,
                "action": action,
            }
        except Exception as exc:
            return {"status": "failed", "error": str(exc)}

    return await asyncio.to_thread(_sync_ui)


async def mouse_action(
    action: str = "click",
    x: Optional[int] = None,
    y: Optional[int] = None,
    button: str = "left",
    clicks: int = 1,
    delta_y: int = 0,
) -> Dict[str, Any]:
    """
    Executes DPI-aware mouse control: click, double_click, right_click, drag, scroll.
    """
    def _sync_mouse():
        _ensure_input_desktop()
        try:
            act_clean = action.lower()
            if x is not None and y is not None:
                pyautogui.moveTo(x, y)

            if act_clean == "click":
                pyautogui.click(button=button, clicks=clicks)
            elif act_clean == "double_click":
                pyautogui.doubleClick(button=button)
            elif act_clean == "right_click":
                pyautogui.rightClick()
            elif act_clean == "scroll":
                pyautogui.scroll(delta_y)
            return {"status": "success", "action": action, "x": x, "y": y}
        except Exception as exc:
            return {"status": "failed", "error": str(exc)}

    return await asyncio.to_thread(_sync_mouse)


async def keyboard_action(
    action: str = "hotkey",
    keys: Optional[List[str]] = None,
    text: Optional[str] = None,
    press_enter: bool = True,
) -> Dict[str, Any]:
    """
    Executes DPI-aware keyboard control: hotkey, type_text.
    """
    def _sync_key():
        _ensure_input_desktop()
        try:
            act_clean = action.lower()
            if act_clean == "hotkey" and keys:
                pyautogui.hotkey(*keys)
                return {"status": "success", "action": "hotkey", "keys": keys}
            elif act_clean in ("type", "type_text") and text:
                pyautogui.write(text, interval=0.02)
                if press_enter:
                    pyautogui.press("enter")
                return {"status": "success", "action": "type_text", "length": len(text)}
            return {"status": "success", "action": action}
        except Exception as exc:
            return {"status": "failed", "error": str(exc)}

    return await asyncio.to_thread(_sync_key)


async def close_application(process_name_or_title: str, force: bool = False) -> Dict[str, Any]:
    """
    Closes open GUI applications cleanly via WM_CLOSE (window.close()),
    falling back to psutil.Process.terminate() when force=True or if the process remains active.
    Resolves short forms, abbreviations, slang, and typos using resolve_app_query.
    """
    clean_target = process_name_or_title.strip()
    resolution = resolve_app_query(clean_target)
    canonical = resolution.get("canonical_name", clean_target)
    
    def _sync_close():
        candidates = set()
        clean_low = clean_target.lower()
        clean_no_ext = clean_low.replace(".exe", "")
        canonical_low = canonical.lower()
        canonical_no_ext = canonical_low.replace(".exe", "")

        candidates.add(clean_no_ext)
        candidates.add(clean_low)
        candidates.add(canonical_no_ext)
        candidates.add(canonical_low)

        # Add all process names from resolution
        for p in resolution.get("process_names", []):
            p_low = p.lower()
            candidates.add(p_low)
            candidates.add(p_low.replace(".exe", ""))

        # Check alias process mapping
        if clean_low in APP_PROCESS_NAME_MAP:
            for p in APP_PROCESS_NAME_MAP[clean_low]:
                candidates.add(p.lower().replace(".exe", ""))
                candidates.add(p.lower())

        if canonical_low in APP_PROCESS_NAME_MAP:
            for p in APP_PROCESS_NAME_MAP[canonical_low]:
                candidates.add(p.lower().replace(".exe", ""))
                candidates.add(p.lower())

        # Also check alias resolution from COMMON_APP_MAP_WINDOWS
        resolved = resolve_app_alias(clean_low).lower()
        resolved_no_ext = resolved.replace(".exe", "").replace(":", "")
        candidates.add(resolved_no_ext)

        logger.info(f"[ComputerEngine] Closing application '{clean_target}' ({canonical}, force={force}) matching: {candidates}")

        terminated = []

        # 1. Graceful Window Close first (WM_CLOSE via pygetwindow) if not force
        if not force:
            try:
                _ensure_input_desktop()
                import pygetwindow as gw
                for win in gw.getAllWindows():
                    w_title = win.title.strip().lower()
                    if w_title and any(c in w_title for c in candidates if len(c) > 1):
                        try:
                            win.close()
                            terminated.append({"pid": win._hWnd, "name": win.title, "method": "graceful_wm_close"})
                        except Exception:
                            pass
            except Exception as w_err:
                logger.debug(f"[ComputerEngine] Graceful close note: {w_err}")

        # 2. Terminate running process via psutil if force=True or if no windows closed
        if force or not terminated:
            for proc in psutil.process_iter(["pid", "name"]):
                try:
                    p_name = (proc.info["name"] or "").lower()
                    p_base = p_name.replace(".exe", "")
                    if any(c in p_base or c in p_name for c in candidates if len(c) > 1):
                        if p_name == "explorer.exe" and clean_target not in ("explorer", "explorer.exe"):
                            continue
                        proc.terminate()
                        terminated.append({"pid": proc.info["pid"], "name": p_name, "method": "psutil_terminate"})
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

        # Wait briefly for process cleanup
        if terminated and sys.platform == "win32":
            time.sleep(0.5)

        return {
            "status": "success" if terminated else "not_found",
            "app_target": clean_target,
            "force": force,
            "terminated_count": len(terminated),
            "processes": terminated,
            "message": f"Closed {len(terminated)} instance(s) of '{clean_target}'." if terminated else f"No active window or process found for '{clean_target}'."
        }

    return await asyncio.to_thread(_sync_close)


# ============================================================================
# 2. GUI Interaction Engine (Mouse & Keyboard)
# ============================================================================

async def send_hotkey(keys: List[str]) -> Dict[str, Any]:
    """
    Simulates pressing arbitrary OS keyboard combinations (e.g., ['win', 'd'], ['alt', 'tab']).
    """
    logger.info(f"[ComputerEngine] Sending hotkey sequence: {keys}")

    def _sync_hotkey():
        try:
            _ensure_input_desktop()
            pyautogui.hotkey(*keys)
            return {"status": "success", "keys": keys}
        except Exception as exc:
            return {"status": "failed", "error": str(exc)}

    return await asyncio.to_thread(_sync_hotkey)


async def type_text(text: str, interval: float = 0.02, press_enter: bool = True) -> Dict[str, Any]:
    """
    Types text into the currently active focused window field.
    """
    def _sync_type():
        try:
            _ensure_input_desktop()
            pyautogui.write(text, interval=interval)
            if press_enter:
                pyautogui.press("enter")
            return {"status": "success", "typed_length": len(text)}
        except Exception as exc:
            return {"status": "failed", "error": str(exc)}

    return await asyncio.to_thread(_sync_type)


async def click_coordinate(x: int, y: int, button: str = "left", clicks: int = 1) -> Dict[str, Any]:
    """
    Clicks at exact screen pixel coordinates (x, y).
    """
    def _sync_click():
        try:
            _ensure_input_desktop()
            pyautogui.click(x=x, y=y, clicks=clicks, button=button)
            return {"status": "success", "x": x, "y": y, "button": button}
        except Exception as exc:
            return {"status": "failed", "error": str(exc)}

    return await asyncio.to_thread(_sync_click)


async def drag_mouse(start_x: int, start_y: int, end_x: int, end_y: int, duration: float = 0.5) -> Dict[str, Any]:
    """
    Drags mouse cursor from start to end coordinates.
    """
    def _sync_drag():
        try:
            _ensure_input_desktop()
            pyautogui.moveTo(start_x, start_y)
            pyautogui.dragTo(end_x, end_y, duration=duration, button="left")
            return {"status": "success", "from": (start_x, start_y), "to": (end_x, end_y)}
        except Exception as exc:
            return {"status": "failed", "error": str(exc)}

    return await asyncio.to_thread(_sync_drag)


async def get_screen_geometry() -> Dict[str, Any]:
    """
    Detects screen resolution and multi-monitor layouts, normalizing DPI scaling
    for accurate coordinate calculations.
    """
    def _sync_geom():
        try:
            _ensure_input_desktop()
            size = pyautogui.size()
            width, height = size.width, size.height
            monitors = [{"monitor": 1, "width": width, "height": height, "primary": True}]

            # Detect secondary monitors via win32api if available
            if sys.platform == "win32":
                try:
                    import win32api
                    enum_monitors = win32api.EnumDisplayMonitors()
                    if enum_monitors and len(enum_monitors) > 0:
                        monitors = []
                        for idx, (hmon, hdc, rect) in enumerate(enum_monitors, 1):
                            mon_w = rect[2] - rect[0]
                            mon_h = rect[3] - rect[1]
                            monitors.append({
                                "monitor": idx,
                                "left": rect[0],
                                "top": rect[1],
                                "width": mon_w,
                                "height": mon_h,
                                "primary": idx == 1,
                            })
                except Exception as mon_err:
                    logger.debug(f"[ComputerEngine] Multi-monitor inspection note: {mon_err}")

            return {
                "status": "success",
                "primary_resolution": {"width": width, "height": height},
                "total_monitors": len(monitors),
                "monitors": monitors,
            }
        except Exception as exc:
            logger.error(f"[ComputerEngine] Screen geometry check failed: {exc}")
            return {
                "status": "failed",
                "primary_resolution": {"width": 1920, "height": 1080},
                "total_monitors": 1,
                "error": str(exc),
            }

    return await asyncio.to_thread(_sync_geom)


async def click_visual_element(
    template_image_path: Optional[str] = None,
    text_label: Optional[str] = None,
    confidence: float = 0.8,
) -> Dict[str, Any]:
    """
    Locates an on-screen element using template matching (OpenCV/PyAutoGUI) or Vision OCR,
    and executes a click at the center coordinates.
    """
    def _sync_visual_click():
        try:
            _ensure_input_desktop()
            # 1. Template image matching
            if template_image_path and os.path.exists(template_image_path):
                location = pyautogui.locateOnScreen(template_image_path, confidence=confidence)
                if location:
                    center_point = pyautogui.center(location)
                    pyautogui.click(center_point.x, center_point.y)
                    return {
                        "status": "success",
                        "method": "template_match",
                        "coordinates": {"x": center_point.x, "y": center_point.y},
                        "template": template_image_path,
                    }

            # 2. Heuristic fallback / center click
            screen_w, screen_h = pyautogui.size()
            mid_x, mid_y = screen_w // 2, screen_h // 2
            return {
                "status": "fallback",
                "method": "default_anchor",
                "coordinates": {"x": mid_x, "y": mid_y},
                "label": text_label or "visual_anchor",
                "message": "Template match not found; anchored to screen reference.",
            }
        except Exception as exc:
            logger.warning(f"[ComputerEngine] Visual element click error: {exc}")
            return {"status": "failed", "error": str(exc)}

    return await asyncio.to_thread(_sync_visual_click)


async def scroll(clicks: int, direction: str = "down") -> Dict[str, Any]:
    """
    Simulates mouse wheel scrolling up or down.
    """
    def _sync_scroll():
        try:
            _ensure_input_desktop()
            amount = -abs(clicks) if direction.lower() == "down" else abs(clicks)
            pyautogui.scroll(amount)
            return {"status": "success", "clicks": amount, "direction": direction}
        except Exception as exc:
            return {"status": "failed", "error": str(exc)}

    return await asyncio.to_thread(_sync_scroll)


# ============================================================================
# 3. Desktop Vision & Media Control
# ============================================================================

async def capture_desktop_screenshot(filename: str = "desktop_state.png", region: Optional[List[int]] = None) -> str:
    """
    Captures entire desktop or subregion and saves to ./workspace/.
    Enforces sandbox path isolation, window settle delays, and handles headless displays with virtual canvas fallback.
    """
    safe_path = resolve_safe_workspace_path(filename)
    safe_path.parent.mkdir(parents=True, exist_ok=True)

    # Window animation / paint settle delay before screen grab
    await asyncio.sleep(0.75)

    def _sync_capture():
        try:
            _ensure_input_desktop()
            bbox = tuple(region) if region and len(region) == 4 else None
            shot = ImageGrab.grab(bbox=bbox)
            shot.save(str(safe_path), "PNG")
            return str(safe_path)
        except Exception as exc:
            logger.warning(f"[ComputerEngine] Screen grab note ({exc}); creating virtual frame.")
            canvas = Image.new("RGB", (1920, 1080), color=(25, 25, 25))
            canvas.save(str(safe_path), "PNG")
            return str(safe_path)

    saved_path = await asyncio.to_thread(_sync_capture)
    logger.info(f"[ComputerEngine] Desktop screenshot captured: {saved_path}")
    return saved_path


MEDIA_KEY_MAP = {
    "play": "playpause",
    "pause": "playpause",
    "stop": "playpause",
    "play_pause": "playpause",
    "resume": "playpause",
    "next": "nexttrack",
    "next_song": "nexttrack",
    "skip": "nexttrack",
    "previous": "prevtrack",
    "previous_song": "prevtrack",
    "prev": "prevtrack",
    "backward": "prevtrack",
    "mute": "volumemute",
    "unmute": "volumemute",
    "volume_up": "volumeup",
    "volume_down": "volumedown",
    "louder": "volumeup",
    "lower": "volumedown",
}


async def control_music_playback(
    action: str,
    app_focus: Optional[str] = None,
    value: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Specialized Music Controller:
    Sends native media hotkeys, brings target music players (Spotify, YT Music, VLC, Chrome) to foreground,
    and returns now playing status.
    """
    act_clean = action.lower().replace("-", "_").replace(" ", "_")
    logger.info(f"[ComputerEngine] Music control: action='{act_clean}', app='{app_focus}', value={value}")

    def _sync_control():
        try:
            _ensure_input_desktop()
            # 1. Bring player window to focus if specified
            if app_focus:
                force_window_foreground(app_focus)
                time.sleep(0.2)

            # 2. Volume control
            if act_clean in ("volume_up", "louder", "increase_volume"):
                steps = value or 4
                for _ in range(steps):
                    pyautogui.press("volumeup")
                    time.sleep(0.04)
                return {"status": "success", "action": "volume_up", "steps": steps}

            if act_clean in ("volume_down", "lower", "decrease_volume"):
                steps = value or 4
                for _ in range(steps):
                    pyautogui.press("volumedown")
                    time.sleep(0.04)
                return {"status": "success", "action": "volume_down", "steps": steps}

            if act_clean in ("mute", "unmute", "toggle_mute"):
                pyautogui.press("volumemute")
                return {"status": "success", "action": "mute"}

            if act_clean in ("next", "next_song", "skip", "next_track"):
                pyautogui.press("nexttrack")
                return {"status": "success", "action": "next"}

            if act_clean in ("previous", "previous_song", "prev", "prev_track", "backward"):
                pyautogui.press("prevtrack")
                return {"status": "success", "action": "previous"}

            # Default: Play/Pause toggle
            key = MEDIA_KEY_MAP.get(act_clean, "playpause")
            pyautogui.press(key)

            # Retrieve active track name if Spotify is playing
            track_info = "Active Player"
            spotify_win = get_active_spotify_window()
            if spotify_win and " - " in spotify_win.title:
                track_info = spotify_win.title.replace("Spotify - ", "").strip()

            return {
                "status": "success",
                "action": act_clean,
                "key_pressed": key,
                "now_playing": track_info,
            }
        except Exception as exc:
            logger.error(f"[ComputerEngine] Music control error: {exc}")
            return {"status": "failed", "action": action, "error": str(exc)}

    return await asyncio.to_thread(_sync_control)


async def control_media_playback(action: str) -> Dict[str, Any]:
    """
    Sends native OS media playback commands across Spotify and all media apps:
    play/pause, stop, next/skip, previous, forward, rewind, volume adjustments, shuffle, and repeat.
    """
    act_clean = action.lower().replace("-", "_").replace(" ", "_")

    def _sync_media():
        try:
            _ensure_input_desktop()
            pyautogui.FAILSAFE = False

            # Specialized Spotify shortcuts when Spotify is focused
            if act_clean in ("shuffle", "toggle_shuffle"):
                force_window_foreground("spotify")
                time.sleep(0.2)
                pyautogui.hotkey("ctrl", "s")
                return {"status": "success", "action": "shuffle", "message": "Toggled Spotify Shuffle."}

            if act_clean in ("repeat", "toggle_repeat"):
                force_window_foreground("spotify")
                time.sleep(0.2)
                pyautogui.hotkey("ctrl", "r")
                return {"status": "success", "action": "repeat", "message": "Toggled Spotify Repeat mode."}

            if act_clean in ("forward", "seek_forward", "fast_forward"):
                force_window_foreground("spotify")
                time.sleep(0.2)
                pyautogui.hotkey("shift", "right")
                return {"status": "success", "action": "seek_forward", "message": "Seeked forward 5 seconds."}

            if act_clean in ("rewind", "seek_backward", "seek_back"):
                force_window_foreground("spotify")
                time.sleep(0.2)
                pyautogui.hotkey("shift", "left")
                return {"status": "success", "action": "seek_backward", "message": "Rewound backward 5 seconds."}

            if act_clean in ("volume_up", "louder", "increase_volume"):
                for _ in range(4):
                    pyautogui.press("volumeup")
                    time.sleep(0.05)
                return {"status": "success", "action": "volume_up", "message": "Increased volume."}

            if act_clean in ("volume_down", "lower", "decrease_volume"):
                for _ in range(4):
                    pyautogui.press("volumedown")
                    time.sleep(0.05)
                return {"status": "success", "action": "volume_down", "message": "Decreased volume."}

            if act_clean in ("next", "next_song", "skip", "next_track"):
                pyautogui.press("nexttrack")
                return {"status": "success", "action": "next", "message": "Skipped to next track."}

            if act_clean in ("previous", "previous_song", "prev", "prev_track", "backward"):
                pyautogui.press("prevtrack")
                return {"status": "success", "action": "previous", "message": "Returned to previous track."}

            # Default: Play / Pause / Stop
            key = MEDIA_KEY_MAP.get(act_clean, "playpause")
            pyautogui.press(key)
            return {"status": "success", "action": action, "key_pressed": key, "message": f"Media command '{action}' triggered."}

        except Exception as exc:
            return {"status": "failed", "action": action, "error": str(exc)}

    return await asyncio.to_thread(_sync_media)


async def play_spotify_music(
    song: Optional[str] = None,
    playlist: Optional[str] = None,
    artist: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Navigates and starts playback in Spotify for a song, playlist, or liked songs.
    Uses Spotify URI protocol triggers, foreground focus, and active keyboard navigation (Ctrl+K -> query -> Tab -> Enter).
    """
    logger.info(f"[ComputerEngine] Playing Spotify music: song='{song}', playlist='{playlist}', artist='{artist}'")

    def _sync_spotify():
        try:
            _ensure_input_desktop()
            pyautogui.FAILSAFE = False

            query_parts = []
            if song:
                query_parts.append(song)
            if artist:
                query_parts.append(artist)
            full_query = " ".join(query_parts).strip()

            is_liked_songs = playlist and any(k in playlist.lower() for k in ("liked", "favorites", "favorite"))

            query_parts = []
            if song:
                query_parts.append(song)
            if artist:
                query_parts.append(artist)
            if playlist and not is_liked_songs:
                query_parts.append(playlist)
            full_query = " ".join(query_parts).strip()

            # 1. Ensure Spotify window exists and bring to foreground
            force_window_foreground("spotify")
            time.sleep(0.5)

            # 2. Liked Songs playlist navigation
            if is_liked_songs and not full_query:
                try:
                    os.startfile("spotify:collection:tracks")
                except Exception:
                    subprocess.Popen('start "" "spotify:collection:tracks"', shell=True)
                time.sleep(1.2)
                force_window_foreground("spotify")
                time.sleep(0.4)
                pyautogui.press("tab")
                time.sleep(0.2)
                pyautogui.press("enter")
                time.sleep(0.3)
                pyautogui.press("down")
                time.sleep(0.2)
                pyautogui.press("enter")
                time.sleep(0.2)
                pyautogui.press("playpause")
                track_title = "Liked Songs"
            elif is_liked_songs and full_query:
                # Open Liked Songs collection and filter
                try:
                    os.startfile("spotify:collection:tracks")
                except Exception:
                    subprocess.Popen('start "" "spotify:collection:tracks"', shell=True)
                time.sleep(1.2)
                force_window_foreground("spotify")
                time.sleep(0.4)
                pyautogui.hotkey("ctrl", "f")
                time.sleep(0.3)
                pyautogui.write(full_query, interval=0.02)
                time.sleep(0.5)
                pyautogui.press("enter")
                time.sleep(0.3)
                pyautogui.press("down")
                time.sleep(0.2)
                pyautogui.press("enter")
                time.sleep(0.2)
                pyautogui.press("playpause")
                track_title = f"{full_query} (Liked Songs)"
            elif full_query:
                # Global track search in Spotify
                force_window_foreground("spotify")
                time.sleep(0.4)
                # Open search bar in Spotify
                pyautogui.hotkey("ctrl", "k")
                time.sleep(0.4)
                pyautogui.hotkey("ctrl", "a")
                time.sleep(0.1)
                pyautogui.write(full_query, interval=0.02)
                time.sleep(0.5)
                pyautogui.press("enter")
                # Wait for search results to render
                time.sleep(1.2)

                # Fetch Spotify window position to perform precise clicks
                spotify_win = get_active_spotify_window()
                if spotify_win and spotify_win.width > 300 and spotify_win.height > 300:
                    w_left = spotify_win.left
                    w_top = spotify_win.top
                    w_w = spotify_win.width
                    w_h = spotify_win.height

                    # 1. Double click the #1 song in the Songs result table
                    song_row_x = w_left + int(w_w * 0.58)
                    song_row_y = w_top + int(w_h * 0.35)
                    pyautogui.doubleClick(song_row_x, song_row_y)
                    time.sleep(0.4)

                    # 2. Backup double click the Top Result big card
                    top_card_x = w_left + int(w_w * 0.32)
                    top_card_y = w_top + int(w_h * 0.32)
                    pyautogui.doubleClick(top_card_x, top_card_y)
                    time.sleep(0.4)

                # 3. Native keyboard trigger: Unfocus search input and trigger immediate playback
                pyautogui.press("escape")
                time.sleep(0.2)
                pyautogui.press("enter")
                time.sleep(0.5)

                track_title = full_query
            else:
                # Just play/resume current queue
                pyautogui.press("playpause")
                track_title = "Active Spotify Queue"

            # Check if Spotify window title updated with active track
            now_playing = track_title
            try:
                import pygetwindow as gw
                for w in gw.getAllWindows():
                    if "spotify" in w.title.lower() and " - " in w.title:
                        now_playing = w.title.replace("Spotify - ", "").strip()
                        break
            except Exception:
                pass

            return {
                "status": "success",
                "app": "spotify",
                "action": "play_music",
                "song": song or full_query,
                "playlist": playlist,
                "now_playing": now_playing,
                "message": f"Playback started: '{now_playing}'",
            }
        except Exception as exc:
            logger.error(f"[ComputerEngine] Spotify playback error: {exc}")
            return {"status": "failed", "app": "spotify", "error": str(exc)}

    return await asyncio.to_thread(_sync_spotify)

