import os
from pathlib import Path
import pytest
from app.tools.filesystem import create_file, read_file, organize_directory, list_directory
from app.tools.computer import capture_desktop_screenshot
from app.agents.workers import file_agent_node, computer_agent_node


@pytest.mark.asyncio
async def test_create_and_read_file_in_workspace():
    """Verify safe creation and reading of text files in ./workspace/."""
    filename = "test_doc.txt"
    content = "Hello NEXUS AI Filesystem!"
    saved_path = await create_file(filename, content)

    path_obj = Path(saved_path)
    assert path_obj.exists()
    assert path_obj.is_file()

    read_back = await read_file(filename)
    assert read_back == content


@pytest.mark.asyncio
async def test_path_traversal_rejection():
    """Verify that path traversal attempts outside ./workspace/ raise PermissionError."""
    with pytest.raises(PermissionError):
        await create_file("../../escape.txt", "Malicious content")

    with pytest.raises(PermissionError):
        await read_file("../../../Windows/System32/drivers/etc/hosts")


@pytest.mark.asyncio
async def test_organize_directory():
    """Verify that directory organization categorizes files by extension into subdirectories."""
    # Create test files
    await create_file("sample_report.pdf", "PDF test content")
    await create_file("sample_data.csv", "col1,col2\n1,2")
    await create_file("sample_code.py", "print('hello')")

    org_result = await organize_directory(directory="")
    assert org_result["status"] == "success"
    assert org_result["total_organized"] >= 3

    # Verify files moved to appropriate subdirectories
    workspace_dir = Path("./workspace")
    assert (workspace_dir / "documents" / "sample_report.pdf").exists()
    assert (workspace_dir / "data" / "sample_data.csv").exists()
    assert (workspace_dir / "code" / "sample_code.py").exists()


@pytest.mark.asyncio
async def test_file_agent_node_execution():
    """Verify file_agent_node creates files and registers them in state artifacts."""
    state = {
        "user_id": "test_user",
        "chat_id": "test_chat",
        "channel": "telegram",
        "raw_prompt": "Save findings to note.md",
        "task_graph": {
            "steps": [
                {
                    "step_id": "step_file_1",
                    "target_agent": "FileAgent",
                    "tool_name": "create_file",
                    "tool_params": {
                        "filename": "findings_summary.md",
                        "content": "# Research Findings\n- AI Agent 1\n- AI Agent 2",
                    },
                    "depends_on": [],
                }
            ]
        },
        "current_step_id": "step_file_1",
        "completed_steps": [],
        "failed_steps": [],
        "step_results": {},
        "agent_outputs": {},
        "artifacts": [],
    }

    updated_state = await file_agent_node(state)
    assert "step_file_1" in updated_state["completed_steps"]
    assert len(updated_state["artifacts"]) >= 1
    artifact = updated_state["artifacts"][0]
    assert artifact["filename"] == "findings_summary.md"
    assert Path(artifact["path"]).exists()


@pytest.mark.asyncio
async def test_computer_agent_screenshot():
    """Verify ComputerAgent captures desktop screenshot safely."""
    state = {
        "user_id": "test_user",
        "chat_id": "test_chat",
        "channel": "telegram",
        "raw_prompt": "Take screenshot of desktop",
        "task_graph": {
            "steps": [
                {
                    "step_id": "step_comp_1",
                    "target_agent": "ComputerAgent",
                    "tool_name": "capture_desktop_screenshot",
                    "tool_params": {"filename": "desktop_test.png"},
                    "depends_on": [],
                }
            ]
        },
        "current_step_id": "step_comp_1",
        "completed_steps": [],
        "failed_steps": [],
        "step_results": {},
        "agent_outputs": {},
        "artifacts": [],
    }

    updated_state = await computer_agent_node(state)
    assert "step_comp_1" in updated_state["completed_steps"]
    assert len(updated_state["artifacts"]) >= 1
    artifact = updated_state["artifacts"][0]
    assert artifact["filename"] == "desktop_test.png"
    assert Path(artifact["path"]).exists()

