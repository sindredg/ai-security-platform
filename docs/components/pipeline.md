# Repository and pipeline

The repository is the approval channel: a change reaches `main` only through a pull request. So its protection is a system control, not housekeeping.

| | |
| --- | --- |
| State | Built. Verified on GitHub on 2026-10-17: the required signature check blocked a pull request with a commit GitHub signed ([worklog](../worklogs/0004-edge-network-and-monitoring.md#the-fail-side-on-github)). Settings read on 2026-10-26 ([repository settings](#repository-settings)) |
| Defined in | `.github/workflows/checks.yml`, `.github/workflows/signatures.yml`, `.github/allowed_signers`, `.github/dependabot.yml`, and repository settings |
| Decision | [0010](../decisions/0010-threat-model-and-security-checks-per-milestone.md), [0024](../decisions/0024-the-targets-in-their-own-repository-and-signed-commits.md) |

## Checks on every pull request

| Check | What it does |
| --- | --- |
| Terraform format and validate | `terraform fmt -check` and `terraform validate` on the bootstrap and platform roots, then `terraform test` on the network module against a mocked provider: the module refuses an inbound Allow rule from any source, `Internet`, `0.0.0.0/0`, or `::/0` ([#99](https://github.com/sindredg/ai-security-platform/issues/99)). The target root is checked in the [targets repository](https://github.com/sindredg/ai-security-platform-test) |
| Checkov | Terraform and Kubernetes manifest misconfigurations |
| Trivy | Terraform, Kubernetes manifest, and Dockerfile misconfigurations. For Terraform and the manifests, a second scanner beside Checkov. For the manifests, `.github/trivy-data/ksv0125.yaml` names `ghcr.io` and `quay.io` as the trusted registries, with their reasons, and `platform/argo/.trivyignore.yml` accepts two findings on the Argo controller's Role, limited to its two files, each with its reason. For Terraform, `AZU-0051` is ignored on the orchestrator's security group only, with its reason in the network module ([worklog](../worklogs/0004-edge-network-and-monitoring.md#the-suppression)) |
| Secret scan | gitleaks over the whole history, with the runner's `git`. gitleaks runs from its release archive, checked against a pinned SHA-256 ([#155](https://github.com/sindredg/ai-security-platform/issues/155)). When `git` fails, gitleaks reports no leaks and exits 0, so the step also fails when gitleaks logs an error or scans no commits ([worklog](../worklogs/0003-toolchain-integration.md#fix-the-secret-scan-without-the-gitleaks-image)) |
| ShellCheck | Every shell script under `worker/`, `platform/`, `edge/`, `validation/`, `collectors/`, and `.github/scripts/`, found by a `.sh` name or a first line that starts a shell ([#118](https://github.com/sindredg/ai-security-platform/issues/118)), and each VM's first-boot script, rendered out of its cloud-init template by `.github/scripts/render-first-boot.sh` ([#101](https://github.com/sindredg/ai-security-platform/issues/101)). Most run as root on the VMs |
| Squid configuration | Squid from the Ubuntu archive, the release the edge runs, parses the configuration the edge template writes, rendered with placeholder addresses by `.github/scripts/render-cloud-init-file.sh`, once with the fetch window closed and once open, with `edge/fetch-hosts` in place. A warning fails the job too: two overlapping names in the host list only warn ([#104](https://github.com/sindredg/ai-security-platform/issues/104)) |
| Ruff | Lint and format check on all Python files under `worker/`, `platform/`, `tool-service/`, `collectors/`, and `validation/`. The tool service and the collectors add bugbear, the security rules, and import order, because they read hostile input |
| Kubernetes manifests | kubeconform over every manifest under `platform/`, strict, against the cluster's Kubernetes release. Then every image line has to name a digest that is not the placeholder of zeros |
| Tool service tests | The line count against the limit of 300, then the tests, on the pinned Python image with every package installed by hash |
| Log copier tests | The unit tests of the audit copier and the journal puller under `platform/logs/`, on the runner's `python3`: Ubuntu 26.04's, the release the orchestrator runs them with. The step fails when it is not the release `HOST_PYTHON` names. `-S` leaves Ubuntu's own packages off the path, so the tests have the standard library only ([#168](https://github.com/sindredg/ai-security-platform/issues/168)) |
| Collector tests | The unit tests of NetBox's collector under `collectors/netbox/`, on the runner's `python3`, as for the log copiers: the orchestrator and the lab VM run the collector with Ubuntu's. One test runs the collector's own opener against a local server, to show that it follows no redirect and ignores the proxy settings |
| Dispatch tests | The unit tests of the job runner and the job program under `worker/agent-runtime/job/`, with the copies of the fixture and the model comparison's `measure.py` against a stub model server, on the runner's `python3`, as for the log copiers. Then the dispatch step's under `platform/dispatch/`, on the pinned Python image, which the dispatch image is built from. They run the real job runner and job program behind a fake `ssh`. Both with a fake Goose and stubs for registration and the model server. Standard library only |
| Evidence pages | The tests under `validation/evidence/`, then `render.py --check`: each page in `docs/evidence/` matches its record, no record holds anything not to publish, and the pages keep the page rules. Then `render.py --rules` holds the README, the architecture, and the roadmap to the same rules |
| Tool service image | hadolint on the Dockerfile, a build from the pinned base image, and a Trivy scan of the image that blocks on any finding with a fix. On `main`, the job pushes the image to the repository's package registry and writes its digest to the run summary |
| Dispatch image | The same for `platform/dispatch/`, from the same base image, plus a check that `ssh` starts as the image's user, and one that the comparison step's program runs in it |
| Tool service dependency scan | Trivy over the tool service's pins, the runtime and the development lists apart. Blocks on any finding, with a fix or without. The image scan covers the runtime packages only, and only findings with a fix ([#167](https://github.com/sindredg/ai-security-platform/issues/167)) |
| Converter dependency scan | Trivy over the converter's Python pins. Reports, never blocks |
| Commit signatures | `git verify-commit` on every commit in the pull request, against `.github/allowed_signers`: the public half of the operator's signing key, nothing else. A commit signed by GitHub, by another key, or not at all fails. See [below](#the-signature-check) |

All but the converter dependency scan are required by the ruleset on `main`. The converter dependency scan runs on every pull request and does not block a merge ([advisories](../security/accepted-risks.md#advisories-in-the-converters-packages)).

The two image jobs are the only jobs with write permission. Each can write its package to this repository's registry, in a step that runs on `main` only.

The pipeline holds no cloud credentials and runs no plan. The scanners and linters run from images pinned by digest, except Terraform and gitleaks, which run from release archives checked against a pinned SHA-256. No third-party action runs.

## The signature check

A stolen GitHub token can make commits through the GraphQL API (`createCommitOnBranch`), and GitHub signs them. The ruleset's signature rule accepts any verified signature, so it lets those commits in and cannot tell them from the operator's. The check can: it accepts one key ([0024](../decisions/0024-the-targets-in-their-own-repository-and-signed-commits.md)).

It runs in its own workflow, on `pull_request_target`, not in `checks.yml`. A `pull_request` job runs the workflow as the pull request has it, so a pull request made with a stolen token could rewrite the check and pass it. With `pull_request_target`, the workflow, the script (`.github/scripts/check-signatures.sh`), and the allowed signers file come from the default branch. The pull request's commits are fetched by hash and verified as data. Nothing from the pull request is checked out or run, and the job can only read.

A pull request can still add a workflow of its own with a job named "Commit signatures". Both runs then come from GitHub Actions, so the source on the required check does not tell them apart. It does not have to: a failing run of the real job blocks the merge even when the other run passes, and even when that pass is the most recent run of the name ([worklog](../worklogs/0004-edge-network-and-monitoring.md#the-fail-side-on-github)).

The range is every commit reachable from the pull request's head and not from `main` as it is when the job runs. The squash commit GitHub makes at merge is outside it.

## Repository settings

Read from the GitHub API on 2026-10-17 at 07:10 UTC, after the changes for [0024](../decisions/0024-the-targets-in-their-own-repository-and-signed-commits.md):

- Secret scanning with push protection is on.
- The ruleset `protect-main`, on the default branch, refuses deletion and force pushes, requires signed commits, and requires a pull request with every check above except the converter dependency scan. Each required check names GitHub Actions as its source, so a status with the same name from anything else does not count. The only merge method it allows is squash. No one can bypass it.
- A second ruleset, on every branch, requires signed commits and nothing else. No one can bypass it.
- In the repository settings, squash is the only merge method. Merge commits and rebase merges are off. On `main`, the ruleset allows squash only as well.

Read again on 2026-10-18 at 12:52 UTC, after "Squid configuration" was made required: the same, with that check in the list, twelve checks, each from GitHub Actions.

Read again on 2026-10-20 at 15:00 UTC, after "Dispatch tests" and "Dispatch image" were made required: fourteen checks, each from GitHub Actions, and every other rule of `protect-main` unchanged. Configured, not tested: no pull request has been seen blocked by either of the two.

Read again on 2026-10-23 at 19:26 UTC, after "Tool service dependency scan" was made required ([#167](https://github.com/sindredg/ai-security-platform/issues/167)): fifteen checks, each from GitHub Actions, and every other rule of `protect-main` unchanged. The read-back equals the ruleset that was written. Tested the same day: a pull request with a known-vulnerable development pin was blocked by that check alone, and was clean again once the pin was removed ([worklog](../worklogs/0003-toolchain-integration.md#fix-a-required-tool-service-scan-and-the-host-code-on-the-hosts-python)).

Read again on 2026-10-25 at 07:46 UTC, after "Collector tests" was made required: sixteen checks, each from GitHub Actions, and every other rule of `protect-main` unchanged. Configured, not tested: no pull request has been seen blocked by it.

Read again on 2026-10-26 at 17:10 UTC, after "Evidence pages" was made required: seventeen checks, each from GitHub Actions, and every other rule of `protect-main` unchanged. Configured, not tested: no pull request has been seen blocked by it.

The [repository settings runbook](../runbooks/repository-settings.md) sets these up and repeats the fail side.

## The targets repository

The [targets repository](https://github.com/sindredg/ai-security-platform-test) holds the target root ([0024](../decisions/0024-the-targets-in-their-own-repository-and-signed-commits.md)) and has a pipeline of its own, at the same pins: Terraform format and validate, Checkov, Trivy, the secret scan, ShellCheck on the signature script and on the scripts the target VMs run as root, Quadlet's own dry run on NetBox's units, Ruff and a JSON parse on NetBox's Python and JSON files, and "Commit signatures", a copy of this repository's check with the same allowed signer. The two scanners fetch the shared module first, because the rules are arguments to it, and a step fails each job when the module is missing.

Its settings were set through the API with the runbook on 2026-10-17 and read back at 08:05 UTC: squash merges only, secret scanning with push protection, `protect-main` with six checks required, each from GitHub Actions (all of the above except Quadlet's dry run and Ruff, which came later with NetBox), and a second ruleset that requires signed commits on every branch. Neither ruleset can be bypassed. The fail side was repeated there ([worklog](../worklogs/0004-edge-network-and-monitoring.md#the-targets-in-poland-central)).

Read again on 2026-10-25 at 07:42 UTC, after "Quadlet units" and "Ruff" were made required: eight checks, each from GitHub Actions, and every other rule of `protect-main` unchanged. Configured, not tested: no pull request has been seen blocked by either of the two.

## Limits

- **One person approves their own pull requests.**
- **Checkov does not judge the security group rules.** It does not resolve the rules the network module receives as a variable, so a rule that allows SSH from any source passes it. Trivy fails that rule ([#99](https://github.com/sindredg/ai-security-platform/issues/99), [worklog](../worklogs/0004-edge-network-and-monitoring.md#the-security-group-rules-in-the-scanners)), and the module refuses it at plan, which its test shows on every pull request. The target root gets the refusal through its module pin, moved to `2114890` in [targets PR 6](https://github.com/sindredg/ai-security-platform-test/pull/6), with a plan of no changes. Other rule content, such as a port opened wider than needed, has only Trivy. The live rules are compared with the configured ones by the [`Z` checks](../validation/containment.md#from-azures-side), after an apply.
- **The Squid job parses with the runner's Squid.** The edge installs Squid unpinned at first boot and updates it daily, so the two match only while both are current.
- **Two copies of the signature check.** A change to the script or the allowed signers file has to be made in both repositories.
- **A change to the signature check takes effect only after it merges.** The pull request that changes it is judged by the version on `main`. The pull request that added it was not judged by it at all.
- **The fail side on GitHub was run from branches of this repository.** A pull request that edits `signatures.yml` itself was blocked by the default branch's copy. A pull request from a fork was not tried ([#95](https://github.com/sindredg/ai-security-platform/issues/95), [worklog](../worklogs/0004-edge-network-and-monitoring.md#the-fail-side-on-github)).
- **Every version update is made by hand.** Dependabot's commits are signed by GitHub, so its pull requests fail the signature check. The operator makes the same change in a pull request of their own.
- **Push protection is read as enabled, not tested with a pushed secret.**
- **The secret scan has false positives.** A `curl -u` with a command substitution was flagged once.
- **The converter dependency scan does not block.** The tool service's scan has a job of its own, which does. The converter's packages follow llama.cpp's own pins, so an advisory in them has no fix here short of leaving upstream's list. On 2026-10-12, `trivy fs --scanners vuln` (0.75.0) on those pins listed 8 advisories, 5 of them high: 5 in `transformers` 4.57.6 and one each in `protobuf`, `setuptools`, and `torch`. The packages run once per model build, with no network. None of the eight is reachable in that build, and each is [accepted with its reason](../security/accepted-risks.md#advisories-in-the-converters-packages).
- **Dependabot cannot see every pin.** See the version table in the [index](README.md#versions).

## Official documentation

- [Push protection](https://docs.github.com/en/code-security/secret-scanning/introduction/about-push-protection)
- [Dependabot version updates](https://docs.github.com/en/code-security/dependabot/dependabot-version-updates/about-dependabot-version-updates)
