"""Comprehensive Test Suite for Autonomous Developer & Competitive Programming Subsystem.
Verifies:
1. Autonomous project scaffolding, full-stack generation, and automated pytest execution.
2. Self-healing debugger repairing an intentional bug in generated FastAPI app.
3. Runtime monitor detecting simulated Python Tracebacks and 500 error logs.
4. Competitive programming solver: problem metadata extraction, local sandbox harness verification,
   mock Monaco editor injection, and verdict retry/repair loop.
5. LangGraph DeveloperAgent node integration.
"""

import asyncio
import os
import shutil
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from app.developer.project_architect import plan_project_architecture, scaffold_project
from app.developer.code_generator import generate_full_stack_project
from app.developer.runtime_monitor import RuntimeMonitor
from app.developer.self_healer import SelfHealer
from app.developer.cp_solver import CompetitiveProgrammingSolver
from app.developer.developer_agent import run_developer_task, developer_agent_node
from langchain_core.messages import HumanMessage


@pytest.fixture
def temp_dev_workspace(tmp_path):
    """Fixture providing isolated developer workspace directory."""
    ws = tmp_path / "dev_test_ws"
    ws.mkdir()
    return ws


def test_project_architect_and_code_scaffold(temp_dev_workspace):
    """Verify architectural file-tree planning and code generation."""
    prompt = "Build a student attendance management application"
    arch = plan_project_architecture(prompt)

    assert arch["domain"] == "student_attendance"
    assert "main.py" in arch["file_tree"]
    assert "models.py" in arch["file_tree"]

    # Redirect project_dir to temp_dev_workspace
    arch["project_dir"] = str(temp_dev_workspace / arch["slug"])
    proj_dir = scaffold_project(arch)
    assert Path(proj_dir).exists()

    generated_files = generate_full_stack_project(arch)
    assert len(generated_files) >= 10
    assert (Path(proj_dir) / "main.py").exists()
    assert (Path(proj_dir) / "tests/test_app.py").exists()
    assert (Path(proj_dir) / "static/index.html").exists()


@pytest.mark.asyncio
async def test_runtime_monitor_and_pytest_execution(temp_dev_workspace):
    """Verify running pytest in scaffolded project and parsing logs."""
    arch = plan_project_architecture("Simple task tracker application")
    arch["project_dir"] = str(temp_dev_workspace / "task_tracker_app")
    scaffold_project(arch)
    generate_full_stack_project(arch)

    monitor = RuntimeMonitor()
    res = await monitor.run_pytest_in_project(arch["project_dir"])

    assert res["status"] == "passed"
    assert res["returncode"] == 0
    assert len(monitor.get_logs()) > 0


def test_runtime_monitor_log_diagnostics():
    """Verify detection of Python tracebacks, syntax errors, and HTTP 500 errors."""
    monitor = RuntimeMonitor()
    simulated_log = (
        'INFO: 127.0.0.1 - "GET /api/records HTTP/1.1" 200 OK\n'
        'Traceback (most recent call last):\n'
        '  File "C:/app/main.py", line 42, in get_records\n'
        '    result = 10 / 0\n'
        'ZeroDivisionError: division by zero\n'
        'ERROR: 127.0.0.1 - "POST /api/records HTTP/1.1" 500 Internal Server Error\n'
    )

    diagnostics = monitor.parse_diagnostics(simulated_log)
    assert len(diagnostics) >= 2

    # Check Traceback diagnostic
    tb_diag = [d for d in diagnostics if d["error_type"] == "PythonTraceback"][0]
    assert tb_diag["line_number"] == 42
    assert "ZeroDivisionError" in tb_diag["exception"]

    # Check 500 diagnostic
    http_diag = [d for d in diagnostics if d["error_type"] == "HTTP500InternalServerError"][0]
    assert http_diag["endpoint"] == "/api/records"


