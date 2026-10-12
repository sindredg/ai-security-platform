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
| Checkov | Terraform misconfigurations |
| Trivy | Terraform misconfigurations, a second opinion |
| Secret scan | gitleaks over the whole history |
| ShellCheck | Every shell script under `worker/` and `validation/`. They run as root on the VMs |
| Ruff | All Python files under `worker/`, with the default rules of the pinned release |
| Dependency scan | Trivy over the converter's Python pins. Reports, never blocks |

The first six are required by the ruleset on `main`. The dependency scan runs on every pull request and is not in the ruleset. The pipeline holds no cloud credentials and runs no plan. The scanners and linters run from images pinned by digest, so no third-party action runs.

## Repository settings

Secret scanning with push protection is on. The ruleset `protect-main` refuses deletion and force pushes, and requires a pull request with the six checks.

## Limits

- **One person approves their own pull requests.**
- **Push protection is read as enabled, not tested with a pushed secret.**
- **The secret scan has false positives.** A `curl -u` with a command substitution was flagged once.
- **The dependency scan does not block.** The converter's packages follow llama.cpp's own pins, so an advisory in them has no fix here short of leaving upstream's list. On 2026-10-12, `trivy fs --scanners vuln` (0.75.0) on those pins listed 8 advisories, 5 of them high: 5 in `transformers` 4.57.6 and one each in `protobuf`, `setuptools`, and `torch`. The packages run once per model build, with no network. None of the eight is reachable in that build, and each is [accepted with its reason](../security/accepted-risks.md#advisories-in-the-converters-packages).
- **Dependabot cannot see every pin.** See the version table in the [index](README.md#versions).

## Official documentation

- [Push protection](https://docs.github.com/en/code-security/secret-scanning/introduction/about-push-protection)
- [Dependabot version updates](https://docs.github.com/en/code-security/dependabot/dependabot-version-updates/about-dependabot-version-updates)
