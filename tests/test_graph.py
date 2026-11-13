import pytest
from app.agents.graph import build_nexus_graph
from app.agents.supervisor import find_next_executable_step


@pytest.mark.asyncio
async def test_single_step_developer_execution():
    """Verify single-step DeveloperAgent execution through LangGraph."""
    graph = build_nexus_graph()

    initial_state = {
        "user_id": "test_user_1",
        "chat_id": "test_chat_1",
        "channel": "telegram",
        "raw_prompt": "Run build and test suite",
        "task_graph": {
            "intent_category": "DEVELOPER",
            "summary": "Run developer suite",
            "requires_clarification": False,
            "steps": [
                {
                    "step_id": "step_1",
                    "description": "Execute pytest suite",
                    "target_agent": "DeveloperAgent",
                    "tool_name": "run_command",
                    "tool_params": {"command": "pytest"},
                    "depends_on": [],
                    "expected_output": "Test results",
                }
            ],
        },
        "current_step_id": None,
        "completed_steps": [],
        "failed_steps": [],
        "step_results": {},
        "retry_counts": {},
        "is_graph_complete": False,
        "agent_outputs": {},
        "artifacts": [],
        "token_usage": {},
        "hitl_approval_required": False,
        "hitl_payload": None,
        "error_logs": [],
    }

    config = {"configurable": {"thread_id": "test_thread_single_step"}}
    final_state = await graph.ainvoke(initial_state, config=config)

    assert final_state["is_graph_complete"] is True
    assert "step_1" in final_state["completed_steps"]
    assert "step_1" in final_state["step_results"]
    assert final_state["step_results"]["step_1"]["agent"] == "DeveloperAgent"
    assert "verification" in final_state["agent_outputs"]


@pytest.mark.asyncio
async def test_multi_step_dependent_dag_execution():
    """Verify multi-step DAG with dependencies (Browser ➔ FileAgent) executes sequentially."""
    graph = build_nexus_graph()

    initial_state = {
        "user_id": "test_user_2",
        "chat_id": "test_chat_2",
        "channel": "telegram",
        "raw_prompt": "Search AI tools and save to excel",
        "task_graph": {
            "intent_category": "HYBRID",
            "summary": "Search web and create spreadsheet",
            "requires_clarification": False,
            "steps": [
                {
                    "step_id": "step_1",
                    "description": "Search web for top AI tools",
                    "target_agent": "BrowserAgent",
                    "tool_name": "web_search",
                    "tool_params": {"query": "Top AI tools 2026"},
                    "depends_on": [],
                    "expected_output": "Search findings",
                },
                {
                    "step_id": "step_2",
                    "description": "Write findings to Excel spreadsheet in workspace",
                    "target_agent": "FileAgent",
                    "tool_name": "write_file",
                    "tool_params": {"filename": "ai_tools.xlsx"},
                    "depends_on": ["step_1"],
                    "expected_output": "Excel file in ./workspace/",
                },
            ],
        },
        "current_step_id": None,
        "completed_steps": [],
        "failed_steps": [],
        "step_results": {},
        "retry_counts": {},
        "is_graph_complete": False,
        "agent_outputs": {},
        "artifacts": [],
        "token_usage": {},
        "hitl_approval_required": False,
        "hitl_payload": None,
        "error_logs": [],
    }

    config = {"configurable": {"thread_id": "test_thread_multi_step"}}
    final_state = await graph.ainvoke(initial_state, config=config)

    assert final_state["is_graph_complete"] is True
    assert "step_1" in final_state["completed_steps"]
    assert "step_2" in final_state["completed_steps"]
    assert final_state["step_results"]["step_1"]["agent"] == "BrowserAgent"
    assert final_state["step_results"]["step_2"]["agent"] == "FileAgent"
    assert len(final_state["artifacts"]) >= 1


@pytest.mark.asyncio
async def test_circuit_breaker_max_retries():
    """Verify circuit breaker trips when retry counter reaches limit."""
    state = {
        "task_graph": {
            "steps": [
                {
                    "step_id": "step_err",
                    "description": "Failing step",
                    "target_agent": "DeveloperAgent",
                    "depends_on": [],
                }
            ]
        },
        "completed_steps": [],
        "failed_steps": [],
        "retry_counts": {"step_err": 5},
        "is_graph_complete": False,
    }

    from app.agents.supervisor import supervisor_node
    result = await supervisor_node(state)

    assert result["is_graph_complete"] is True
    assert "step_err" in result["failed_steps"]

