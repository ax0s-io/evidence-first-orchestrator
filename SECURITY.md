# Security policy

> This policy accompanied the August 2026 release. See the
> [historical project status](README.md); current response capacity has not
> been verified. Keep vulnerability reports private using the contacts below.

## Reporting a vulnerability

Report suspected exploitable vulnerabilities privately by email to
**chris@ax0s.io**. If the primary address is unavailable, use
**aaron@ax0s.io**. Do not open a public issue for anything exploitable.

Include the affected version, impact, reproduction steps, and any relevant
evidence. Do not include provider credentials or other secrets. We will
acknowledge a report within seven days on a best-effort basis.

This is a small, volunteer-scale project maintained by two people. There is no
SLA, no guaranteed response or remediation timeline, and no bug bounty.

## Supported versions

Only the latest release is supported. Version 0.1.0 is the first release. While
the project is pre-1.0, security fixes are not backported to older versions.

| Version | Supported |
| --- | --- |
| Latest release | Yes, best effort |
| Earlier releases | No |

## Scope

The following code in this repository is in scope:

- the launcher and its deterministic result-validation pipeline;
- the out-of-band slot controller;
- the repository's `efo-codex-leg` and `efo-grok-leg` adapter layers;
- the install script and preflight checks; and
- evidence handling, fallback safety checks, and process supervision performed
  by those components.

The following are out of scope:

- the vendor CLIs themselves;
- the external `codex-leg` and `grok-leg` implementations supplied by the user;
- model behavior or the correctness of model output; and
- provider accounts, authentication, entitlements, billing, or account policy.

Report a vulnerability in a vendor CLI to that vendor, not to this project. A
problem in a user-supplied external adapter belongs with its supplier unless
the issue is how this repository validates or invokes that interface.

## Operator responsibility

Read the full threat model in [docs/security.md](docs/security.md). The
orchestrator executes tool calls produced by an untrusted model. Briefs,
repository content, worker output, and other model-visible material are data,
not instructions that expand the operator's authorization.

The Grok worker path can use non-interactive approval under its declared
sandbox, profile, and working-directory restrictions. That means allowed tools
may run without asking. Its deny list is not a general security boundary.
The user-supplied adapter and vendor CLI must enforce the actual sandbox and
profile. Enabling this path is the operator's deliberate choice, and the
operator must accept the risk for the selected worktree and provider plan.
