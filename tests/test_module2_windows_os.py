"""
Unit & Integration Tests for Module 2: Complete Windows 11 Desktop Automation.
Tests:
1. Installed application discovery (Registry scan + PowerShell Get-StartApps).
2. Process detection (psutil) and window state management (minimize, maximize, switch).
3. Authorized software install/uninstall blocked by HITL gate unless explicitly approved.
4. Hung-window and error dialog detection with DPI awareness initialization.
5. Precision mouse and keyboard actions.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.tools.computer import (
    search_installed_apps,
    get_running_apps,
    manage_window,
    install_application,
    uninstall_application,
    detect_app_errors,
    control_app_ui,
    mouse_action,
    keyboard_action,
    close_application,
    _init_dpi_awareness,
)
from app.core.hitl_gate import hitl_manager


# ============================================================================
# 1. Installed Software Search & Registry Indexer Tests
# ============================================================================

@pytest.mark.asyncio
async def test_search_installed_apps_discovery():
    """Verify search_installed_apps queries registry keys and Get-StartApps."""
    mock_ps_res = MagicMock()
    mock_ps_res.returncode = 0
    mock_ps_res.stdout = '[{"Name": "Spotify Music", "AppID": "Spotify.Spotify_mbt5bj5842xr4!Spotify"}, {"Name": "Calculator", "AppID": "Microsoft.WindowsCalculator_8wekyb3d8bbwe!App"}]'

    with patch("subprocess.run", return_value=mock_ps_res):
        apps = await search_installed_apps(query="spotify")
        assert len(apps) >= 1
        found_spotify = any("spotify" in a["name"].lower() for a in apps)
        assert found_spotify


# ============================================================================
# 2. Process Detection & Window State Management Tests
# ============================================================================

@pytest.mark.asyncio
async def test_get_running_apps():
    """Verify get_running_apps captures running desktop processes."""
    mock_proc = MagicMock()
    mock_proc.info = {"pid": 4321, "name": "notepad.exe", "memory_percent": 1.25, "status": "running"}
    mock_proc.memory_percent.return_value = 1.25

    with patch("psutil.process_iter", return_value=[mock_proc]):
        apps = await get_running_apps()
        assert len(apps) >= 1
        assert any(a["pid"] == 4321 for a in apps)


@pytest.mark.asyncio
async def test_manage_window_actions():
    """Verify manage_window supports minimize, maximize, restore, and switch."""
    with patch("app.tools.computer.sys.platform", "win32"), \
         patch("app.tools.computer.win32gui") as mock_win32gui:

        # Simulate finding HWND
        def _fake_enum(callback, extra):
            callback(999888, None)
            return True

        mock_win32gui.EnumWindows.side_effect = _fake_enum
        mock_win32gui.IsWindowVisible.return_value = True
        mock_win32gui.GetWindowText.return_value = "Untitled - Notepad"

        # 1. Minimize
        res_min = await manage_window("notepad", "minimize")
        assert res_min["status"] == "success"
        assert res_min["action"] == "minimize"

        # 2. Maximize
        res_max = await manage_window("notepad", "maximize")
        assert res_max["status"] == "success"

        # 3. Switch (Foreground)
        res_switch = await manage_window("notepad", "switch")
        assert res_switch["status"] == "success"


# ============================================================================
# 3. Authorized Software Install / Uninstall (HITL Gate Enforcement)
# ============================================================================

@pytest.mark.asyncio
async def test_install_application_strictly_requires_hitl():
    """Verify install_application blocks execution when HITL approval is rejected."""
    with patch.object(hitl_manager, "request_and_wait_for_approval", AsyncMock(return_value=False)):
        res = await install_application("Git.Git")
        assert res["status"] == "rejected"
        assert "denied" in res["message"].lower()


@pytest.mark.asyncio
async def test_install_application_executes_on_approval():
    """Verify install_application runs winget command when explicitly approved."""
    mock_subproc = MagicMock()
    mock_subproc.communicate = AsyncMock(return_value=(b"Successfully installed Git", b""))
    mock_subproc.returncode = 0

    with patch.object(hitl_manager, "request_and_wait_for_approval", AsyncMock(return_value=True)), \
         patch("asyncio.create_subprocess_shell", AsyncMock(return_value=mock_subproc)) as mock_shell:

        res = await install_application("Git.Git")
        assert res["status"] == "success"
        assert res["exit_code"] == 0
        mock_shell.assert_called_once()
        assert "winget install" in mock_shell.call_args[0][0]


@pytest.mark.asyncio
async def test_uninstall_application_hitl():
    """Verify uninstall_application blocks when HITL is rejected and proceeds when approved."""
    with patch.object(hitl_manager, "request_and_wait_for_approval", AsyncMock(return_value=False)):
        res_rej = await uninstall_application("VLC")
        assert res_rej["status"] == "rejected"

    mock_subproc = MagicMock()
    mock_subproc.communicate = AsyncMock(return_value=(b"Successfully uninstalled", b""))
    mock_subproc.returncode = 0

    with patch.object(hitl_manager, "request_and_wait_for_approval", AsyncMock(return_value=True)), \
         patch("asyncio.create_subprocess_shell", AsyncMock(return_value=mock_subproc)):
        res_app = await uninstall_application("VLC")
        assert res_app["status"] == "success"


# ============================================================================
# 4. Error Detection, DPI Awareness & Input Control Tests
# ============================================================================

@pytest.mark.asyncio
async def test_detect_app_errors():
    """Verify detect_app_errors scans desktop for hung or crash dialogs."""
    with patch("app.tools.computer.sys.platform", "win32"), \
         patch("app.tools.computer.win32gui") as mock_win32gui:

        def _fake_enum(callback, extra):
            callback(111222, None)
            return True

        mock_win32gui.EnumWindows.side_effect = _fake_enum
        mock_win32gui.IsWindowVisible.return_value = True
        mock_win32gui.GetWindowText.return_value = "Application Error: Fatal exception"

        errors = await detect_app_errors()
        assert len(errors) == 1
        assert "Fatal exception" in errors[0]["title"]


@pytest.mark.asyncio
async def test_mouse_and_keyboard_actions():
    """Verify DPI-aware mouse and keyboard actions execute cleanly."""
    with patch("pyautogui.moveTo") as mock_move, \
         patch("pyautogui.click") as mock_click, \
         patch("pyautogui.hotkey") as mock_hotkey:

        res_mouse = await mouse_action(action="click", x=500, y=300)
        assert res_mouse["status"] == "success"
        mock_move.assert_called_with(500, 300)
        mock_click.assert_called_once()

        res_key = await keyboard_action(action="hotkey", keys=["win", "d"])
        assert res_key["status"] == "success"
        mock_hotkey.assert_called_with("win", "d")


def test_dpi_awareness_init():
    """Verify DPI awareness initialization runs without raising errors."""
    _init_dpi_awareness()

