"""Deterministic investigator for synthetic Kubernetes incident cases.

The investigator reads one case snapshot, runs a set of finding rules over
it, scores candidate root causes, pulls the runbook sections that match,
and returns a structured diagnosis. It only reads. Every action it proposes
is marked as requiring human approval, and nothing in this module executes
anything.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

CATEGORIES = (
    "image_pull_failure",
    "crash_loop",
    "oom_killed",
    "unschedulable_resources",
    "bad_config",
    "node_pressure",
    "healthy_no_fault",
)

PRESSURE_CONDITIONS = ("MemoryPressure", "DiskPressure", "PIDPressure")
IMAGE_PULL_REASONS = ("ImagePullBackOff", "ErrImagePull")

SUMMARIES = {
    "image_pull_failure": "Pods cannot pull their image, so the containers never start.",
    "crash_loop": "A container starts, exits, and restarts in a loop.",
    "oom_killed": "A container was killed for exceeding its memory limit.",
    "unschedulable_resources": "Pods cannot be placed on any node, so they stay Pending.",
    "bad_config": "A pod references config that does not exist, so its container cannot be created.",
    "node_pressure": "A node is under resource pressure and pods are being evicted from it.",
    "healthy_no_fault": "No fault found. Pods are running, deployments are at full replicas, and nodes report no pressure.",
}

PROPOSED_ACTIONS = {
    "image_pull_failure": [
        "Verify the image reference in the deployment exists in the registry, and correct the tag if it is wrong",
        "Check the image pull secret in the pod namespace and refresh it if the registry credentials rotated",
        "Roll the corrected deployment and confirm one pod becomes ready before closing the incident",
    ],
    "crash_loop": [
        "Read the previous container logs to find the startup error before changing anything",
        "Roll back the deployment if the loop began with the latest release",
        "Fix the failing config or dependency, then watch the restart count stay flat for ten minutes",
    ],
    "oom_killed": [
        "Compare the memory limit with the peak usage of the workload and size the limit to the real working set",
        "Check the hot code path for unbounded caching or whole file loads and cap it",
        "Raise the memory request together with the limit so the scheduler places the pod honestly",
    ],
    "unschedulable_resources": [
        "Compare the pod resource requests with free capacity on the nodes and lower any request that exceeds measured usage",
        "Add node capacity if the requests reflect real usage",
        "Clear any stale cordons left over from node maintenance",
    ],
    "bad_config": [
        "Create or restore the missing configmap or secret in the pod namespace",
        "Check the deployment for typos in its config references before rolling anything out",
        "Restart the affected pods and confirm they leave CreateContainerConfigError",
    ],
    "node_pressure": [
        "Let the scheduler replace the evicted pods on a healthy node, or move them there directly",
        "Find what is consuming memory and disk on the pressured node and clear or cap it",
        "Add node capacity or rebalance resource requests if pressure repeats across nodes",
    ],
    "healthy_no_fault": [],
}

MISSING_DATA_BY_CATEGORY = {
    "crash_loop": [
        "previous container logs for the restarting pod",
        "the termination reason and exit code of the last exit",
        "cluster events from the time of the restarts",
    ],
    "oom_killed": [
        "memory usage history for the container leading up to the kill",
        "cluster events from the time of the kill",
    ],
    "image_pull_failure": [
        "the full pull error from the kubelet event",
        "the list of tags the build pushed to the registry",
    ],
}

GENERIC_MISSING_DATA = [
    "cluster events from the time of the incident",
    "a second snapshot taken a few minutes later, to see whether the state is changing",
]

QUERY_TERMS = {
    "image_pull_failure": "image pull failed registry tag manifest unknown pull secret backoff",
    "crash_loop": "crash loop restart count exit code previous logs backoff startup",
    "oom_killed": "oomkilled memory limit pressure killed exit code 137 usage",
    "unschedulable_resources": "scheduling pending failedscheduling insufficient cpu requests capacity nodes",
    "bad_config": "config missing configmap secret not found startup container create",
    "node_pressure": "memory pressure evicted node capacity disk pressure pods",
}

STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with",
    "is", "are", "was", "were", "it", "its", "at", "by", "from", "that",
    "this", "so", "be", "as", "has", "have", "no", "not",
}


@dataclass
class Finding:
    category: str
    points: int
    evidence: str


@dataclass
class Diagnosis:
    case_id: str
    title: str
    category: str
    confidence: str
    summary: str
    evidence: list = field(default_factory=list)
    scores: dict = field(default_factory=dict)
    runbook_citations: list = field(default_factory=list)
    proposed_actions: list = field(default_factory=list)
    missing_data: list = field(default_factory=list)

    def to_dict(self):
        return asdict(self)


def load_case(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def default_runbooks_dir():
    return Path(__file__).resolve().parent.parent / "runbooks"


def collect_findings(snapshot):
    """Run every finding rule over a snapshot and return the findings."""
    findings = []
    pods = snapshot.get("pods", []) or []
    events = snapshot.get("events", []) or []
    nodes = snapshot.get("nodes", []) or []

    for pod in pods:
        pod_name = pod.get("name", "unknown")
        for container in pod.get("containers", []) or []:
            where = f"pod {pod_name} container {container.get('name', 'unknown')}"
            reason = container.get("reason")
            restarts = container.get("restart_count", 0) or 0
            last_reason = container.get("last_termination_reason")

            if reason in IMAGE_PULL_REASONS:
                findings.append(Finding(
                    "image_pull_failure", 6,
                    f"{where} is in {reason} for image {container.get('image')} "
                    f"and has never started (restart count {restarts})",
                ))
            if reason == "CrashLoopBackOff":
                findings.append(Finding(
                    "crash_loop", 6,
                    f"{where} is in CrashLoopBackOff (restart count {restarts})",
                ))
            if reason == "CreateContainerConfigError":
                findings.append(Finding(
                    "bad_config", 6,
                    f"{where} is in CreateContainerConfigError, so a referenced "
                    "configmap or secret could not be loaded",
                ))
            if last_reason == "OOMKilled":
                points = 9 if container.get("last_exit_code") == 137 else 7
                memory = (
                    container.get("resources", {}).get("limits", {}).get("memory")
                )
                text = (
                    f"{where} was OOMKilled on its last exit "
                    f"(restart count {restarts}"
                )
                if memory:
                    text += f", memory limit {memory}"
                text += ")"
                findings.append(Finding("oom_killed", points, text))
            if (
                restarts >= 2
                and reason != "CrashLoopBackOff"
                and last_reason != "OOMKilled"
            ):
                findings.append(Finding(
                    "crash_loop", 2,
                    f"{where} has restart count {restarts} with no recorded "
                    "termination reason, which points to repeated exits",
                ))

        if pod.get("termination_reason") == "Evicted" or (
            pod.get("phase") == "Failed" and pod.get("reason") == "Evicted"
        ):
            findings.append(Finding(
                "node_pressure", 3,
                f"pod {pod_name} was Evicted from node {pod.get('node')}",
            ))

        container_reasons = {
            c.get("reason") for c in pod.get("containers", []) or []
        }
        if (
            pod.get("phase") == "Pending"
            and not pod.get("node")
            and not (container_reasons - {None})
        ):
            findings.append(Finding(
                "unschedulable_resources", 2,
                f"pod {pod_name} has been Pending with no node assigned",
            ))

    for event in events:
        message = event.get("message", "") or ""
        reason = event.get("reason", "") or ""
        obj = event.get("object", "unknown object")
        lowered = message.lower()
        if "failed to pull image" in lowered:
            findings.append(Finding(
                "image_pull_failure", 4, f"event on {obj}: {message}",
            ))
        if reason == "FailedScheduling":
            findings.append(Finding(
                "unschedulable_resources", 7,
                f"event on {obj}: FailedScheduling, {message}",
            ))
        if reason == "BackOff" and "restarting failed container" in lowered:
            findings.append(Finding(
                "crash_loop", 2, f"event on {obj}: {message}",
            ))
        if reason == "Evicted":
            findings.append(Finding(
                "node_pressure", 4, f"event on {obj}: {message}",
            ))
        if "not found" in lowered and (
            "configmap" in lowered or "secret" in lowered
        ):
            findings.append(Finding(
                "bad_config", 4, f"event on {obj}: {message}",
            ))

    for node in nodes:
        for condition in node.get("conditions", []) or []:
            if (
                condition.get("type") in PRESSURE_CONDITIONS
                and condition.get("status") == "True"
            ):
                findings.append(Finding(
                    "node_pressure", 5,
                    f"node {node.get('name')} reports {condition.get('type')}",
                ))

    return findings


def score_causes(findings):
    scores = {}
    for finding in findings:
        scores[finding.category] = scores.get(finding.category, 0) + finding.points
    return scores


def _rank(scores):
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))


def pick_category(scores):
    """Return (category, confidence) for a score map."""
    if not scores:
        return "healthy_no_fault", "high"
    ranked = _rank(scores)
    top_category, top_points = ranked[0]
    second_points = ranked[1][1] if len(ranked) > 1 else 0
    if top_points >= 8 and top_points - second_points >= 4:
        confidence = "high"
    elif top_points >= 5:
        confidence = "medium"
    else:
        confidence = "low"
    return top_category, confidence


def _tokens(text):
    return [
        tok
        for tok in re.findall(r"[a-z0-9]+", text.lower())
        if tok not in STOPWORDS and len(tok) > 1
    ]


def _split_sections(text):
    sections = []
    current_title = None
    current_lines = []
    for line in text.splitlines():
        if line.startswith("#"):
            if current_title is not None:
                sections.append((current_title, "\n".join(current_lines)))
            current_title = line.lstrip("#").strip()
            current_lines = []
        else:
            current_lines.append(line)
    if current_title is not None:
        sections.append((current_title, "\n".join(current_lines)))
    return sections


def load_runbook_sections(runbooks_dir):
    runbooks_dir = Path(runbooks_dir)
    sections = []
    for path in sorted(runbooks_dir.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        for title, body in _split_sections(text):
            tokens = _tokens(title + " " + body)
            if tokens:
                sections.append(
                    {"file": path.name, "section": title, "tokens": tokens}
                )
    return sections


def retrieve_runbooks(category, evidence, runbooks_dir, limit=2):
    """Rank runbook sections with BM25 and return the best citations."""
    if category == "healthy_no_fault":
        return []
    sections = load_runbook_sections(runbooks_dir)
    if not sections:
        return []
    query = _tokens(QUERY_TERMS.get(category, ""))
    for item in evidence:
        query.extend(_tokens(item))
    query = list(dict.fromkeys(query))
    if not query:
        return []

    doc_count = len(sections)
    doc_freq = Counter()
    for section in sections:
        for tok in set(section["tokens"]):
            doc_freq[tok] += 1
    avg_len = sum(len(s["tokens"]) for s in sections) / doc_count
    k1, b = 1.5, 0.75

    scored = []
    for section in sections:
        counts = Counter(section["tokens"])
        length = len(section["tokens"])
        score = 0.0
        for tok in query:
            freq = counts.get(tok, 0)
            if not freq:
                continue
            idf = math.log(1 + (doc_count - doc_freq[tok] + 0.5) / (doc_freq[tok] + 0.5))
            denom = freq + k1 * (1 - b + b * length / avg_len)
            score += idf * (freq * (k1 + 1)) / denom
        if score > 0:
            scored.append((score, section))
    scored.sort(key=lambda item: (-item[0], item[1]["file"], item[1]["section"]))
    return [
        {"file": section["file"], "section": section["section"], "score": round(score, 2)}
        for score, section in scored[:limit]
    ]


def compose_diagnosis(case, findings, scores, category, confidence, citations):
    if category == "healthy_no_fault":
        evidence = []
    else:
        evidence = [f.evidence for f in findings if f.category == category]
    missing_data = []
    if confidence == "low" and category != "healthy_no_fault":
        missing_data = list(
            MISSING_DATA_BY_CATEGORY.get(category, GENERIC_MISSING_DATA)
        )
        if not (case.get("snapshot", {}).get("events")):
            missing_data.append("any cluster events at all: this snapshot contains none")
    actions = [
        {"action": text, "requires_approval": True}
        for text in PROPOSED_ACTIONS.get(category, [])
    ]
    return Diagnosis(
        case_id=case.get("id", "unknown"),
        title=case.get("title", ""),
        category=category,
        confidence=confidence,
        summary=SUMMARIES[category],
        evidence=evidence,
        scores=dict(scores),
        runbook_citations=citations,
        proposed_actions=actions,
        missing_data=missing_data,
    )


def investigate_case(case, runbooks_dir=None):
    """Investigate one case dict and return a Diagnosis."""
    if runbooks_dir is None:
        runbooks_dir = default_runbooks_dir()
    snapshot = case.get("snapshot", {})
    findings = collect_findings(snapshot)
    scores = score_causes(findings)
    category, confidence = pick_category(scores)
    category_evidence = [f.evidence for f in findings if f.category == category]
    citations = retrieve_runbooks(category, category_evidence, runbooks_dir)
    return compose_diagnosis(
        case, findings, scores, category, confidence, citations
    )
