# Security policy

This is a lab: one operator, synthetic data, and no service for anyone else. A weakness still matters when it shows that a control the documentation claims does not hold.

## Report a vulnerability

Use private vulnerability reporting: **Security**, then **Report a vulnerability**, on this repository. Do not open a public issue for something that could be used against the running platform before it is fixed.

A useful report names the file and line, or the command and its output, and the claim in the documentation that it breaks.

## Scope

In scope:

- The code and configuration in this repository and in the [targets repository](https://github.com/sindredg/ai-security-platform-test).
- A claim in the documentation that the code or the [checks](docs/validation/README.md) do not support.

Out of scope:

- The weaknesses seeded into the targets for the exercises. They are there on purpose.
- Azure, GitHub, and the mesh VPN provider themselves, and the operator's workstation ([threat model scope](docs/security/threat-model.md#scope-and-method)).

Risks carried on purpose are listed in [accepted risks](docs/security/accepted-risks.md). A report that one of them is exploitable in a way the page does not describe is in scope.

## What happens next

One person reads the reports, and no response time is promised. A confirmed weakness is fixed in a pull request before anything about it is made public.
