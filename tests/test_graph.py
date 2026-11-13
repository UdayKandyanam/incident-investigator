from pathlib import Path

import pytest

pytest.importorskip("langgraph")

from incident_investigator import core  # noqa: E402
from incident_investigator.graph import run_graph  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CASES_DIR = ROOT / "cases"
RUNBOOKS_DIR = ROOT / "runbooks"

GRAPH_CASE_IDS = ["case-02-crash-loop", "case-03-oom-killed"]


@pytest.mark.parametrize("case_id", GRAPH_CASE_IDS)
def test_graph_matches_core_category(case_id):
    case = core.load_case(CASES_DIR / f"{case_id}.json")
    expected = core.investigate_case(case, runbooks_dir=RUNBOOKS_DIR)
    via_graph = run_graph(case, runbooks_dir=RUNBOOKS_DIR)
    assert via_graph.category == expected.category
    assert via_graph.category == case["expected_category"]
    assert via_graph.confidence == expected.confidence
