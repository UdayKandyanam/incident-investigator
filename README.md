# Incident Investigator

I built this to practise the part of incident work that happens before any
fix: looking at the evidence, naming the likely root cause, and being
honest about confidence. The investigator reads a synthetic Kubernetes
incident case, a snapshot of pods, events, nodes, and deployments, and
produces a structured diagnosis: a root cause category, the evidence
behind it, the runbook sections that apply, and the next actions it would
propose.

## Safety model

This comes first because it shapes everything else.

- Read-only. The investigator only reads a case file. It has no path to a
  cluster and nothing in the core can run a command.
- Proposals only. It never carries out an action. Every proposed action is
  data, and every one is marked requires_approval: true. A human decides.
- Confidence is part of the answer. Strong evidence gives a high
  confidence diagnosis. Thin evidence gives a low confidence one, plus a
  list of the data that would settle the question. It does not guess
  louder when the evidence is weak.
- Synthetic data only. Every case in this repo is invented, with made up
  service names and a fake registry. Nothing here comes from a real
  cluster.

## How it works

```text
case snapshot -> finding rules -> cause scoring -> runbook retrieval -> diagnosis
```

1. Finding rules scan the snapshot: waiting reasons such as
   CrashLoopBackOff and ImagePullBackOff, last termination reasons such
   as OOMKilled, FailedScheduling events, missing config references, node
   pressure conditions, and pods that were evicted.
2. Each finding votes for a root cause category with a weight. The scores
   decide the category, and the gap between the top score and the rest,
   plus the total weight of evidence, decides the confidence.
3. Runbook sections are ranked with a small BM25 implementation and the
   best matches are cited by file and section heading.
4. The diagnosis is composed: category, confidence, evidence, citations,
   proposed actions, and, when confidence is low, the missing data that
   would raise it.

Root cause categories: image_pull_failure, crash_loop, oom_killed,
unschedulable_resources, bad_config, node_pressure, healthy_no_fault.

## Quick start

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

Investigate one case:

```bash
.venv/bin/python -m incident_investigator investigate cases/case-02-crash-loop.json
```

```text
Case: case-02-crash-loop, Billing worker keeps restarting after a config change
Diagnosis: crash_loop (confidence: high)
Summary: A container starts, exits, and restarts in a loop.

Evidence:
- pod billing-worker-5c4d6f7b8-z9t2r container billing-worker is in CrashLoopBackOff (restart count 14)
- event on pod/billing-worker-5c4d6f7b8-z9t2r: Back-off restarting failed container billing-worker in pod billing-worker-5c4d6f7b8-z9t2r

Runbook sections:
- runbooks/crash-loops.md, section "Symptoms"
- runbooks/crash-loops.md, section "Checks"

Proposed actions (each one requires human approval):
- Read the previous container logs to find the startup error before changing anything [requires_approval: true]
- Roll back the deployment if the loop began with the latest release [requires_approval: true]
- Fix the failing config or dependency, then watch the restart count stay flat for ten minutes [requires_approval: true]
```

Run the evaluation over the whole case set:

```bash
.venv/bin/python -m incident_investigator evaluate
```

```text
PASS  case-01-image-pull: expected image_pull_failure, got image_pull_failure (confidence high)
PASS  case-02-crash-loop: expected crash_loop, got crash_loop (confidence high)
PASS  case-03-oom-killed: expected oom_killed, got oom_killed (confidence high)
PASS  case-04-unschedulable: expected unschedulable_resources, got unschedulable_resources (confidence high)
PASS  case-05-bad-config: expected bad_config, got bad_config (confidence high)
PASS  case-06-node-pressure: expected node_pressure, got node_pressure (confidence high)
PASS  case-07-healthy: expected healthy_no_fault, got healthy_no_fault (confidence high)
PASS  case-08-ambiguous: expected crash_loop, got crash_loop (confidence low)

Cases passed: 8/8
Category accuracy: 100% (8/8)
```

The case set is the interesting part. It has one case per category, one
healthy cluster that should produce no fault, and one overnight restart
case with thin evidence on purpose: the snapshot shows a restart count of
3 and nothing else, so the honest answer is a tentative category at low
confidence with a list of what to fetch next. Try it:

```bash
.venv/bin/python -m incident_investigator investigate cases/case-08-ambiguous.json
```

## The graph path

The same four steps are also expressed as a LangGraph state graph in
incident_investigator/graph.py, with one node per step. It is an optional
extra and the CLI never needs it:

```bash
.venv/bin/pip install -e ".[agent]"
```

The graph calls the same core functions in the same order, and the tests
run both paths on the same cases and require the same category and
confidence out of each.

## Design choices

- Deterministic core, graph as orchestration. The rules and scoring are
  plain Python with no dependencies, so a diagnosis can be explained line
  by line and reproduced exactly. The graph adds structure for future
  steps; it does not change answers.
- Evaluations as the quality gate. The case set ships with expected
  categories and expected evidence strings, and the test suite requires
  100 percent category accuracy on it. A rule change that breaks a case
  fails the build.
- Evidence before category. A diagnosis with no evidence strings is
  treated as a failure in evaluation, not just a wrong label.
- Runbooks are part of the repo. Four short runbooks (image pull
  failures, crash loops, memory pressure and OOM kills, scheduling
  failures) are written for this project, and citations resolve to real
  files and real section headings, which a test checks.

## Limits

- Input is a case file in this repo's snapshot format. It does not read a
  live cluster, and it does not parse the output of other tools yet.
- The rules cover the seven categories above. Anything outside them, for
  example a slow application with no restarts, comes back as the closest
  match at low confidence or as no fault.
- BM25 retrieval is lexical. It ranks the sections that share words with
  the findings, which is enough for four runbooks and would need help at
  forty.

## Roadmap

1. Accept a snapshot written by the KubePulse collect command as input,
   so the investigator runs on a real cluster export, still read-only.
2. Add case categories for probe failures and network policy faults, each
   with cases, expected evidence, and runbook sections.
3. Add a small web view that renders the evaluation scorecard and one
   diagnosis page per case.

## Tests

```bash
.venv/bin/python -m pytest -q
```

34 tests with the agent extra installed, 32 plus the graph module skipped
without it. They cover every case end to end, the approval flag on every
proposed action, the low confidence behaviour on the ambiguous case, the
evaluation score, citation targets, determinism, and a check that the
investigator core contains no way to run a command.
