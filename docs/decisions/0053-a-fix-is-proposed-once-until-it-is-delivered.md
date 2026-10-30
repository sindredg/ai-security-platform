# 0053. A fix is proposed once until it is delivered

Status: Proposed
Date: 2026-10-30

## Context

Two jobs on one case can find the same excess: the same account holding the same permission. Each matched job can be proposed, and each allowed and rehearsed proposal gets a pull request in the targets repository from the operator's machine ([0045](0045-the-operator-publishes-a-checked-proposal.md)). Until milestone 6 the propose command refused only a job that was proposed already, so the second job's bundle would have given a second pull request for one finding.

The platform holds no repository credential ([0045](0045-the-operator-publishes-a-checked-proposal.md)), so the orchestrator cannot read the targets repository's pull requests. It does hold every bundle it wrote and every delivery's result ([0046](0046-a-signed-tag-approves-and-delivery-checks-before-the-merge.md)).

## Options

| Option | Stops the duplicate at | Trade-off |
| --- | --- | --- |
| The propose command refuses a fix an earlier undelivered bundle holds | The orchestrator, before the staging test | Local state only; a bundle removed by hand lifts the rule |
| The operator's machine reads the open pull requests before publishing | The pull request | Needs the operator's GitHub session; catches state the orchestrator lost |
| A branch per finding, so the push of a second one fails | The push | The branch names the job today, and GitHub refuses nothing by content |
| Both of the first two | Both places | Two checks to keep in step |

## Decision

**The propose command refuses a proposal that removes an account from a permission an earlier allowed and rehearsed bundle removes it from too, while no delivery of that bundle passed.** The match is on the account name and the permission's NetBox ID. Nothing is written for the refused job, so it can be proposed once the earlier fix is delivered, or once the earlier bundle is removed.

**The operator's machine reads the open pull requests before it opens one.** `open_fixes.py` takes the targets repository's open pull requests as the GitHub API lists them, and the bundle, and refuses when a body's change row names an account and permission ID of the bundle's changes. It fetches nothing itself.

**A failed delivery keeps the rule.** Only a delivery result with `passed` lifts it: a failed one leaves the pull request open and the finding in place.

## Trade-offs

- A bundle removed by hand, or an orchestrator rebuilt without its state, lifts the orchestrator's rule. The operator's read of the open pull requests is the second check for that case.
- The match is on the live NetBox's permission ID. A permission deleted and made again gets a new ID, and the same name passes as a new fix.
- The rows in a pull request's body are read by pattern. A body written in another shape is not matched. The branch name is not used: it names the job, not the finding.
- Not seen when this was written: a second job on a seed with a fix to propose. The drill uses a fixture bundle and the operator's proposals ([worklog](../worklogs/0007-operational-and-containment-drills.md#slice-5-the-same-finding-twice)).
