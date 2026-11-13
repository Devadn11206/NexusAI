"""
NEXUS AI - Repository Application & Tool Registry Scanner
Inspects codebase app maps, tool definitions, and system configurations to dynamically
extract all supported desktop applications with metadata for the Telegram Control Center.
"""

import inspect
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

# Fallback emoji and category associations for common application keys
APP_METADATA_DECORATORS = {
    "chrome": {"display_name": "Google Chrome", "emoji": "🌐", "category": "Browsers"},
    "browser": {"display_name": "Default Web Browser", "emoji": "🌍", "category": "Browsers"},
    "google chrome": {"display_name": "Google Chrome", "emoji": "🌐", "category": "Browsers"},
    "vscode": {"display_name": "Visual Studio Code", "emoji": "💻", "category": "IDEs & Editors"},
    "vs code": {"display_name": "VS Code", "emoji": "💻", "category": "IDEs & Editors"},
    "code": {"display_name": "VS Code", "emoji": "💻", "category": "IDEs & Editors"},
    "notepad": {"display_name": "Notepad", "emoji": "📝", "category": "IDEs & Editors"},
    "notepad.exe": {"display_name": "Notepad", "emoji": "📝", "category": "IDEs & Editors"},
    "terminal": {"display_name": "Windows Terminal", "emoji": "⚡", "category": "Utilities"},
    "wt": {"display_name": "Windows Terminal", "emoji": "⚡", "category": "Utilities"},
    "cmd": {"display_name": "Command Prompt", "emoji": "⬛", "category": "Utilities"},
    "command prompt": {"display_name": "Command Prompt", "emoji": "⬛", "category": "Utilities"},
    "powershell": {"display_name": "PowerShell", "emoji": "🔷", "category": "Utilities"},
    "calculator": {"display_name": "Calculator", "emoji": "🔢", "category": "Utilities"},
    "calc": {"display_name": "Calculator", "emoji": "🔢", "category": "Utilities"},
    "explorer": {"display_name": "File Explorer", "emoji": "📁", "category": "Files"},
    "file explorer": {"display_name": "File Explorer", "emoji": "📁", "category": "Files"},
    "files": {"display_name": "File Explorer", "emoji": "📁", "category": "Files"},
    "my computer": {"display_name": "This PC", "emoji": "🖥️", "category": "Files"},
    "downloads": {"display_name": "Downloads Folder", "emoji": "📥", "category": "Files"},
    "documents": {"display_name": "Documents Folder", "emoji": "📂", "category": "Files"},
    "spotify": {"display_name": "Spotify Music", "emoji": "🎵", "category": "Media"},
    "vlc": {"display_name": "VLC Media Player", "emoji": "🎬", "category": "Media"},
    "paint": {"display_name": "MS Paint", "emoji": "🎨", "category": "Graphics"},
    "task manager": {"display_name": "Task Manager", "emoji": "📊", "category": "Utilities"},
    "taskmgr": {"display_name": "Task Manager", "emoji": "📊", "category": "Utilities"},
    "settings": {"display_name": "Windows Settings", "emoji": "⚙️", "category": "System"},
}


class RepoAppScanner:
    """
    Scans repository application definitions, path registries, and tool mappings
    to construct a unified catalog of launcher-ready applications.
    """

    @classmethod
    def get_all_registered_apps(cls) -> List[Dict[str, Any]]:
        """
        Dynamically extracts and deduplicates registered applications across the workspace.
        Returns a list of dicts: [
            {"alias_key": "notepad", "display_name": "Notepad", "emoji": "📝", "category": "IDEs & Editors"}
        ]
        """
        discovered: Dict[str, Dict[str, Any]] = {}

        # 1. Inspect app.tools.computer for COMMON_APP_MAP_WINDOWS
        try:
            from app.tools import computer
            app_map = getattr(computer, "COMMON_APP_MAP_WINDOWS", {})
            for alias, target in app_map.items():
                cls._register_alias(discovered, alias, target)
        except Exception as exc:
            logger.warning(f"[RepoAppScanner] Error reading computer.py app map: {exc}")

        # 2. Inspect computer.py functions and planner tools if available
        try:
            from app.core import planner
            planner_doc = getattr(planner, "PLANNER_SYSTEM_PROMPT", "")
            # Inspect mentioned applications in planner prompt
            for known_key in ["notepad", "calculator", "spotify", "chrome", "vscode"]:
                if known_key in planner_doc.lower() and known_key not in discovered:
                    cls._register_alias(discovered, known_key, known_key)
        except Exception as exc:
            logger.debug(f"[RepoAppScanner] Planner inspection note: {exc}")

        # Fallback ensuring standard tools are present if repo imports are empty
        if not discovered:
            for k, meta in APP_METADATA_DECORATORS.items():
                cls._register_alias(discovered, k, k)

        # Filter out redundant aliases and normalize list
        result_list = cls._deduplicate_and_sort(discovered)
        return result_list

    @classmethod
    def _register_alias(cls, discovered: Dict[str, Dict[str, Any]], alias: str, target: Any) -> None:
        alias_clean = alias.strip().lower()
        if not alias_clean:
            return

        # Fetch metadata decoration
        decorator = APP_METADATA_DECORATORS.get(alias_clean, {})
        display_name = decorator.get("display_name") or alias_clean.replace("_", " ").title()
        emoji = decorator.get("emoji") or "🚀"
        category = decorator.get("category") or "General"

        # Unique key grouping to avoid duplicate buttons for same app (e.g. calc and calculator)
        norm_group = cls._normalize_group_name(alias_clean)

        if norm_group not in discovered:
            discovered[norm_group] = {
                "alias_key": alias_clean,
                "display_name": display_name,
                "emoji": emoji,
                "category": category,
                "target": str(target),
            }

    @staticmethod
    def _normalize_group_name(alias: str) -> str:
        """Groups duplicate aliases like 'calc' & 'calculator' together."""
        a = alias.replace(".exe", "").replace(":", "").strip()
        if a in ("calc", "calculator"):
            return "calculator"
        if a in ("chrome", "google chrome", "browser"):
            return "chrome"
        if a in ("notepad", "ms-notepad"):
            return "notepad"
        if a in ("vscode", "vs code", "code"):
            return "vscode"
        if a in ("terminal", "wt"):
            return "terminal"
        if a in ("cmd", "command prompt"):
            return "cmd"
        if a in ("explorer", "file explorer", "files"):
            return "explorer"
        if a in ("task manager", "taskmgr"):
            return "taskmgr"
        return a

    @staticmethod
    def _deduplicate_and_sort(discovered: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Sorts apps logically by category then display name."""
        priority_order = [
            "chrome", "spotify", "vscode", "explorer", "notepad",
            "calculator", "terminal", "powershell", "cmd", "paint", "taskmgr", "settings"
        ]

        apps = list(discovered.values())

        def sort_key(app_item: Dict[str, Any]):
            alias = app_item["alias_key"]
            if alias in priority_order:
                return (0, priority_order.index(alias))
            return (1, app_item["category"], app_item["display_name"])

        apps.sort(key=sort_key)
        return apps
