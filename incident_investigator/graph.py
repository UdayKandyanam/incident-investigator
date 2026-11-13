"""The same investigation expressed as a LangGraph state graph.

The graph adds orchestration, not new logic. Each node calls the same
functions the deterministic path uses, in the same order: collect
findings, score causes, retrieve runbooks, compose diagnosis. Importing
this module needs the optional agent extra (langgraph, langchain-core).
The package and the CLI work without it.
"""

from __future__ import annotations

from typing import TypedDict

from . import core


class InvestigationState(TypedDict, total=False):
    case: dict
    runbooks_dir: str
    findings: list
    scores: dict
    category: str
    confidence: str
    citations: list
    diagnosis: core.Diagnosis


def _collect_findings(state):
    findings = core.collect_findings(state["case"].get("snapshot", {}))
    return {"findings": findings}


def _score_causes(state):
    scores = core.score_causes(state["findings"])
    category, confidence = core.pick_category(scores)
    return {"scores": scores, "category": category, "confidence": confidence}


def _retrieve_runbooks(state):
    category = state["category"]
    evidence = [
        f.evidence for f in state["findings"] if f.category == category
    ]
    runbooks_dir = state.get("runbooks_dir") or core.default_runbooks_dir()
    citations = core.retrieve_runbooks(category, evidence, runbooks_dir)
    return {"citations": citations}


def _compose_diagnosis(state):
    diagnosis = core.compose_diagnosis(
        state["case"],
        state["findings"],
        state["scores"],
        state["category"],
        state["confidence"],
        state["citations"],
    )
    return {"diagnosis": diagnosis}


def build_graph():
    from langgraph.graph import END, StateGraph

    graph = StateGraph(InvestigationState)
    graph.add_node("collect_findings", _collect_findings)
    graph.add_node("score_causes", _score_causes)
    graph.add_node("retrieve_runbooks", _retrieve_runbooks)
    graph.add_node("compose_diagnosis", _compose_diagnosis)
    graph.set_entry_point("collect_findings")
    graph.add_edge("collect_findings", "score_causes")
    graph.add_edge("score_causes", "retrieve_runbooks")
    graph.add_edge("retrieve_runbooks", "compose_diagnosis")
    graph.add_edge("compose_diagnosis", END)
    return graph.compile()


def run_graph(case, runbooks_dir=None):
    """Run one case through the graph and return the Diagnosis."""
    app = build_graph()
    state = {"case": case}
    if runbooks_dir is not None:
        state["runbooks_dir"] = str(runbooks_dir)
    result = app.invoke(state)
    return result["diagnosis"]
