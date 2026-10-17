"""
LangGraph Workflow Builder: Compiles nodes, edges, retry loops, HITL, and Checkpointers.
"""
from typing import Optional, Any
from langgraph.graph import StateGraph, END
from src.graph.state import AgentState
from src.graph.nodes.normalize import ingest_and_normalize_node
from src.graph.nodes.presidio_premask import presidio_premask_node
from src.graph.nodes.classify import classify_issue_node
from src.graph.nodes.semantic_mask import semantic_mask_node
from src.graph.nodes.validator import validate_masked_state_node
from src.graph.nodes.hitl_gate import human_review_gate_node
from src.graph.nodes.fallback import fallback_scrubber_node
from src.graph.nodes.dispatcher import dispatch_to_mock_api_node
from src.graph.edges.router import should_continue_or_fallback, route_masking_tier

def build_pii_masking_graph(checkpointer: Optional[Any] = None):
    """
    Compiles and returns the LangGraph state machine.
    If checkpointer is provided (e.g. MemorySaver, PostgresSaver), thread-level
    state persistence is activated.
    """
    workflow = StateGraph(AgentState)

    # Register Nodes
    workflow.add_node("normalize", ingest_and_normalize_node)
    workflow.add_node("presidio_premask", presidio_premask_node)
    workflow.add_node("classify", classify_issue_node)
    workflow.add_node("semantic_mask", semantic_mask_node)
    workflow.add_node("validator", validate_masked_state_node)
    workflow.add_node("human_review", human_review_gate_node)
    workflow.add_node("fallback", fallback_scrubber_node)
    workflow.add_node("dispatch", dispatch_to_mock_api_node)

    # Linear Ingestion & Pre-Mask Edges
    workflow.set_entry_point("normalize")
    workflow.add_edge("normalize", "presidio_premask")
    workflow.add_edge("presidio_premask", "classify")

    # Tiered Processing / Cascade Routing Edge:
    # Routes to 'validator' (Fast-Path) if deterministic masking is complete,
    # or to 'semantic_mask' (Semantic LLM) if contextual entities exist.
    workflow.add_conditional_edges(
        "classify",
        route_masking_tier,
        {
            "fast_path": "validator",
            "semantic_path": "semantic_mask"
        }
    )
    workflow.add_edge("semantic_mask", "validator")

    # Conditional Validation Routing (Self-Correction, HITL, and Fallback)
    workflow.add_conditional_edges(
        "validator",
        should_continue_or_fallback,
        {
            "dispatch": "dispatch",
            "human_review": "human_review",
            "retry": "semantic_mask",
            "fallback": "fallback"
        }
    )

    # Terminal Paths
    workflow.add_edge("fallback", "dispatch")
    workflow.add_edge("human_review", END)  # Pauses for DPO manual sign-off
    workflow.add_edge("dispatch", END)

    # Compile with checkpointer if explicitly provided
    if checkpointer is not None:
        return workflow.compile(checkpointer=checkpointer)
    return workflow.compile()
