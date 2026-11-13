"""Comprehensive Verification Suite for Short-Form App Resolution & Desktop Automation.
Verifies:
1. Short-form, slang, abbreviation, and typo resolution across 30+ aliases:
   (chrome, gc, vs, vscode, calc, np, notepad, wa, whatsapp, yt, ytm, spotify, spot,
    ppt, word, excel, xl, cmd, ps, term, vlc, edge, tg, telegram, dc, discord, obs,
    taskmgr, settings, explorer).
2. 5-Source Windows 11 App Indexing (App Paths, Uninstall, Get-StartApps, StartMenu, PATH).
3. search_installed_apps finding apps via short forms without false "Not Found" errors.
4. launch_application, manage_window, and close_application resolving short forms.
"""

import pytest
import asyncio
from app.tools.computer import (
    APP_ALIASES,
    _build_installed_app_index,
    resolve_app_query,
    resolve_app_alias,
    search_installed_apps,
    launch_application,
    manage_window,
    close_application,
)


def test_app_aliases_dictionary_coverage():
    """Verify that all requested short forms, slang, and abbreviations are present."""
    required_aliases = [
        "chrome", "gc", "google", "browser", "edge", "msedge", "brave",
        "vs", "vscode", "code", "cursor", "np", "notepad", "note",
        "calc", "calculator", "wa", "whatsapp", "tg", "telegram",
        "spot", "spotify", "yt", "youtube", "ytm", "yt music",
        "vlc", "word", "winword", "doc", "excel", "xl", "xls",
        "ppt", "powerpoint", "cmd", "ps", "powershell", "term", "terminal", "wt",
        "explorer", "files", "settings", "taskmgr", "paint", "snip", "dc", "discord", "obs"
    ]
    for alias in required_aliases:
        assert alias in APP_ALIASES, f"Missing required alias: '{alias}'"
        info = APP_ALIASES[alias]
        assert "canonical_name" in info
        assert "exe" in info
        assert "protocol" in info


def test_resolve_app_query_shortforms():
    """Verify resolution of short forms to canonical names and process targets."""
    cases = [
        ("gc", "Google Chrome", "chrome.exe"),
        ("chrome", "Google Chrome", "chrome.exe"),
        ("vs", "Visual Studio Code", "code.exe"),
        ("vscode", "Visual Studio Code", "code.exe"),
        ("calc", "Calculator", "calculatorapp.exe"),
        ("np", "Notepad", "notepad.exe"),
        ("notepad", "Notepad", "notepad.exe"),
        ("wa", "WhatsApp", "whatsapp.exe"),
        ("tg", "Telegram", "telegram.exe"),
        ("spot", "Spotify", "spotify.exe"),
        ("ppt", "Microsoft PowerPoint", "powerpnt.exe"),
        ("word", "Microsoft Word", "winword.exe"),
        ("xl", "Microsoft Excel", "excel.exe"),
        ("excel", "Microsoft Excel", "excel.exe"),
        ("term", "Windows Terminal", "wt.exe"),
        ("cmd", "Command Prompt", "cmd.exe"),
        ("ps", "Windows PowerShell", "powershell.exe"),
        ("vlc", "VLC media player", "vlc.exe"),
        ("dc", "Discord", "discord.exe"),
        ("obs", "OBS Studio", "obs64.exe"),
        ("taskmgr", "Task Manager", "taskmgr.exe"),
        ("settings", "Settings", "systemsettings.exe"),
        ("explorer", "File Explorer", "explorer.exe"),
    ]

    for short_form, expected_canonical, expected_exe in cases:
        res = resolve_app_query(short_form)
        assert res["canonical_name"].lower() == expected_canonical.lower(), (
            f"Expected '{expected_canonical}' for '{short_form}', got '{res['canonical_name']}'"
        )
        procs_lower = [p.lower() for p in res["process_names"]]
        assert any(expected_exe.lower().replace(".exe", "") in p for p in procs_lower), (
            f"Expected process matching '{expected_exe}' for '{short_form}', got {res['process_names']}"
        )


def test_resolve_app_query_fuzzy_and_typos():
    """Verify fuzzy resolver handles typos and variations (e.g. 'notepd', 'chrom', 'calculater')."""
    res_np = resolve_app_query("notepd")
    assert "Notepad" in res_np["canonical_name"]

    res_calc = resolve_app_query("calculater")
    assert "Calculator" in res_calc["canonical_name"]

    res_ch = resolve_app_query("chrom")
    assert "Google Chrome" in res_ch["canonical_name"]


def test_five_source_app_indexing():
    """Verify 5-source Windows 11 index discovers apps from registry, UWP, and shortcuts."""
    apps = _build_installed_app_index(force_refresh=True)
    assert len(apps) > 10, f"Expected >10 discovered apps, got {len(apps)}"

    # Check presence of standard Windows apps
    names_lower = [a["name"].lower() for a in apps]
    assert any("notepad" in n for n in names_lower)
    assert any("calculator" in n or "calc" in n for n in names_lower)


@pytest.mark.asyncio
async def test_search_installed_apps_with_shortforms():
    """Verify search_installed_apps correctly finds apps via shortforms without false 'Not Found'."""
    test_queries = ["gc", "chrome", "calc", "np", "notepad", "vs", "ppt"]
    for q in test_queries:
        results = await search_installed_apps(q)
        assert len(results) > 0, f"search_installed_apps('{q}') returned empty list!"
        app_names = [r["name"].lower() for r in results]
        canonical_target = resolve_app_query(q)["canonical_name"].lower()
        canonical_words = [w for w in canonical_target.split() if len(w) > 3]
        match_found = any(
            canonical_target in n or q in n or any(w in n for w in canonical_words)
            for n in app_names
        )
        assert match_found, (
            f"Search query '{q}' did not return expected target '{canonical_target}': {app_names}"
        )


@pytest.mark.asyncio
async def test_launch_and_close_with_shortforms():
    """Verify launch_application and close_application seamlessly accept shortforms."""
    # Launch Notepad via shortform 'np'
    launch_res = await launch_application("np")
    assert launch_res["status"] == "success"
    assert "Notepad" in launch_res.get("resolved", "") or "notepad" in launch_res.get("app", "")

    await asyncio.sleep(1.0)

    # Manage window via shortform 'np'
    manage_res = await manage_window("np", action="minimize")
    assert manage_res["status"] in ("success", "simulated")

    # Close via shortform 'np'
    close_res = await close_application("np")
    assert close_res["status"] in ("success", "not_found")
    assert close_res.get("terminated_count", 0) >= 1 or close_res["status"] == "success"

