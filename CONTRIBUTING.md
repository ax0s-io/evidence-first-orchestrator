# Contributing

Contributions are accepted under the same MIT license under which this project
is distributed: inbound equals outbound. No Contributor License Agreement
(CLA) is required.

## Developer Certificate of Origin

Every commit must include a `Signed-off-by:` trailer. Create it with:

```bash
git commit -s
```

The sign-off certifies the
[Developer Certificate of Origin 1.1](https://developercertificate.org/): you
created the contribution, or have the right to submit work derived from a
properly licensed source; you provide it under the project's open-source
license; and you understand that the contribution and sign-off are recorded
publicly and may be retained indefinitely.

Do not contribute code you do not have the right to license. In particular, do
not paste another project's wrapper implementation into this repository. This
project specifies adapter interfaces and deliberately vendors no one else's
`codex-leg` or `grok-leg` implementation.

## Required validation

The authoritative gate is:

```bash
./tests/run-tests.sh
```

It must pass. The suite is deterministic, offline, and hermetic: it invokes no
vendor CLI, opens no socket, makes no model call, and spends no provider quota.
New behavior needs a test. Keep the suite offline and hermetic.

Match the surrounding code style. Runtime code targets Python 3.10+ and
POSIX-ish Bash. Do not add runtime dependencies; the project deliberately has
none.

## Review posture

Two maintainers review proposals on a best-effort basis. There is no guaranteed
response time, and a proposal may be declined for scope reasons. Submission
does not imply that the project will accept or merge a contribution.

Do not add badges, logos, or wordmarks that imply endorsement, certification,
partnership, or official listing by Anthropic, OpenAI, xAI, or any other
vendor.
