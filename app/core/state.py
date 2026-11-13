"""
NEXUS AI - Central Cognitive State Definition
Defines the stateful, cyclical LangGraph state schema with explicit reducers
for multi-turn context preservation, dynamic replanning, and multi-step execution.
"""

from typing import TypedDict, Annotated, List, Dict, Any, Optional
from langgraph.graph.message import add_messages


def _reduce_artifacts(left: Optional[List[str]], right: Optional[List[str]]) -> List[str]:
    """Combines artifact paths while maintaining uniqueness."""
    res = list(left or [])
    for item in (right or []):
        if item and item not in res:
            res.append(item)
    return res


def _reduce_execution_logs(left: Optional[List[Dict[str, Any]]], right: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """Appends new step execution logs."""
    res = list(left or [])
    if right:
        res.extend(right)
    return res


class NexusState(TypedDict, total=False):
    """
    Central LangGraph state schema for NEXUS AI Core AI Intelligence.
    Tracks multi-turn context, intent classification, multi-step plan execution,
    logs, retry bounding, and generated artifacts.
    """
    # 1. Multi-turn conversation context
    messages: Annotated[List[Any], add_messages]

    # 2. Classified intent & entity extraction
    user_intent: Dict[str, Any]

    # 3. Ordered atomic plan steps
    # Each step: {step_id: str, description: str, tool_name: str, tool_args: dict, status: "pending" | "running" | "completed" | "failed"}
    plan_steps: List[Dict[str, Any]]

    # 4. Multi-step execution progress pointer
    current_step_index: int

    # 5. Execution logs & exception traces
    # Each log: {step_id: str, output: Any, error_traceback: Optional[str]}
    execution_logs: Annotated[List[Dict[str, Any]], _reduce_execution_logs]

    # 6. Replan count (bounded to max 3)
    replan_count: int

    # 7. Collected artifact paths (screenshots, generated reports) for Telegram dispatch
    artifacts: Annotated[List[str], _reduce_artifacts]

    # 8. Final synthesized answer
    final_response: Optional[str]
