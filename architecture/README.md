# Architecture

The living truth about what `modern-di-litestar` does **now** — one file per
capability, updated by hand whenever a change ships. The *why* and *how it got
here* live in [`../planning/changes/`](../planning/changes/), and decisions
deliberately taken (including options rejected) in
[`../planning/decisions/`](../planning/decisions/); this directory is the
present.

These files carry **no frontmatter** — they are prose, dated by git.

## Capabilities

Capability files are added here as behavior is documented: a change that
introduces or alters a capability creates or edits its file in the same PR that
ships the code.

- [autowiring.md](autowiring.md) — how `ModernDIPlugin` registers
  `autowired_groups` providers as Litestar dependencies by name.

## Promotion rule

Shipping a change hand-edits the affected capability file(s) here to match the
new reality, in the same PR as the code. The change bundle stays in place under
[`../planning/changes/`](../planning/changes/) — no folder move.
