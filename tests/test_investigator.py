from pathlib import Path

import pytest

from incident_investigator import core, evaluate

ROOT = Path(__file__).resolve().parent.parent
CASES_DIR = ROOT / "cases"
RUNBOOKS_DIR = ROOT / "runbooks"

CASE_FILES = sorted(CASES_DIR.glob("*.json"))
CASES = [core.load_case(path) for path in CASE_FILES]
CASE_IDS = [case["id"] for case in CASES]
CASE_BY_ID = {case["id"]: case for case in CASES}
FAULT_CASES = [c for c in CASES if c["expected_category"] != "healthy_no_fault"]


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_each_case_matches_expected_category(case):
    diagnosis = core.investigate_case(case, runbooks_dir=RUNBOOKS_DIR)
    assert diagnosis.category == case["expected_category"]


@pytest.mark.parametrize("case", FAULT_CASES, ids=[c["id"] for c in FAULT_CASES])
def test_fault_cases_cite_evidence(case):
    diagnosis = core.investigate_case(case, runbooks_dir=RUNBOOKS_DIR)
    assert diagnosis.evidence, f"no evidence for {case['id']}"


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_every_proposed_action_requires_approval(case):
    diagnosis = core.investigate_case(case, runbooks_dir=RUNBOOKS_DIR)
    for action in diagnosis.proposed_actions:
        assert action["requires_approval"] is True


def test_healthy_case_returns_no_fault():
    diagnosis = core.investigate_case(
        CASE_BY_ID["case-07-healthy"], runbooks_dir=RUNBOOKS_DIR
    )
    assert diagnosis.category == "healthy_no_fault"
    assert diagnosis.confidence == "high"
    assert diagnosis.evidence == []
    assert diagnosis.proposed_actions == []


def test_ambiguous_case_returns_low_confidence():
    diagnosis = core.investigate_case(
        CASE_BY_ID["case-08-ambiguous"], runbooks_dir=RUNBOOKS_DIR
    )
    assert diagnosis.confidence == "low"


def test_low_confidence_says_what_data_would_help():
    diagnosis = core.investigate_case(
        CASE_BY_ID["case-08-ambiguous"], runbooks_dir=RUNBOOKS_DIR
    )
    assert diagnosis.missing_data
    joined = " ".join(diagnosis.missing_data)
    assert "logs" in joined


def test_image_pull_case_is_high_confidence():
    diagnosis = core.investigate_case(
        CASE_BY_ID["case-01-image-pull"], runbooks_dir=RUNBOOKS_DIR
    )
    assert diagnosis.category == "image_pull_failure"
    assert diagnosis.confidence == "high"


def test_core_module_has_no_execution_primitives():
    source = (ROOT / "incident_investigator" / "core.py").read_text(
        encoding="utf-8"
    )
    for banned in ("subprocess", "os.system", "kubectl"):
        assert banned not in source, f"core.py must not reference {banned}"


def test_evaluation_reports_full_accuracy_on_shipped_cases():
    results = evaluate.run_evaluation(
        cases_dir=CASES_DIR, runbooks_dir=RUNBOOKS_DIR
    )
    assert results, "no cases were evaluated"
    correct = sum(1 for r in results if r["category_match"])
    assert correct == len(results)
    assert all(r["passed"] for r in results)


def test_runbook_citations_point_at_real_files_and_sections():
    checked = 0
    for case in FAULT_CASES:
        diagnosis = core.investigate_case(case, runbooks_dir=RUNBOOKS_DIR)
        assert diagnosis.runbook_citations, f"no citations for {case['id']}"
        for citation in diagnosis.runbook_citations:
            path = RUNBOOKS_DIR / citation["file"]
            assert path.exists(), f"missing runbook file {citation['file']}"
            headings = [
                line.lstrip("#").strip()
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.startswith("#")
            ]
            assert citation["section"] in headings
            checked += 1
    assert checked >= len(FAULT_CASES)


def test_investigation_is_deterministic():
    case = CASE_BY_ID["case-02-crash-loop"]
    first = core.investigate_case(case, runbooks_dir=RUNBOOKS_DIR).to_dict()
    second = core.investigate_case(case, runbooks_dir=RUNBOOKS_DIR).to_dict()
    assert first == second


def test_diagnosis_is_structured():
    diagnosis = core.investigate_case(
        CASE_BY_ID["case-03-oom-killed"], runbooks_dir=RUNBOOKS_DIR
    )
    as_dict = diagnosis.to_dict()
    for key in (
        "case_id",
        "category",
        "confidence",
        "evidence",
        "runbook_citations",
        "proposed_actions",
        "missing_data",
    ):
        assert key in as_dict
    assert as_dict["confidence"] in ("high", "medium", "low")
