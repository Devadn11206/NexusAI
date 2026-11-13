from typing import TypedDict, Literal, Optional, Any, Dict, List


class NexusState(TypedDict):
    """
    Central LangGraph State for NEXUS AI Multi-Agent Engine.
    Tracks DAG task progression, individual step completions, retries,
    node outputs, and HITL gate interrupts.
    """
    # Ingress Origin & Sinks
    user_id: str
    chat_id: str
    channel: Literal["telegram", "whatsapp"]
    raw_prompt: str

    # Execution Progression & DAG
    task_graph: Dict[str, Any]
    current_step_id: Optional[str]
    completed_steps: List[str]
    failed_steps: List[str]
    step_results: Dict[str, Any]
    retry_counts: Dict[str, int]
    is_graph_complete: bool

    # Node Output & Artifact Storage
    agent_outputs: Dict[str, Any]
    artifacts: List[Dict[str, Any]]
    token_usage: Dict[str, int]

    # Human-In-The-Loop Interrupt Mechanism
    hitl_approval_required: bool
    hitl_payload: Optional[Dict[str, Any]]

    # System Logs & Error Tracking
    error_logs: List[Dict[str, Any]]
