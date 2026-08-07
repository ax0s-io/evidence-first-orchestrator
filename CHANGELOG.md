# Changelog

All notable changes to this project are documented in this file. The format is
based on Keep a Changelog, and releases follow Semantic Versioning.

## 0.1.0 - 2026-08-07

### Added

- A launcher that creates a per-run job directory and records briefs,
  contracts, commands, attempt streams, worker artifacts, normalized results,
  validation errors, metrics, and run metadata as inspectable evidence.
- Reader and writer worker lanes, with three independent mechanical caps for
  concurrent workers, concurrent writers, and cumulative node starts.
- An out-of-band, file-locked slot controller that enforces all three caps
  across vendors and records worker lifecycle events.
- Deterministic result validation and downgrade-only normalization that
  preserves the raw model claim while preventing unsupported success from
  passing the launcher gate.
- A proof-gated cross-model availability fallback that runs only after on-disk
  slot and tool-use evidence establishes that the first attempt had no worker
  starts or potentially mutating tool use.
- Interface contracts and slot-controlled entry points for user-supplied
  `codex-leg` and `grok-leg` adapters.
- Preflight and install scripts for local, dependency-free setup.
- A deterministic, offline, hermetic test suite that uses no vendor CLI,
  socket, model call, or provider quota.
