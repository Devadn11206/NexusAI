"""
End-to-End Master Feature Suite:
Validates Vision Intelligence, Background Cron Engine, Voice I/O,
HITL Gates, Verification Auditing, and MCP Integrations.
"""

import pytest
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

# 1. Vision Intelligence
from app.tools.vision import analyze_desktop_vision

# 2. Scheduler & Cron Engine
from app.core.scheduler import CronSchedulerEngine

# 3. Voice Input & TTS Engine
from app.tools.voice import transcribe_voice_note, generate_voice_response

# 4. HITL Approval Gate
from app.core.hitl_gate import HITLApprovalManager

# 5. Verification Agent
from app.agents.verification import verification_agent_node

# 6. MCP Integration
from app.tools.mcp_client import MCPClientManager


# ============================================================================
# 1. Vision-Based GUI & Desktop Intelligence
# ============================================================================

@pytest.mark.asyncio
async def test_analyze_desktop_vision_fallback_coordinates(tmp_path):
    """Verify vision engine extracts coordinates and handles fallback gracefully."""
    fake_img = tmp_path / "test_screen.png"
    fake_img.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82")

    res = await analyze_desktop_vision(str(fake_img), instruction="Click the blue save button")
    assert "coordinates" in res
    assert "x" in res["coordinates"]
    assert "y" in res["coordinates"]
    assert isinstance(res["coordinates"]["x"], int)
    assert isinstance(res["coordinates"]["y"], int)


# ============================================================================
# 2. Scheduler & Background Cron Engine
# ============================================================================

def test_cron_scheduler_register_and_load(tmp_path):
    """Verify CronSchedulerEngine loads persistent jobs and registers handlers."""
    config_file = tmp_path / "cron_tasks.json"
    engine = CronSchedulerEngine(config_path=str(config_file))

    dummy_jobs = [
        {"job_id": "daily_cleanup", "name": "Daily Cleanup", "interval": 86400}
    ]
    engine.save_scheduled_jobs(dummy_jobs)
    loaded = engine.load_scheduled_jobs()
    assert len(loaded) == 1
    assert loaded[0]["job_id"] == "daily_cleanup"

    mock_handler = MagicMock()
    engine.register_job("job_1", "Quick Job", 10, mock_handler)
    assert "job_1" in engine._registered_jobs


# ============================================================================
# 3. Voice Input & TTS Engine
# ============================================================================

@pytest.mark.asyncio
async def test_transcribe_voice_note_and_tts(tmp_path):
    """Verify voice transcription API and TTS synthesis pipelines."""
    fake_audio = tmp_path / "note.ogg"
    fake_audio.write_bytes(b"OggS\x00\x02\x00\x00\x00\x00\x00\x00\x00\x00")

    with patch("httpx.AsyncClient.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"text": "Play Love Me on Spotify"}
        mock_post.return_value = mock_resp

        transcript = await transcribe_voice_note(str(fake_audio), api_key="test_key")
        assert transcript == "Play Love Me on Spotify"

    # Test TTS synthesis
    out_audio = await generate_voice_response("Your task completed.", output_filename="test_tts.mp3")
    assert Path(out_audio).exists()
    assert Path(out_audio).stat().st_size > 0


# ============================================================================
# 4. Advanced Security & HITL Gates
# ============================================================================

@pytest.mark.asyncio
async def test_hitl_approval_manager_pause_and_resolve():
    """Verify HITL gate halts execution and resumes upon resolve_gate()."""
    mgr = HITLApprovalManager()
    gate_id = mgr.create_gate(
        action_name="rm -rf /workspace/critical",
        reason="Destructive command pattern detected",
        chat_id="6663290532",
    )
    assert gate_id in mgr._pending_approvals

    # Asynchronously approve the gate after 0.1 seconds
    async def async_approve():
        await asyncio.sleep(0.1)
        mgr.resolve_gate(gate_id, approved=True)

    asyncio.create_task(async_approve())

    with patch("app.services.messaging.telegram_service.send_approval_buttons", new_callable=AsyncMock):
        verdict = await mgr.request_and_wait_for_approval(gate_id, timeout_seconds=5)
        assert verdict is True


# ============================================================================
# 5. Verification Agent Post-Execution Audit
# ============================================================================

@pytest.mark.asyncio
async def test_verification_agent_audit(tmp_path):
    """Verify VerificationAgent audits completed DAG steps and artifacts."""
    test_file = tmp_path / "report.xlsx"
    test_file.write_text("dummy report data")

    dummy_state = {
        "completed_steps": ["step_1", "step_2"],
        "step_results": {
            "step_1": {"status": "success", "agent": "BrowserAgent"},
            "step_2": {"status": "success", "agent": "FileAgent"},
        },
        "artifacts": [
            {"filename": "report.xlsx", "path": str(test_file), "type": "file"}
        ],
        "agent_outputs": {},
    }

    res = await verification_agent_node(dummy_state)
    assert res["is_graph_complete"] is True
    audit = res["agent_outputs"]["verification"]
    assert audit["status"] == "verified"
    assert audit["verified_steps_count"] == 2
    assert audit["verified_artifacts_count"] == 1


# ============================================================================
# 6. Model Context Protocol (MCP) Integration
# ============================================================================

@pytest.mark.asyncio
async def test_mcp_client_tool_discovery_and_execution():
    """Verify MCPClientManager discovers dynamic tools and invokes them."""
    client = MCPClientManager()
    client.register_server("sqlite_db", transport="stdio", command="uvx mcp-server-sqlite")

    tools = await client.list_tools()
    assert len(tools) >= 2
    tool_names = [t["name"] for t in tools]
    assert "sqlite_db_read_context" in tool_names

    call_res = await client.execute_tool(
        tool_name="sqlite_db_query_db",
        arguments={"sql": "SELECT * FROM users"},
        server_name="sqlite_db",
    )
    assert call_res["status"] == "success"
    assert "sqlite_db_query_db" in call_res["result"]

