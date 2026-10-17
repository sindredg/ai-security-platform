# Repository and pipeline

The repository is the approval channel: a change reaches `main` only through a pull request. So its protection is a system control, not housekeeping.

| | |
| --- | --- |
| State | Built |
| Defined in | `.github/workflows/checks.yml`, `.github/workflows/signatures.yml`, `.github/allowed_signers`, `.github/dependabot.yml`, and repository settings |
| Decision | [0010](../decisions/0010-threat-model-and-security-checks-per-milestone.md), [0024](../decisions/0024-the-targets-in-their-own-repository-and-signed-commits.md) |

## Checks on every pull request

| Check | What it does |
| --- | --- |
| Terraform format and validate | `terraform fmt -check` and `terraform validate` on the bootstrap and platform roots. The target root is checked in the [targets repository](https://github.com/sindredg/ai-security-platform-test) |
| Checkov | Terraform and Kubernetes manifest misconfigurations |
| Trivy | Terraform, Kubernetes manifest, and Dockerfile misconfigurations. For Terraform and the manifests, a second scanner beside Checkov. For the manifests, `.github/trivy-data/ksv0125.yaml` names `ghcr.io` as the trusted registry, with its reason |
| Secret scan | gitleaks over the whole history |
| ShellCheck | Every shell script under `worker/`, `platform/`, `validation/`, and `.github/scripts/`. Most run as root on the VMs |
| Ruff | Lint and format check on all Python files under `worker/`, `platform/`, and `tool-service/`. The tool service adds bugbear, the security rules, and import order |
| Kubernetes manifests | kubeconform over every manifest under `platform/`, strict, against the cluster's Kubernetes release. Then every image line has to name a digest that is not the placeholder of zeros |
| Tool service tests | The line count against the limit of 300, then the tests, on the pinned Python image with every package installed by hash |
| Log copier tests | The unit tests of the audit copier and the journal puller under `platform/logs/`, on the pinned Python image. They use the standard library only, so nothing is installed |
| Tool service image | hadolint on the Dockerfile, a build from the pinned base image, and a Trivy scan of the image that blocks on any finding with a fix. On `main`, the job pushes the image to the repository's package registry and writes its digest to the run summary |
| Dependency scan | Trivy over the converter's Python pins: reports, never blocks. Trivy over the tool service's pins: blocks |
| Commit signatures | `git verify-commit` on every commit in the pull request, against `.github/allowed_signers`: the public half of the operator's signing key, nothing else. A commit signed by GitHub, by another key, or not at all fails. See [below](#the-signature-check) |

All but the dependency scan are required by the ruleset on `main`. The dependency scan runs on every pull request and does not block a merge. The image job is the only job with write permission. It can write packages to this repository's registry, in a step that runs on `main` only. The pipeline holds no cloud credentials and runs no plan. The scanners and linters run from images pinned by digest, so no third-party action runs.

## The signature check

A stolen GitHub token can make commits through the GraphQL API (`createCommitOnBranch`), and GitHub signs them. The ruleset's signature rule accepts any verified signature, so it lets those commits in and cannot tell them from the operator's. The check can: it accepts one key ([0024](../decisions/0024-the-targets-in-their-own-repository-and-signed-commits.md)).

It runs in its own workflow, on `pull_request_target`, not in `checks.yml`. A `pull_request` job runs the workflow as the pull request has it, so a pull request made with a stolen token could rewrite the check and pass it. With `pull_request_target`, the workflow, the script (`.github/scripts/check-signatures.sh`), and the allowed signers file come from the default branch. The pull request's commits are fetched by hash and verified as data. Nothing from the pull request is checked out or run, and the job can only read.

A pull request can still add a workflow of its own with a job named "Commit signatures". Both runs then come from GitHub Actions, so the source on the required check does not tell them apart. It does not have to: a failing run of the real job blocks the merge even when the other run passes, and even when that pass is the most recent run of the name ([worklog](../worklogs/0004-edge-network-and-monitoring.md#the-fail-side-on-github)).

The range is every commit reachable from the pull request's head and not from `main` as it is when the job runs. The squash commit GitHub makes at merge is outside it.

## Repository settings

Read from the GitHub API on 2026-10-17 at 07:10 UTC, after the changes for [0024](../decisions/0024-the-targets-in-their-own-repository-and-signed-commits.md):

- Secret scanning with push protection is on.
- The ruleset `protect-main`, on the default branch, refuses deletion and force pushes, requires signed commits, and requires a pull request with every check above except the dependency scan. Each required check names GitHub Actions as its source, so a status with the same name from anything else does not count. The only merge method it allows is squash. No one can bypass it.
- A second ruleset, on every branch, requires signed commits and nothing else. No one can bypass it.
- In the repository settings, squash is the only merge method. Merge commits and rebase merges are off. On `main`, the ruleset allows squash only as well.

The [repository settings runbook](../runbooks/repository-settings.md) sets these up and repeats the fail side.

## The targets repository

The [targets repository](https://github.com/sindredg/ai-security-platform-test) holds the target root ([0024](../decisions/0024-the-targets-in-their-own-repository-and-signed-commits.md)) and has a pipeline of its own, at the same pins: Terraform format and validate, Checkov, Trivy, the secret scan, ShellCheck on the signature script, and "Commit signatures", a copy of this repository's check with the same allowed signer. The two scanners fetch the shared module first, because the rules are arguments to it, and a step fails each job when the module is missing.

Its settings were set through the API with the runbook on 2026-10-17 and read back at 08:05 UTC: squash merges only, secret scanning with push protection, `protect-main` with the six checks above required, each from GitHub Actions, and a second ruleset that requires signed commits on every branch. Neither ruleset can be bypassed. The fail side was repeated there ([worklog](../worklogs/0004-edge-network-and-monitoring.md#the-targets-in-poland-central)).

## Limits

- **One person approves their own pull requests.**
- **Checkov does not judge the security group rules.** It does not resolve the rules the network module receives as a variable, so a rule that allows SSH from any source passes it. Trivy fails that rule ([#99](https://github.com/sindredg/ai-security-platform/issues/99), [worklog](../worklogs/0004-edge-network-and-monitoring.md#the-security-group-rules-in-the-scanners)). The live rules are compared with the configured ones by the [`Z` checks](../validation/containment.md#from-azures-side), after an apply.
- **Two copies of the signature check.** A change to the script or the allowed signers file has to be made in both repositories.
- **A change to the signature check takes effect only after it merges.** The pull request that changes it is judged by the version on `main`. The pull request that added it was not judged by it at all.
- **The fail side on GitHub was run from branches of this repository.** A pull request that edits `signatures.yml` itself was blocked by the default branch's copy. A pull request from a fork was not tried ([#95](https://github.com/sindredg/ai-security-platform/issues/95), [worklog](../worklogs/0004-edge-network-and-monitoring.md#the-fail-side-on-github)).
- **Every version update is made by hand.** Dependabot's commits are signed by GitHub, so its pull requests fail the signature check. The operator makes the same change in a pull request of their own.
- **Push protection is read as enabled, not tested with a pushed secret.**
- **The secret scan has false positives.** A `curl -u` with a command substitution was flagged once.
- **The dependency scan does not block for the converter's packages.** It blocks for the tool service's. The converter's packages follow llama.cpp's own pins, so an advisory in them has no fix here short of leaving upstream's list. On 2026-10-12, `trivy fs --scanners vuln` (0.75.0) on those pins listed 8 advisories, 5 of them high: 5 in `transformers` 4.57.6 and one each in `protobuf`, `setuptools`, and `torch`. The packages run once per model build, with no network. None of the eight is reachable in that build, and each is [accepted with its reason](../security/accepted-risks.md#advisories-in-the-converters-packages).
- **Dependabot cannot see every pin.** See the version table in the [index](README.md#versions).

## Official documentation

- [Push protection](https://docs.github.com/en/code-security/secret-scanning/introduction/about-push-protection)
- [Dependabot version updates](https://docs.github.com/en/code-security/dependabot/dependabot-version-updates/about-dependabot-version-updates)
