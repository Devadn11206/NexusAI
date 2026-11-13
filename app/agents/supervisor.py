import logging
from typing import Dict, Any, Optional
from app.agents.state import NexusState

logger = logging.getLogger(__name__)

MAX_RETRIES = 5


def find_next_executable_step(state: NexusState) -> Optional[Dict[str, Any]]:
    """
    Scans the DAG in task_graph to find the first step that is not yet completed
    and whose dependencies in `depends_on` are fully satisfied.
    """
    steps = state.get("task_graph", {}).get("steps", [])
    completed = set(state.get("completed_steps", []))
    failed = set(state.get("failed_steps", []))

    for step in steps:
        step_id = step.get("step_id")
        if step_id in completed or step_id in failed:
            continue

        dependencies = step.get("depends_on", [])
        # Step is ready if all required prior steps are completed
        if all(dep in completed for dep in dependencies):
            return step

    return None


async def supervisor_node(state: NexusState) -> Dict[str, Any]:
    """
    Supervisor Router Node:
    Monitors graph state, advances execution across the DAG,
    tracks retry circuit breakers, and transitions to verification upon completion.
    """
    steps = state.get("task_graph", {}).get("steps", [])
    completed = state.get("completed_steps", [])
    retry_counts = dict(state.get("retry_counts", {}))
    failed = list(state.get("failed_steps", []))

    logger.info(
        f"[Supervisor] Checking DAG progress: {len(completed)}/{len(steps)} steps finished. "
        f"Completed: {completed}"
    )

    # 1. Check if all steps in DAG are completed
    if steps and len(completed) >= len(steps):
        logger.info("[Supervisor] All DAG steps completed. Transitioning to verification.")
        return {
            "current_step_id": None,
            "is_graph_complete": True,
        }

    # 2. Find next ready step
    next_step = find_next_executable_step(state)

    if not next_step:
        # No step ready - either all done or circular dependency / blocked
        logger.info("[Supervisor] No further executable steps identified. Closing graph.")
        return {
            "current_step_id": None,
            "is_graph_complete": True,
        }

    step_id = next_step.get("step_id")
    target_agent = next_step.get("target_agent", "SupervisorAgent")

    # 3. Circuit breaker check
    current_retries = retry_counts.get(step_id, 0)
    if current_retries >= MAX_RETRIES:
        logger.error(f"[Supervisor] Circuit breaker tripped for step '{step_id}' ({current_retries} retries).")
        if step_id not in failed:
            failed.append(step_id)
        return {
            "failed_steps": failed,
            "current_step_id": None,
            "is_graph_complete": True,
        }

    logger.info(f"[Supervisor] Dispatching next step '{step_id}' to agent '{target_agent}'.")
    return {
        "current_step_id": step_id,
        "is_graph_complete": False,
    }


def route_next_agent(state: NexusState) -> str:
    """
    Conditional routing function for LangGraph.
    Inspects active step and routes from supervisor to assigned worker node or END.
    """
    if state.get("is_graph_complete", False):
        return "verification_agent"

    current_id = state.get("current_step_id")
    if not current_id:
        return "verification_agent"

    steps = state.get("task_graph", {}).get("steps", [])
    target_agent = None
    for step in steps:
        if step.get("step_id") == current_id:
            target_agent = step.get("target_agent")
            break

    agent_str = str(target_agent).lower() if target_agent else ""

    if "music" in agent_str:
        return "music_agent"
    elif "document" in agent_str or "paper" in agent_str:
        return "document_agent"
    elif "browser" in agent_str:
        return "browser_agent"
    elif "file" in agent_str:
        return "file_agent"
    elif "developer" in agent_str:
        return "developer_agent"
    elif "computer" in agent_str:
        return "computer_agent"
    else:
        # Default fallback to file_agent or developer_agent
        return "developer_agent"

