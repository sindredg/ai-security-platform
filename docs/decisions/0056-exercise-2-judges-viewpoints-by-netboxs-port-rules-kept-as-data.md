# 0056. Exercise 2 judges viewpoints by NetBox's port rules, kept as data

Status: Proposed
Date: 2026-11-01

## Context

Exercise 2 seeds a target network rule that lets an unintended viewpoint reach NetBox's port ([roadmap](../roadmap.md#7-exercise-2-excess-network-access)). Exercise 1's chain judges NetBox's permissions: collect, compare, policy, staging test, pull request, signed approval, delivery. A network rule breaks three of its assumptions.

The rules are Terraform in the targets repository, and only the operator's Terraform run changes them. The platform holds no cloud credential ([0013](0013-a-token-per-job-and-no-cloud-identity-yet.md)), so it cannot read the live rules from Azure or apply a change. No copy of the network exists to test a change on: the rehearsal copy shares the lab VM and its subnets with the live NetBox ([0044](0044-the-rehearsal-copy-is-a-second-netbox-on-the-lab-vm.md)).

Every target subnet ends in `deny-all-outbound` at priority 4096. A path from one subnet to NetBox's port needs an outbound allow on the source subnet and an inbound allow on NetBox's subnet. The seed is that pair, both named `allow-netbox-from-rehearsal` at 1120, so the staging subnet, the staging copy's, reaches the live NetBox's port.

## Options

| Question | Options | Chosen, and why |
| --- | --- | --- |
| Which address is the unintended viewpoint | A machine in the empty `unintended` subnet; the lab VM's staging interface, `10.50.1.4` | The staging interface. It routes already, and a new machine or interface does not fit the quota |
| Where the rules live | HCL in `main.tf`; a JSON file `main.tf` reads; the live rules from Azure | The JSON file. A diff of data is checkable by pattern, and Azure needs a cloud identity |
| How the job names a fix | New schema fields; the existing schema | The existing schema: one verdict per viewpoint, the rule's priority in the permission field |
| What tests the change | A copy of the network; the rules judged without the change | The rules judged, then connections after the apply. No copy exists |
| Who delivers | The delivery command; the operator's Terraform apply after the merge | The apply. The platform has no cloud credential |

## Decision

**The rules about NetBox's port that name a target subnet are data.** `infra/targets/netbox-rules.json` in the targets repository holds them per subnet, and `main.tf` merges them into each subnet's security group. The orchestrator's own rules stay in `main.tf`. A merge that changes the file needs an approval on its head, as the seed does ([0050](0050-a-guarded-change-merges-only-with-an-approval-on-its-head.md)).

**The contract gets a network part.** It names NetBox's address, port, and subnet, and viewpoints: an address in a target subnet, and whether a connection from it should reach the port (`open`) or not (`closed`).

**Two methods judge each viewpoint, as two methods judge each account ([0040](0040-a-jobs-evidence-is-collected-on-the-hosts-and-stored-per-job.md)).** The configured half reads the rules file at the main of the delivery mirror and judges by priority order and the deny-all baseline. The observed half connects from the lab VM, bound to the viewpoint's address. The job gets two more documents: `ev-0004`, the rules without their descriptions, and `ev-0005`, each connection's result.

**The answer uses the existing schema.** Each viewpoint gets a verdict under `viewpoint-NAME`, beside the accounts ([0051](0051-a-netbox-jobs-schema-names-each-account-of-the-job.md)). A fix for an excess viewpoint names the inbound rule on NetBox's subnet by its priority, in the field that holds a permission's ID.

**The policy allows a rule's removal only when it fixes that viewpoint and nothing else moves.** Both checks call the viewpoint excess. The priority names an inbound allow that lets the viewpoint in. Without it and its same-named outbound half, the viewpoint is within and every other viewpoint keeps its verdict. A fix changes permissions or rules, not both.

**A rule's fix has no staging test.** The bundle holds the rules judged without the change, says so, and is the only check before the pull request. The connections from both viewpoints after the apply are the test.

**The operator delivers it.** `edit_rules.py` applies the bundle on the operator's machine: only the removals it names, only to the file the job judged by SHA-256. The pull request merges with an approval. The operator plans and applies main, then the mirror fetches main and a new collection judges the result.

## Trade-offs

- The unintended viewpoint is the staging copy's subnet, not the `unintended` subnet, which stays empty. The contract names no viewpoint there, so a rule that opens it to NetBox's port is judged by nothing.
- The rules that stay in `main.tf` are outside the file and outside the configured half. A seed placed there is seen only by the connection.
- A rule with an address the collector cannot read, such as a service tag, makes the viewpoint's verdict unknown, so the job stops.
- The contract file is not guarded by the approval check. A pull request can change a viewpoint's expected reach, and the next collection judges against it.
- The field named for a permission carries a priority. The task says so; a reader of a raw answer has to know.
- The delivery command does not check the approval before the apply. The merge check does, and the operator applies main. Between the merge and the apply, the configured half judges rules that are not live yet.
- Not seen when this was written: a model's answer for a viewpoint, and an apply of a fix.