@pytest.mark.asyncio
async def test_self_healing_targeted_patch(temp_dev_workspace):
    """Verify SelfHealer patches intentional bug and restores passing test suite."""
    arch = plan_project_architecture("Buggy service test")
    arch["project_dir"] = str(temp_dev_workspace / "buggy_app")
    scaffold_project(arch)
    generate_full_stack_project(arch)

    main_py = Path(arch["project_dir"]) / "main.py"
    # Inject intentional bug
    broken_code = main_py.read_text(encoding="utf-8").replace("def health():", "def health():\n    x = 10 / 0")
    main_py.write_text(broken_code, encoding="utf-8")

    monitor = RuntimeMonitor()
    pytest_res = await monitor.run_pytest_in_project(arch["project_dir"])
    assert pytest_res["status"] == "failed"

    # Self-heal
    healer = SelfHealer(arch["project_dir"])
    for diag in pytest_res["diagnostics"]:
        healer.heal_traceback(diag)

    # Re-run verification
    healed_res = await monitor.run_pytest_in_project(arch["project_dir"])
    assert healed_res["status"] == "passed"


def test_cp_problem_metadata_extraction():
    """Verify parsing of LeetCode/CodeChef problem description and test cases."""
    solver = CompetitiveProgrammingSolver()
    raw_problem = (
        "1. Two Sum\n"
        "Given an array of integers nums and an integer target, return indices of the two numbers such that they add up to target.\n"
        "Example 1:\n"
        "Input: nums = [2,7,11,15], target = 9\n"
        "Output: [0,1]\n"
        "Constraints:\n"
        "2 <= nums.length <= 10^4\n"
    )

    meta = solver.extract_problem_metadata(raw_problem)
    assert "1. Two Sum" in meta["title"]
    assert len(meta["examples"]) >= 1
    assert "target = 9" in meta["examples"][0]["input"]
    assert meta["examples"][0]["output"] == "[0,1]"


@pytest.mark.asyncio
async def test_cp_sandbox_and_repair_loop(temp_dev_workspace):
    """Verify local test harness execution and verdict-driven repair loop."""
    solver = CompetitiveProgrammingSolver(sandbox_dir=temp_dev_workspace)
    raw_problem = (
        "1. Two Sum\n"
        "Input: nums = [2,7,11,15], target = 9\n"
        "Output: [0,1]\n"
    )

    res = await solver.solve_with_repair_loop(raw_problem, max_attempts=3)
    assert res["final_verdict"] == "Accepted"
    assert "class Solution:" in res["solution_code"]
    assert res["total_attempts"] >= 1


@pytest.mark.asyncio
async def test_mock_monaco_editor_injection():
    """Verify Playwright Monaco editor injection and submission flow."""
    solver = CompetitiveProgrammingSolver()

    # Mock Playwright Page
    mock_page = MagicMock()
    mock_locator = AsyncMock()
    mock_locator.count = AsyncMock(return_value=1)
    mock_locator.inner_text = AsyncMock(return_value="Accepted")
    mock_locator.first = mock_locator
    mock_page.locator = MagicMock(return_value=mock_locator)
    mock_page.keyboard.press = AsyncMock()
    mock_page.keyboard.insert_text = AsyncMock()
    mock_page.evaluate = AsyncMock(return_value=True)

    result = await solver.inject_and_submit_browser(mock_page, "class Solution: pass", auto_submit=True)
    assert result["status"] == "submitted"
    assert result["verdict"] == "Accepted"


@pytest.mark.asyncio
async def test_developer_agent_node_execution():
    """Verify DeveloperAgent executes within LangGraph node and returns artifacts."""
    state = {
        "messages": [HumanMessage(content="Solve LeetCode Two Sum Problem with optimal hash map algorithm")],
        "artifacts": [],
        "execution_logs": [],
    }

    res = await developer_agent_node(state)
    assert len(res["messages"]) == 1
    assert "Accepted" in res["messages"][0].content
    assert len(res["execution_logs"]) >= 1

