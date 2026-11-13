import os
import sys
import pytest
from pathlib import Path

from app.tools.developer import (
    execute_shell_command,
    execute_python_code,
    run_git_command,
    is_command_destructive,
)
from app.tools.computer import play_spotify_music
from app.config import settings


@pytest.mark.asyncio
async def test_execute_shell_command_safe():
    # Run a simple echo command
    res = await execute_shell_command("echo hello world")
    assert res["status"] == "success"
    assert "hello world" in res["stdout"].lower()
    assert res["exit_code"] == 0


@pytest.mark.asyncio
async def test_destructive_command_blocking():
    # Attempt destructive command without approval
    res = await execute_shell_command("rm -rf /")
    assert res["status"] == "blocked"
    assert res["requires_hitl"] is True
    assert "dangerous pattern" in res["reason"]

    # Windows destructive command
    is_dest, reason = is_command_destructive("del /f /s /q C:\\Windows")
    assert is_dest is True


@pytest.mark.asyncio
async def test_execute_python_code():
    art_path = Path(settings.WORKSPACE_DIR) / "test_artifact.txt"
    art_path.unlink(missing_ok=True)
    code = """
import sys
print(f"Python running successfully: {2 + 2}")
with open("test_artifact.txt", "w") as f:
    f.write("Generated from python test")
"""
    res = await execute_python_code(code=code, filename="math_test.py")
    assert res["status"] == "success"
    assert "Python running successfully: 4" in res["stdout"]
    assert "test_artifact.txt" in res["generated_artifacts"]

    # Verify file was created in workspace
    assert art_path.exists()
    assert art_path.read_text() == "Generated from python test"
    # Cleanup
    art_path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_run_git_command():
    res = await run_git_command(subcommand="status")
    # Git status in workspace or repo
    assert res["status"] in ("success", "failed")  # Workspace might not be a git repo, but command must execute safely


@pytest.mark.asyncio
async def test_play_spotify_music_mock(monkeypatch):
    # Verify play_spotify_music executes without unhandled errors
    monkeypatch.setattr("app.tools.computer._ensure_input_desktop", lambda: None)
    monkeypatch.setattr("app.tools.computer.force_window_foreground", lambda pat: True)
    
    res = await play_spotify_music(song="Love Me Not", playlist="Liked Songs")
    assert res["status"] == "success"
    assert res["song"] == "Love Me Not"
    assert res["playlist"] == "Liked Songs"
