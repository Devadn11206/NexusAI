"""
Comprehensive Unit & Integration Tests for NEXUS AI Core Intelligence Layer.
Tests:
1. Multi-turn context awareness across consecutive invocations with the same thread_id (e.g., pronoun resolution 'it').
2. Multi-step task decomposition and sequential cyclical execution of a 3-step workflow.
3. Dynamic replanning loop when a simulated step fails on the first attempt and succeeds on the replanned second attempt.
"""

import pytest
import sqlite3
from unittest.mock import AsyncMock, patch, MagicMock
from langchain_core.messages import HumanMessage, AIMessage
from langgraph.checkpoint.sqlite import SqliteSaver

from app.core.state import NexusState
from app.core.brain import (
    intent_and_context_node,
    task_planner_node,
    step_executor_node,
    dynamic_replanner_node,
    final_responder_node,
)
from app.graph import build_nexus_intelligence_graph


@pytest.fixture
def memory_checkpointer():
    """Provides an in-memory Checkpointer for isolated async/sync testing."""
    from langgraph.checkpoint.memory import MemorySaver
    return MemorySaver()


# ============================================================================
# 1. Multi-Turn Context Awareness Tests
# ============================================================================

@pytest.mark.asyncio
async def test_multiturn_context_awareness(memory_checkpointer):
    """
    Verifies that the cognitive engine retains prior conversation turns
    and resolves pronoun references like 'close it' based on earlier app mentions.
    """
    graph = build_nexus_intelligence_graph(checkpointer=memory_checkpointer)
    config = {"configurable": {"thread_id": "test_thread_multiturn_1"}}

    # Turn 1: User asks to open notepad
    with patch("app.core.brain.dispatch_tool_call", AsyncMock(return_value={"status": "success", "app": "notepad"})):
        state_1 = {
            "messages": [HumanMessage(content="Open notepad please")],
        }
        res_1 = await graph.ainvoke(state_1, config=config)
        assert res_1["user_intent"]["entities"]["app_name"] == "notepad"
        assert len(res_1["plan_steps"]) >= 1

    # Turn 2: User says "close it" in the same thread
    with patch("app.core.brain.dispatch_tool_call", AsyncMock(return_value={"status": "success", "terminated_count": 1})) as mock_dispatch:
        state_2 = {
            "messages": [HumanMessage(content="Okay, now close it")],
        }
        res_2 = await graph.ainvoke(state_2, config=config)

        # Contextual resolution must have mapped 'it' -> 'notepad'
        assert "notepad" in res_2["user_intent"]["resolved_query"].lower()
        assert res_2["user_intent"]["entities"]["app_name"] == "notepad"
        assert res_2["user_intent"]["entities"]["action"] == "close"

        # Step executor must have executed close_application for notepad
        assert any(
            call.args[0] == "close_application" and call.args[1].get("process_name") == "notepad"
            for call in mock_dispatch.call_args_list
        )


# ============================================================================
# 2. Multi-Step Task Decomposition & Sequential Execution Tests
# ============================================================================

@pytest.mark.asyncio
async def test_multistep_decomposition_and_execution(memory_checkpointer):
    """
    Verifies that complex commands decompose into a multi-step plan
    and the cyclical graph executes all steps sequentially to completion.
    """
    graph = build_nexus_intelligence_graph(checkpointer=memory_checkpointer)
    config = {"configurable": {"thread_id": "test_thread_multistep_2"}}

    executed_tools = []

    async def _mock_tool_dispatcher(tool_name: str, tool_args: dict):
        executed_tools.append((tool_name, tool_args))
        if tool_name == "capture_desktop_screenshot":
            return {"status": "success", "screenshot_path": "workspace/proof.png"}
        return {"status": "success", "result": f"Done {tool_name}"}

    with patch("app.core.brain.dispatch_tool_call", side_effect=_mock_tool_dispatcher):
        initial_state = {
            "messages": [HumanMessage(content="Generate a code report and capture desktop screenshot")],
        }
        result = await graph.ainvoke(initial_state, config=config)

        # Confirm 3 distinct steps were generated and executed
        assert len(result["plan_steps"]) == 3
        for step in result["plan_steps"]:
            assert step["status"] == "completed"

        assert len(result["execution_logs"]) == 3
        assert len(executed_tools) == 3
        assert executed_tools[0][0] == "execute_python_script"
        assert executed_tools[1][0] == "create_file"
        assert executed_tools[2][0] == "capture_desktop_screenshot"

        # Confirm final responder summarized all steps
        assert "Task Completed Successfully" in result["final_response"]
        assert "workspace/proof.png" in result["artifacts"]


# ============================================================================
# 3. Dynamic Replanning Upon Tool Failure Tests
# ============================================================================

@pytest.mark.asyncio
async def test_dynamic_replanning_on_failure(memory_checkpointer):
    """
    Verifies that when a step fails, the dynamic_replanner intercepts the failure,
    increments replan_count, generates an alternative step, and resumes execution.
    """
    graph = build_nexus_intelligence_graph(checkpointer=memory_checkpointer)
    config = {"configurable": {"thread_id": "test_thread_replan_3"}}

    attempts = {"count": 0}

    async def _mock_tool_with_recovery(tool_name: str, tool_args: dict):
        attempts["count"] += 1
        if attempts["count"] == 1:
            # First attempt fails
            raise RuntimeError("Simulated connection timeout during play_web_music")
        # Second replanned attempt succeeds
        return {"status": "success", "query": tool_args.get("query")}

    with patch("app.core.brain.dispatch_tool_call", side_effect=_mock_tool_with_recovery):
        initial_state = {
            "messages": [HumanMessage(content="Play Baby song on youtube")],
        }
        result = await graph.ainvoke(initial_state, config=config)

        # Replanning must have triggered exactly once
        assert result["replan_count"] == 1

        # Confirm the execution logs recorded both the failure and the recovery
        statuses = [log["status"] for log in result["execution_logs"]]
        assert "failed" in statuses
        assert "completed" in statuses

        # Confirm final response indicates recovery
        assert "Dynamic recovery activated (1 replan(s) executed)" in result["final_response"]
