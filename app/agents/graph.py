import logging
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from app.agents.state import NexusState
from app.agents.supervisor import supervisor_node, route_next_agent
from app.agents.workers import (
    browser_agent_node,
    file_agent_node,
    computer_agent_node,
    verification_agent_node,
)
from app.music.music_agent import music_agent_node
from app.documents.document_agent import document_agent_node
from app.developer.developer_agent import developer_agent_node

logger = logging.getLogger(__name__)


def build_nexus_graph(checkpointer=None):
    """
    Constructs the LangGraph Multi-Agent StateGraph with dynamic DAG routing.
    Includes worker nodes, supervisor orchestrator, and verification sink.
    """
    workflow = StateGraph(NexusState)

    # 1. Register Nodes
    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("music_agent", music_agent_node)
    workflow.add_node("browser_agent", browser_agent_node)
    workflow.add_node("file_agent", file_agent_node)
    workflow.add_node("developer_agent", developer_agent_node)
    workflow.add_node("computer_agent", computer_agent_node)
    workflow.add_node("document_agent", document_agent_node)
    workflow.add_node("verification_agent", verification_agent_node)

    # 2. Add Ingress Edge
    workflow.add_edge(START, "supervisor")

    # 3. Add Conditional Dispatch from Supervisor
    workflow.add_conditional_edges(
        "supervisor",
        route_next_agent,
        {
            "music_agent": "music_agent",
            "browser_agent": "browser_agent",
            "file_agent": "file_agent",
            "developer_agent": "developer_agent",
            "computer_agent": "computer_agent",
            "document_agent": "document_agent",
            "verification_agent": "verification_agent",
        },
    )

    # 4. Wire Workers back to Supervisor to form loop
    workflow.add_edge("music_agent", "supervisor")
    workflow.add_edge("browser_agent", "supervisor")
    workflow.add_edge("file_agent", "supervisor")
    workflow.add_edge("developer_agent", "supervisor")
    workflow.add_edge("computer_agent", "supervisor")
    workflow.add_edge("document_agent", "supervisor")

    # 5. Verification Node leads to final state
    workflow.add_edge("verification_agent", END)

    # Default to MemorySaver for testing/in-memory checkpointing
    saver = checkpointer or MemorySaver()
    compiled_app = workflow.compile(checkpointer=saver)

    logger.info("LangGraph NEXUS AI multi-agent workflow compiled successfully.")
    return compiled_app


# Pre-compiled graph instance
nexus_graph = build_nexus_graph()

