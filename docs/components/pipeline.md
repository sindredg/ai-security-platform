# Repository and pipeline

The repository is the approval channel: a change reaches `main` only through a pull request. So its protection is a system control, not housekeeping.

| | |
| --- | --- |
| State | Built |
| Defined in | `.github/workflows/checks.yml`, `.github/dependabot.yml`, and repository settings |
| Decision | [0010](../decisions/0010-threat-model-and-security-checks-per-milestone.md) |

## Checks on every pull request

| Check | What it does |
| --- | --- |
| Terraform format and validate | `terraform fmt -check` and `terraform validate` on every root |
| Checkov | Terraform and Kubernetes manifest misconfigurations |
| Trivy | Terraform, Kubernetes manifest, and Dockerfile misconfigurations. For Terraform and the manifests, a second scanner beside Checkov |
| Secret scan | gitleaks over the whole history |
| ShellCheck | Every shell script under `worker/`, `platform/`, and `validation/`. They run as root on the VMs |
| Ruff | Lint and format check on all Python files under `worker/`, `platform/`, and `tool-service/`. The tool service adds bugbear, the security rules, and import order |
| Kubernetes manifests | kubeconform over every manifest under `platform/`, strict, against the cluster's Kubernetes release. Then every image line has to name a digest that is not the placeholder of zeros |
| Tool service tests | The line count against the limit of 300, then the tests, on the pinned Python image with every package installed by hash |
| Tool service image | hadolint on the Dockerfile, a build from the pinned base image, and a Trivy scan of the image that blocks on any finding with a fix. On `main`, the job pushes the image to the repository's package registry and writes its digest to the run summary |
| Dependency scan | Trivy over the converter's Python pins: reports, never blocks. Trivy over the tool service's pins: blocks |

The first six are required by the ruleset on `main`. The tool service tests, the image job, and the dependency scan run on every pull request and are not in the ruleset. The image job is the only job with write permission. It can write packages to this repository's registry, in a step that runs on `main` only. The pipeline holds no cloud credentials and runs no plan. The scanners and linters run from images pinned by digest, so no third-party action runs.

## Repository settings

Secret scanning with push protection is on. The ruleset `protect-main` refuses deletion and force pushes, and requires a pull request with the six checks.

## Limits

- **One person approves their own pull requests.**
- **Push protection is read as enabled, not tested with a pushed secret.**
- **The secret scan has false positives.** A `curl -u` with a command substitution was flagged once.
- **The dependency scan does not block for the converter's packages.** It blocks for the tool service's. The converter's packages follow llama.cpp's own pins, so an advisory in them has no fix here short of leaving upstream's list. On 2026-10-12, `trivy fs --scanners vuln` (0.75.0) on those pins listed 8 advisories, 5 of them high: 5 in `transformers` 4.57.6 and one each in `protobuf`, `setuptools`, and `torch`. The packages run once per model build, with no network. None of the eight is reachable in that build, and each is [accepted with its reason](../security/accepted-risks.md#advisories-in-the-converters-packages).
- **Dependabot cannot see every pin.** See the version table in the [index](README.md#versions).

## Official documentation

- [Push protection](https://docs.github.com/en/code-security/secret-scanning/introduction/about-push-protection)
- [Dependabot version updates](https://docs.github.com/en/code-security/dependabot/dependabot-version-updates/about-dependabot-version-updates)
