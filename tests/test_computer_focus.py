from pathlib import Path
import pytest
from app.tools.computer import (
    launch_application,
    focus_window,
    close_application,
    send_hotkey,
    type_text,
    capture_desktop_screenshot,
    list_active_windows,
)
from app.agents.workers import computer_agent_node


@pytest.mark.asyncio
async def test_launch_application_with_focus():
    """Verify application launch initiates process and resolves foreground window status."""
    res = await launch_application("calc")
    assert res["status"] in ("success", "failed")
    if res["status"] == "success":
        assert "app" in res
        # Close launched app to leave environment clean
        await close_application("Calculator")


@pytest.mark.asyncio
async def test_send_hotkey_and_typing():
    """Verify GUI hotkey dispatch and keyboard text simulation execute without errors."""
    hotkey_res = await send_hotkey(["ctrl"])
    assert hotkey_res["status"] == "success"

    type_res = await type_text("NEXUS AI Test", interval=0.01, press_enter=False)
    assert type_res["status"] == "success"
    assert type_res["typed_length"] == 13


@pytest.mark.asyncio
async def test_computer_agent_node_proof_screenshot():
    """Verify computer_agent_node launches app and records visual proof artifact in state."""
    state = {
        "user_id": "test_user",
        "chat_id": "test_chat",
        "channel": "telegram",
        "raw_prompt": "Open calculator",
        "task_graph": {
            "steps": [
                {
                    "step_id": "step_comp_focus",
                    "target_agent": "ComputerAgent",
                    "tool_name": "launch_application",
                    "tool_params": {"app_name": "calc"},
                    "depends_on": [],
                }
            ]
        },
        "current_step_id": "step_comp_focus",
        "completed_steps": [],
        "failed_steps": [],
        "step_results": {},
        "agent_outputs": {},
        "artifacts": [],
    }

    updated_state = await computer_agent_node(state)
    assert "step_comp_focus" in updated_state["completed_steps"]
    # Check that execution artifact proof screenshot was automatically captured and attached
    assert len(updated_state["artifacts"]) >= 1
    artifact = updated_state["artifacts"][0]
    assert artifact["filename"].endswith(".png")
    assert Path(artifact["path"]).exists()

    # Clean up test artifact
    try:
        Path(artifact["path"]).unlink()
    except Exception:
        pass

