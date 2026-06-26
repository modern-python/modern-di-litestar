# Autowiring

When `ModernDIPlugin` is constructed with `autowired_groups`, `on_app_init`
registers each group's providers as app-level Litestar dependencies, one
`Provide` per provider, keyed by the provider's **declared attribute name**.
Routes then declare those names directly as parameters, without a per-route
`dependencies={...}` mapping.

Names and providers come from `modern_di.Group.get_named_providers()`, which
walks the full MRO — so providers a group **inherits** from a base `Group`
are autowired under their declared names, not skipped.

The mapping is built by `_autowired_dependencies(groups, *, existing)` in
`modern_di_litestar/main.py`. It flags name collisions with a `UserWarning`
and overwrites (last write wins):

- **group-vs-group** — the same attribute name declared in two autowired
  groups;
- **group-vs-existing** — an attribute name that collides with a dependency
  already registered on the app (for example `di_container`).

Autowiring is the implicit counterpart to explicit `FromDI(provider)` wiring,
where each provider is named at the route's `dependencies={...}` call site.
