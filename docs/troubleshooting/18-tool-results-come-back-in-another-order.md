# 18. Tool results come back in another order, and the model reads them by position

Date: 2026-10-25
Milestone: 4, NetBox target and exercise 1 investigation

## Symptom

The first NetBox job with the comparison, `nb-10251751-a`, stopped with `inventory-reader: the model says missing, the checks say excess`. The model asked for `ev-0001`, `ev-0002`, and `ev-0003` in one turn. Its answer described the documents under the wrong references:

```text
**ev-0001 (Contract):**
- **inventory-reader:**
  - Denies: /api/dcim/sites/, /api/tenancy/tenants/, /api/users/permissions/, POST /api/dcim/devices/
  - Reads: All 7 devices (a-fw-01, a-sw-01, a-sw-02, b-fw-01, b-sw-01, c-fw-01, c-sw-01) and all 7 IP addresses
```

Seven devices is what the account's token returned, which is in `ev-0003`. The contract, `ev-0001`, lists three. The answer then took the contract's three devices for what the token returned, and called the account `missing`.

## Cause

Confirmed from the transcripts and the model server's template.

- **The results arrive in the order the tool service answers them.** In `nb-10251751-a` they came back as `ev-0003`, `ev-0002`, `ev-0001`. Two more jobs that asked for all three in one turn got `ev-0003`, `ev-0001`, `ev-0002`, and `ev-0002`, `ev-0003`, `ev-0001`. Each time the order was that of the tool service's audit lines for the three calls. Goose's source was not read for this.
- **Nothing the model reads ties a result to its call.** The chat template the model server applies, read from its `/props` endpoint on 2026-10-25, writes a tool result as `<tool_response>`, the content, and `</tool_response>`. It carries no call ID and no tool name.
- **A document names itself near its end.** The tool service returns each document as JSON with sorted keys ([`evidence.py`](../../tool-service/aisec_tools/tools/evidence.py)), so `reference` comes after `accounts`, the long part.

So the model read the results in the order it asked for them. In each of the three answers, the first result's content is described under `ev-0001`.

## Fix

One line in the NetBox task, [`collectors/netbox/task.txt`](../../collectors/netbox/task.txt):

```text
Ask for one document at a time, and read it before you ask for the next.
```

A line that asked the model to tell the documents apart by their `reference` field was tried first, in two jobs. Both still asked for all three at once, and both answers still read them by position. One of them noticed, `the evidence returned shows different reference fields than the arguments I passed`, and kept the wrong mapping.

The other fix is in the tool service: `reference` first in each document it returns. That needs a new image and a deploy, and was not tried.

## Verification

Two jobs with the line, `nb-10251922-a1` and `nb-10251922-a2`, asked for one document per turn, and each result came right after its request. Both answers gave `inventory-reader` `excess` and the control `within`, the checks' verdicts. `nb-10251922-a2` ended in a match, and its workflow `Succeeded`. `nb-10251922-a1` ended its answer with `**inventory-reader excess ev-0003**` instead of a `Verdict:` line, and the comparison stopped on lines it could not read ([worklog](../worklogs/0005-netbox-target-and-exercise-1.md#the-comparison)). Two jobs show that the order holds with the line. They do not show how often the verdict is right.
