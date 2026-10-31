# 0055. Acceptance is each gate's result, with no numeric thresholds

Status: Accepted
Date: 2026-10-31

## Context

The architecture has listed acceptance thresholds for quality, recovery, and cost as an open decision, needed before the operational drills. No record decided it, and milestone 6's drills ran against the roadmap's gates: each names a behavior, and its result is recorded with the evidence behind it ([worklog](../worklogs/0007-operational-and-containment-drills.md)).

Numbers exist without a threshold. The scored cases count right and wrong verdicts ([evidence](../evidence/README.md)), the KV-cache clear after a timeout took 14 seconds, and each investigation's resource use and minutes are measured. Every one of them comes from a handful of runs on one model, one worker, and one target.

## Options

| Option | Trade-off |
| --- | --- |
| Each gate's pass or fail, with measured values recorded and not scored | Matches how the gates are written. A slower or less accurate result passes while the gate's behavior holds |
| Numeric thresholds per gate: verdict accuracy, recovery time, cost per job | A regression shows as a number crossing a line. The lines would be set from a few runs, and would pass or fail on noise |
| Thresholds from a baseline run, compared after each change | A real regression signal. Needs repeated runs per change, which the model's speed on CPU makes hours each |

## Decision

**A gate is accepted on its result: the behavior it names happened, or failed, with the evidence linked.** Verdict counts, recovery times, resource use, and job minutes are recorded in the evidence records and the worklogs, and no gate passes or fails on a number.

**A number becomes a criterion only where a gate names one.** The 60-minute JIT egress window, the job time limits, and the daily cap are limits the system enforces, not acceptance thresholds, and stay as they are.

## Trade-offs

- A change that makes verdicts worse or jobs slower passes, as long as each gate's behavior still holds. The records show the drift only to someone who compares them.
- Production use would need thresholds set from enough runs to tell a regression from noise. This lab does not have them ([lab against production](../security/lab-vs-production.md)).
- Exercises 2 and 3 are accepted the same way. A threshold for either is a new record.
