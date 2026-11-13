"""Command line entry point.

Usage:
    python -m incident_investigator investigate <case.json>
    python -m incident_investigator evaluate
"""

from __future__ import annotations

import json
import sys

from . import core, evaluate


def format_diagnosis(diagnosis):
    lines = []
    lines.append(f"Case: {diagnosis.case_id}, {diagnosis.title}")
    lines.append(
        f"Diagnosis: {diagnosis.category} (confidence: {diagnosis.confidence})"
    )
    lines.append(f"Summary: {diagnosis.summary}")
    if diagnosis.evidence:
        lines.append("")
        lines.append("Evidence:")
        for item in diagnosis.evidence:
            lines.append(f"- {item}")
    if diagnosis.runbook_citations:
        lines.append("")
        lines.append("Runbook sections:")
        for citation in diagnosis.runbook_citations:
            lines.append(
                f"- runbooks/{citation['file']}, section \"{citation['section']}\""
            )
    if diagnosis.proposed_actions:
        lines.append("")
        lines.append("Proposed actions (each one requires human approval):")
        for action in diagnosis.proposed_actions:
            lines.append(f"- {action['action']} [requires_approval: true]")
    else:
        lines.append("")
        lines.append("Proposed actions: none. No fault found.")
    if diagnosis.missing_data:
        lines.append("")
        lines.append("What would raise confidence:")
        for item in diagnosis.missing_data:
            lines.append(f"- {item}")
    return "\n".join(lines)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print(__doc__.strip())
        return 2
    command = argv[0]
    if command == "investigate":
        if len(argv) != 2:
            print("usage: python -m incident_investigator investigate <case.json>")
            return 2
        case = core.load_case(argv[1])
        diagnosis = core.investigate_case(case)
        print(format_diagnosis(diagnosis))
        return 0
    if command == "evaluate":
        return evaluate.main()
    if command == "investigate-json":
        if len(argv) != 2:
            print(
                "usage: python -m incident_investigator investigate-json <case.json>"
            )
            return 2
        case = core.load_case(argv[1])
        diagnosis = core.investigate_case(case)
        print(json.dumps(diagnosis.to_dict(), indent=2))
        return 0
    print(f"unknown command: {command}")
    print(__doc__.strip())
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
