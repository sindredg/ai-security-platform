# 0024. The targets in their own repository, and signed commits from the operator's machine

Status: Accepted
Date: 2026-10-16

The broker's app was not made: [0045](0045-the-operator-publishes-a-checked-proposal.md) decides milestone 5's pull requests without one.

Extends [0002](0002-separate-platform-and-target-infrastructure.md) to the repository. 0002 separates the two sides at every layer the project controls, and the repository is a layer it did not name.

## Context

One repository holds both sides: the platform's controls (its network rules, checks, pipeline, and decisions) and `infra/targets/`, the target network. Milestone 4 adds NetBox, the seeded weaknesses, and the consumer contract. Milestone 5 gives a pull request broker a repository credential, so the platform can propose fixes (T12).

With one repository, that credential reaches the platform's own controls. A compromised agent could propose a change to the rules that contain it, and the operator is the only reviewer. Path rules do not help: with one owner, code owners change nothing, and a proposal is a pull request, which a rule on pushes does not judge.

Hiding the platform's configuration is not the goal. The repository is public, and the design assumes an attacker knows every rule. What matters is who can write.

Commit signing, read on 2026-10-16:

- The operator's commits are already signed. Global Git configuration has `gpg.format ssh`, `commit.gpgsign true`, and an SSH signing key. GitHub reports recent commits as verified: the operator's as `sindredg`, merges as `web-flow`.
- Nothing requires it. The `protect-main` ruleset has deletion, force push, pull request, and status check rules, and no signature rule.
- GitHub's [signature rule](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets) accepts any commit with a verified signature. It cannot name a key. GitHub [signs commits made in its web interface](https://docs.github.com/en/authentication/managing-commit-signature-verification/about-commit-signature-verification) with its own key, and verifies bot signatures on commits that GitHub Apps make through the API. So a stolen token can create commits that pass the rule, signed by GitHub.
- Unsigned commits on a pull request branch block a squash merge, and GitHub signs the squash commit. Rebase merges are not signed.
- Git is 2.43.0 on the workstation. SSH signing needs 2.34 or later.

## Options

Where the targets live.

| Option | Platform credential that writes to the platform's controls | Cost |
| --- | --- | --- |
| One repository | The broker's, from milestone 5 | Nothing |
| One repository with path rules | The same. Rules on pushes do not judge a pull request's content, and code owners mean nothing with one owner | Rules that look like a control |
| A second repository, same account | None. The broker's app is installed on the targets repository only | Two pipelines, and a pinned reference to the shared module |
| A second account or organization for the targets | None, and a separate owner | A second identity to protect, for one operator |

What "signed by the operator's machine" can mean on GitHub.

| Option | Commit made with a stolen token, through the API | Commit pushed from the platform | Cost |
| --- | --- | --- | --- |
| Signing on, nothing required | Accepted | Accepted | Nothing |
| The ruleset's signature rule | Accepted: GitHub signs it | Refused unless signed | One rule |
| The rule, plus a required check that every commit in a pull request is signed by the operator's key | Refused at the check. GitHub's signature is not the operator's | Refused | A small pipeline job and an allowed signers file |
| A hardware security key, touched for each commit | Refused | Refused | Proves the operator was present. Every commit waits for a touch, including the ones made by the coding agent on the workstation |

## Decision

**A second public repository, `sindredg/ai-security-targets`, holds the target side.** It gets:

- `infra/targets/`, moved there when [0020](0020-an-edge-vm-for-the-way-out-and-the-mesh.md) moves the target network to Poland Central.
- NetBox, the lab VM, the seeded weaknesses, and the consumer contract, from milestone 4.
- Its own pipeline: Terraform format and validate, Checkov, Trivy, a secret scan, and the signature check.
- Its own ruleset, the same as `protect-main`, with the signature rule.

The platform repository keeps everything else: the bootstrap root, which still creates both sides' identities, state, and policy; the platform root; the shared network module; the checks; the documentation.

- The target root uses the shared module as a Git source pinned to a commit of the platform repository. A change to the module reaches the targets only when that pin moves, which narrows T34.
- The platform reads the targets repository without a credential, because it is public. The collectors compare target evidence with it (T23).
- The broker's GitHub App is installed on the targets repository only. The platform repository has no app installation and no deploy key. The platform holds no credential that writes to it.

**Commits to the platform repository are signed by the operator's machine.**

- A second ruleset, on every branch, with the signature rule. An unsigned commit cannot be pushed anywhere in the repository.
- A required check, "Commit signatures", verifies each commit in a pull request with `git verify-commit` against `.github/allowed_signers`. That file holds the public half of the operator's signing key and nothing else. A commit signed by GitHub, or by any other key, fails it. The squash commit GitHub makes at merge is outside the pull request's range and is not checked.
- No exception, Dependabot included. Its commits are signed by GitHub, so its pull requests fail the check and cannot merge. Dependabot stays on as a source of proposals: the operator makes the same version change from the workstation, in a pull request of its own, and closes Dependabot's.
- Merges are squash only. Rebase merges are turned off, because GitHub does not sign them, and merge commits too, so that one method is in use.
- The signing key is the SSH key already configured, protected by a passphrase and loaded into the agent for the working session. The coding agent signs with it, so a signature shows "made on the workstation", not "approved by a person".

The targets repository gets the same rule and check. Its allowed signers are the operator's key, plus the broker's app from milestone 5, whose commits through the API carry GitHub's bot signature. How the check tells the broker's commits apart is a milestone 5 decision.

**Checks**

- The rulesets are read from the GitHub API and recorded, as the [pipeline page](../components/pipeline.md#repository-settings) does for `protect-main` today.
- The fail side, once: a pull request with one commit made in the web interface fails "Commit signatures", and a push of an unsigned commit is refused.

## Trade-offs

- **A takeover of the operator's GitHub account defeats both.** The attacker can change the check, the allowed signers file, and the rulesets, and merge. T15 stays accepted.
- **A compromised workstation signs whatever it likes.** The key is there. That was true of every control in the repository before this record (T30).
- **Two repositories to keep in step.** Two pipelines, two rulesets, and a pin to move when the module changes. The required checks of each are listed separately.
- **History is not moved.** The commits that built `infra/targets/` stay in the platform repository's history. The new repository starts from a copy.
- **Every version update is made by hand.** Dependabot finds them, and the operator redoes each one. A busy week of updates is a busy week of small pull requests. In return, no key but the operator's ever passes the check.
- **The signature proves the machine, not the person.** A hardware key would prove presence, at the cost of a touch for every commit the coding agent makes. Not chosen.
- **The containment rules stay on the platform side.** The worker-side denies are in the platform root, and the policy that refuses public addresses is in the bootstrap root. Moving the target root does not move them, which is what 0002 requires.
