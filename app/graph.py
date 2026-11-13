"""
NEXUS AI - Cyclical LangGraph Orchestrator & Persistent Checkpointer
Compiles the stateful Cyclical StateGraph with SqliteSaver persistence
stored at ./workspace/memory/nexus_checkpoints.db.
"""

import logging
import sqlite3
from pathlib import Path
from typing import Literal, Optional, Any

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.checkpoint.memory import MemorySaver

from app.core.state import NexusState
from app.core.brain import (
    intent_and_context_node,
    task_planner_node,
    step_executor_node,
    dynamic_replanner_node,
    final_responder_node,
)
from app.core.security import resolve_safe_workspace_path

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Routing Condition Functions
# ---------------------------------------------------------------------------

def route_step_execution(state: NexusState) -> Literal["dynamic_replanner", "step_executor", "final_responder"]:
    """
    Decides the next node after step_executor:
    1. If the current step failed and replan_count < 3 -> dynamic_replanner.
    2. Else if there are more steps remaining -> loop back to step_executor.
    3. Else -> transition to final_responder.
    """
    plan_steps = state.get("plan_steps", [])
    idx = state.get("current_step_index", 0)
    replan_count = state.get("replan_count", 0)

    # Check status of step just executed
    if idx < len(plan_steps):
        current_step = plan_steps[idx]
        if current_step.get("status") == "failed":
            if replan_count < 3:
                logger.info(f"[Router] Step '{current_step.get('step_id')}' failed. Triggering dynamic_replanner (attempt {replan_count+1}/3).")
                return "dynamic_replanner"
            else:
                logger.warning(f"[Router] Max replan limit (3) reached. Proceeding to final_responder.")
                return "final_responder"

    # Step succeeded: check if more steps remain
    next_idx = idx + 1
    if next_idx < len(plan_steps):
        logger.info(f"[Router] Advancing to step index {next_idx}/{len(plan_steps)}.")
        return "step_executor"

    # All steps completed
    logger.info("[Router] All plan steps executed. Transitioning to final_responder.")
    return "final_responder"


# Advance step index helper
async def advance_step_node(state: NexusState) -> dict:
    """Increments current_step_index pointer when advancing to the next step."""
    idx = state.get("current_step_index", 0) + 1
    return {"current_step_index": idx}


# ---------------------------------------------------------------------------
# Graph Compilation with Checkpointer (SqliteSaver / AsyncSqliteSaver)
# ---------------------------------------------------------------------------

def get_sqlite_checkpointer(db_path: Optional[str] = None) -> SqliteSaver:
    """Initializes and returns sync SqliteSaver checkpoint storage."""
    target_path = Path(db_path) if db_path else resolve_safe_workspace_path("memory/nexus_checkpoints.db")
    target_path.parent.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(str(target_path), check_same_thread=False)
    return SqliteSaver(conn)


def build_nexus_intelligence_graph(checkpointer: Any = None):
    """
    Constructs and compiles the cyclical LangGraph StateGraph with:
    - Multi-turn context awareness
    - Intent detection & task decomposition
    - Cyclical multi-step execution loop
    - Dynamic replanning on failure
    - Persistent SQLite checkpointing
    """
    workflow = StateGraph(NexusState)

    # 1. Add Cognitive Nodes
    workflow.add_node("intent_and_context", intent_and_context_node)
    workflow.add_node("task_planner", task_planner_node)
    workflow.add_node("step_executor", step_executor_node)
    workflow.add_node("dynamic_replanner", dynamic_replanner_node)
    workflow.add_node("advance_step", advance_step_node)
    workflow.add_node("final_responder", final_responder_node)

    # 2. Wire Linear Start
    workflow.add_edge(START, "intent_and_context")
    workflow.add_edge("intent_and_context", "task_planner")
    workflow.add_edge("task_planner", "step_executor")

    # 3. Wire Conditional Edges from step_executor
    workflow.add_conditional_edges(
        "step_executor",
        route_step_execution,
        {
            "dynamic_replanner": "dynamic_replanner",
            "step_executor": "advance_step",
            "final_responder": "final_responder",
        },
    )

    # 4. Wire Loops Back to Execution
    workflow.add_edge("dynamic_replanner", "step_executor")
    workflow.add_edge("advance_step", "step_executor")

    # 5. Wire Exit
    workflow.add_edge("final_responder", END)

    # Default to MemorySaver if no checkpointer provided for sync/async compatibility
    if checkpointer is None:
        checkpointer = MemorySaver()

    return workflow.compile(checkpointer=checkpointer)


# Singleton compiled graph instance
nexus_ai_graph = build_nexus_intelligence_graph()
