# 0045. The platform prepares a checked proposal, and the operator's machine publishes it

Status: Accepted
Date: 2026-10-26

## Context

[0024](0024-the-targets-in-their-own-repository-and-signed-commits.md) planned a pull request broker for milestone 5: a GitHub App installed on the targets repository only, whose key would live in a `change` namespace. It left two questions to this milestone: the app's permissions (T12), and how the signature check would tell the app's commits from the operator's, since GitHub signs commits an app makes through the API. A third question is what a proposal may carry into a public page (A5).

What is fixed already:

- **The orchestrator reaches GitHub only during a fetch window,** through Squid, for the hosts on the window's list ([0020](0020-an-edge-vm-for-the-way-out-and-the-mesh.md)). Pods reach neither GitHub nor NetBox ([0040](0040-a-jobs-evidence-is-collected-on-the-hosts-and-stored-per-job.md)).
- **The targets repository requires the operator's signature on every commit,** checked against an allowed signers file that holds one key.
- **A proposal's text comes from the model,** which read target evidence and may have followed instructions in it (A1).

## Options

**Who opens the pull request**

| Option | Credential on the platform | What it costs |
| --- | --- | --- |
| A GitHub App with write on the targets repository, its key on the orchestrator | One that writes to the repository a delivery reads | The signature check must accept GitHub's signature for the app. The orchestrator needs the API host |
| A deploy key on the orchestrator that pushes a branch | One that writes to the repository | The signature check must accept that key too |
| The platform prepares the change, and the operator's machine commits and opens it | None | One more step on the operator's machine for each fix |

**What the pull request carries**

| Option | What it gives | What it costs |
| --- | --- | --- |
| The model's text, checked by a filter | The agent's reasoning in the review | A filter cannot tell evidence from an instruction or a secret in free text |
| Checked fields only | Nothing in the page that the model wrote | The reasoning stays in the job's record, not the pull request |

## Decision

**No GitHub App, and no repository credential on the platform.** The orchestrator writes a bundle for each allowed and rehearsed proposal, and the operator's machine applies its change to the seed, commits it with the operator's signing key as for every pull request, pushes a branch, and opens the pull request. The targets repository's allowed signers stay the operator's key alone.

**The pull request carries checked fields only:** the job, the case, the account, the permission's name and ID, the evidence references, the checks' and the model's verdicts, the policy's decision, the rehearsal's verdicts, and links to the records. It holds no text the model wrote.

**The change to the seed is mechanical.** A script on the operator's machine removes the named users from each named permission's list in the seed, and fails unless those lists are the only difference.

[0024](0024-the-targets-in-their-own-repository-and-signed-commits.md)'s broker app, its key in a `change` namespace, and its place in the allowed signers are not made.

## Trade-offs

- **The operator's machine publishes every fix.** A signature there means "made on the workstation", as [0024](0024-the-targets-in-their-own-repository-and-signed-commits.md) says, not "approved". Approval is a separate act ([0046](0046-a-signed-tag-approves-and-delivery-checks-before-the-merge.md)).
- **Nothing on the platform can open a pull request.** That removes T12's credential, and it removes the automation the broker was for.
- **A reviewer sees fields, not reasoning.** The model's answer stays in the job's record, which the evidence pages keep.
- **Not seen when this was written:** a bundle from a live job, and a pull request made from one.
