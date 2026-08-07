# Attribution

> **Approved 2026-08-06.** Both named authors approved this attribution and the
> MIT license. Chris Blaschke approved in person while with Aaron Dyson; Aaron
> recorded that approval in the publication checklist.

## Authors

Developed by **Aaron Dyson** and **Chris Blaschke** at **ax0s**.

- **Aaron Dyson** — orchestration design, launcher and validation
  implementation, extraction, and open-source preparation.
- **Chris Blaschke** — provider-adapter and routing design; author of the
  upstream `codex-leg` / `grok-leg` wrapper lineage that this project treats as
  an external prerequisite.

## Relationship to upstream work

This repository is an extraction of an internal orchestration skill. The
hardened provider wrappers (`codex-leg`, `grok-leg`) and the broader routing
doctrine that inspired it live in a separate, unlicensed private codebase and
are **not included here**. This project defines the *interface* it expects from
those adapters (see [docs/adapters.md](docs/adapters.md)) and fails closed when
they are absent. No upstream implementation is redistributed.

## Independence

This is an **independent community integration**.

It is **not affiliated with, sponsored by, endorsed by, or certified by**
Prime Intellect, Anthropic, OpenAI, or xAI.

"Prime Intellect" and "Prime Agent" are marks of Prime Intellect. "Claude",
"Claude Code", "Opus", and "Fable" are marks of Anthropic. "Codex" is a mark of
OpenAI. "Grok" is a mark of xAI. All other trademarks are the property of their
respective owners. These names are used solely to describe interoperability
with those products, and their use here implies no relationship of any kind.

Each provider's terms of service govern your use of their CLI. This project
does not grant, extend, resell, or circumvent any provider entitlement.

## License

The project is licensed under the [MIT License](LICENSE), with Aaron Dyson and
Chris Blaschke as copyright holders. Both authors approved the license grant
and attribution on 2026-08-06.
