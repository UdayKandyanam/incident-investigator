"""Score the investigator against the shipped case set.

Each case carries the category a correct diagnosis should reach and the
evidence strings it should cite. Evaluation is the quality gate for this
project: a change that drops accuracy does not ship.
"""

from __future__ import annotations

from pathlib import Path

from . import core


def default_cases_dir():
    return Path(__file__).resolve().parent.parent / "cases"


def evaluate_case(case, runbooks_dir=None):
    diagnosis = core.investigate_case(case, runbooks_dir=runbooks_dir)
    expected = case.get("expected_category")
    category_match = diagnosis.category == expected
    required = case.get("expected_evidence") or []
    joined = "\n".join(diagnosis.evidence)
    evidence_match = True
    matched_evidence = None
    if required:
        evidence_match = False
        for item in required:
            if item in joined:
                evidence_match = True
                matched_evidence = item
                break
    return {
        "case_id": case.get("id", "unknown"),
        "expected": expected,
        "actual": diagnosis.category,
        "confidence": diagnosis.confidence,
        "category_match": category_match,
        "evidence_match": evidence_match,
        "matched_evidence": matched_evidence,
        "passed": category_match and evidence_match,
    }


def run_evaluation(cases_dir=None, runbooks_dir=None):
    if cases_dir is None:
        cases_dir = default_cases_dir()
    results = []
    for path in sorted(Path(cases_dir).glob("*.json")):
        case = core.load_case(path)
        results.append(evaluate_case(case, runbooks_dir=runbooks_dir))
    return results


def format_scorecard(results):
    lines = []
    for result in results:
        status = "PASS" if result["passed"] else "FAIL"
        lines.append(
            f"{status}  {result['case_id']}: expected {result['expected']}, "
            f"got {result['actual']} (confidence {result['confidence']})"
        )
        if not result["category_match"]:
            lines.append("       category mismatch")
        if not result["evidence_match"]:
            lines.append("       no expected evidence string in the diagnosis")
    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    correct = sum(1 for r in results if r["category_match"])
    accuracy = (correct / total * 100) if total else 0.0
    lines.append("")
    lines.append(f"Cases passed: {passed}/{total}")
    lines.append(f"Category accuracy: {accuracy:.0f}% ({correct}/{total})")
    return "\n".join(lines)


def main():
    results = run_evaluation()
    print(format_scorecard(results))
    return 0 if all(r["passed"] for r in results) else 1
