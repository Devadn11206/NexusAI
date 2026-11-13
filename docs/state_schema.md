# NEXUS AI: State Schema Specification

## 1. Overview
The central state within NEXUS AI's LangGraph runtime is defined by `NexusState`. All 7 specialized agent nodes receive, enrich, and transition this state across the execution lifecycle.

## 2. TypedDict Definition

```python
from typing import TypedDict, Literal, Optional, Any, Dict, List
from datetime import datetime

class TaskNode(TypedDict):
    step_id: str
    agent: str
    description: str
    dependencies: List[str]
    status: Literal["PENDING", "IN_PROGRESS", "COMPLETED", "FAILED", "SKIPPED"]
    result: Optional[Any]

class TaskGraph(TypedDict):
    nodes: Dict[str, TaskNode]
    edges: List[Dict[str, str]]  # {"from": "step_1", "to": "step_2"}

class NexusState(TypedDict):
    # Channel and Ingress Identity
    user_id: str                              # System internal user ID (UUID)
    chat_id: str                              # Channel specific unique chat/sender ID
    channel: Literal["telegram", "whatsapp"]  # Ingress channel type
    raw_prompt: str                           # Initial instruction received via webhook

    # Task Graph & Progression (DAG)
    task_graph: TaskGraph                     # Synthesized execution graph
    current_step_id: Optional[str]            # Active step identifier in execution

    # Outputs & Artifacts
    agent_outputs: Dict[str, Any]             # Keyed by step_id or agent_name
    artifacts: List[Dict[str, Any]]           # File paths, screenshots, generated code
    token_usage: Dict[str, int]               # Cumulative token consumption {prompt, completion, total}

    # Human-in-the-Loop (HITL) Gate
    hitl_approval_required: bool              # Interrupt trigger flag
    hitl_payload: Optional[Dict[str, Any]]    # Details on destructive or critical actions needing approval

    # Diagnostics & Observability
    error_logs: List[Dict[str, Any]]          # Recorded runtime exceptions and tracebacks
```

## 3. Field Semantic Definitions

| Field Name | Type | Description |
| :--- | :--- | :--- |
| `user_id` | `str` | Internal UUID mapping to `users.id` in PostgreSQL. |
| `chat_id` | `str` | Native telegram `chat_id` or WhatsApp phone number (`E.164`). |
| `channel` | `Literal["telegram", "whatsapp"]` | Communication bus that originated the command and awaits updates. |
| `raw_prompt` | `str` | Raw unmodified text or media caption sent by the authorized user. |
| `task_graph` | `TaskGraph` | Directed Acyclic Graph broken down by the Planner agent. |
| `current_step_id` | `Optional[str]` | The ID of the node currently executing in the graph. |
| `agent_outputs` | `Dict[str, Any]` | Intermediate outputs across Planner, Coder, Tool Executor, etc. |
| `artifacts` | `List[Dict[str, Any]]` | Structured files generated inside `./workspace/` (metadata, path, mime type). |
| `token_usage` | `Dict[str, int]` | Tracking for model token budgets across nodes. |
| `hitl_approval_required` | `bool` | Set to `True` when security policies flag sensitive tools (e.g. bash execution, file deletion). Halts LangGraph until explicit `/approve` command. |
| `hitl_payload` | `Optional[Dict[str, Any]]` | Context presented to the user on Telegram/WhatsApp to approve/reject. |
| `error_logs` | `List[Dict[str, Any]]` | Execution error stack traces and recovery attempts. |

