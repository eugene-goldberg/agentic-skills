"""StateGraph wiring.

initialize -> po_cycle -> parse_backlog -> advance_index -> (decide)
  (decide) routes:
    -> engineering cycle (author_eng_packet -> run_eng_agent -> score_eng
                          -> author_qa_packet -> run_qa_agent -> score_qa
                          -> advance_index -> back to decide)
    -> finalize

The decide step is implemented as a conditional edge from `advance_index`.
"""

from __future__ import annotations

from functools import partial

from langgraph.graph import END, StateGraph

from .config import AzureOpenAIConfig
from .nodes.engineering import author_eng_packet, run_eng_agent, score_eng
from .nodes.finalize import finalize
from .nodes.initialize import initialize
from .nodes.parse_backlog import advance_index, parse_backlog
from .nodes.po_cycle import po_cycle
from .nodes.qa import author_qa_packet, run_qa_agent, score_qa
from .state import GraphState


def _decide_after_advance(state: GraphState) -> str:
    items = state.get("backlog_items", [])
    idx = state.get("current_index", -1)
    if idx < 0 or idx >= len(items):
        return "finalize"
    return "author_eng_packet"


def build_graph(cfg: AzureOpenAIConfig):
    sg: StateGraph = StateGraph(GraphState)

    sg.add_node("initialize", initialize)
    sg.add_node("po_cycle", partial(po_cycle, cfg=cfg))
    sg.add_node("parse_backlog", parse_backlog)
    sg.add_node("advance_index", advance_index)
    sg.add_node("author_eng_packet", author_eng_packet)
    sg.add_node("run_eng_agent", partial(run_eng_agent, cfg=cfg))
    sg.add_node("score_eng", partial(score_eng, cfg=cfg))
    sg.add_node("author_qa_packet", author_qa_packet)
    sg.add_node("run_qa_agent", partial(run_qa_agent, cfg=cfg))
    sg.add_node("score_qa", partial(score_qa, cfg=cfg))
    sg.add_node("finalize", finalize)

    sg.set_entry_point("initialize")
    sg.add_edge("initialize", "po_cycle")
    sg.add_edge("po_cycle", "parse_backlog")
    sg.add_edge("parse_backlog", "advance_index")
    sg.add_conditional_edges(
        "advance_index",
        _decide_after_advance,
        {"author_eng_packet": "author_eng_packet", "finalize": "finalize"},
    )
    sg.add_edge("author_eng_packet", "run_eng_agent")
    sg.add_edge("run_eng_agent", "score_eng")
    sg.add_edge("score_eng", "author_qa_packet")
    sg.add_edge("author_qa_packet", "run_qa_agent")
    sg.add_edge("run_qa_agent", "score_qa")
    sg.add_edge("score_qa", "advance_index")
    sg.add_edge("finalize", END)

    return sg.compile()
