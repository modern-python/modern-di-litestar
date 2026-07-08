---
summary: Replace the id()-keyed reverse lookup in on_app_init with a directly-testable _autowired_dependencies module consuming modern_di.Group.get_named_providers(), fixing the KeyError when autowiring a Group that inherits providers.
---

# Design: Autowired dependencies as a deep, inheritance-correct module

## Summary

`ModernDIPlugin.on_app_init` autowires each `autowired_groups` provider as a
Litestar dependency keyed by its declared attribute name. It recovers those
names with a fragile `id()`-keyed reverse lookup built from `group.__dict__`
only, while `group.get_providers()` walks the full MRO — so a `Group` that
**inherits** a provider raises `KeyError`. Replace the inline loop with a
module-level `_autowired_dependencies(groups, *, existing) -> dict[str, Provide]`
that reads names from `modern_di.Group.get_named_providers()` (MRO-aware,
shipped in `modern-di` 2.20.0) and owns all duplicate-name detection. This fixes
the inheritance bug and gives the autowiring a direct test surface.

## Motivation

Today's loop (`modern_di_litestar/main.py`):

```python
for group in self.groups:
    name_by_provider_id = {id(v): k for k, v in group.__dict__.items() if isinstance(v, providers.AbstractProvider)}
    for provider in group.get_providers():
        name = name_by_provider_id[id(provider)]   # KeyError for inherited providers
        ...
```

`name_by_provider_id` is built from the subclass `__dict__`, but
`get_providers()` returns providers from the whole MRO. Reproduced against the
current code: autowiring `class Child(Base)` where `Base` declares a provider
raises `KeyError: <id>` at app-construction time.

The only test surface for autowiring is a full `TestClient` round-trip — name
resolution and duplicate detection can't be exercised directly. `modern-di`
2.20.0 added `Group.get_named_providers() -> dict[str, AbstractProvider]` (the
MRO-aware name→provider map) precisely so integrations stop re-deriving names.

## Non-goals

- Changing the public API (`ModernDIPlugin`, `FromDI`, the providers). The new
  function is internal (`_autowired_dependencies`, not exported).
- Changing duplicate-name semantics: the `UserWarning` message, its attribution
  frame, last-write-wins overwrite, and detection of both group-vs-group and
  group-vs-already-registered collisions are all preserved. (The `stacklevel`
  literal moves `2 → 3` because the `warn` call is now one frame deeper inside
  `_autowired_dependencies`; 3 points at the same caller the original 2 did.)

## Design

### 1. `_autowired_dependencies`

A module-level function in `main.py`:

```python
def _autowired_dependencies(
    groups: list[type[Group]], *, existing: typing.Iterable[str] = ()
) -> dict[str, Provide]:
    result: dict[str, Provide] = {}
    seen: set[str] = set(existing)
    for group in groups:
        for name, provider in group.get_named_providers().items():
            if name in seen:
                # stacklevel=3: warn -> _autowired_dependencies -> on_app_init -> caller,
                # matching the attribution of the original in-place warning in on_app_init.
                warnings.warn(
                    f"Duplicate dependency name '{name}' from group {group.__name__!r}; overwriting.",
                    stacklevel=3,
                )
            seen.add(name)
            result[name] = FromDI(provider)
    return result
```

Names now come from `get_named_providers()` (MRO-aware), so inherited providers
are included with their declared names — the bug is fixed. `existing` seeds the
collision set with names already registered on the app (e.g. `di_container`),
so group-vs-existing collisions still warn; group-vs-group collisions warn via
the accumulating `seen`.

### 2. `on_app_init` shrinks to one line

```python
app_config.dependencies.update(_autowired_dependencies(self.groups, existing=app_config.dependencies))
```

The context-provider registration, `state.di_container`, the `di_container`
Provide, and the `lifespan.append` are untouched. `.update(...)` preserves the
last-write-wins overwrite of the original loop.

### 3. Direct test surface

Because `_autowired_dependencies` is a plain function, its behavior is tested
without a `TestClient`: the name→`Provide` mapping and the collision warning
are asserted directly. The inheritance fix is covered by a focused integration
test (the smallest app that previously raised `KeyError`).

## Testing

New tests in `tests/test_groups.py`:

- `test_autowiring_resolves_inherited_provider` — integration; the app that
  reproduced the `KeyError` now builds and resolves the inherited provider.
- `test_autowired_dependencies_maps_provider_names_to_provides` — direct;
  returns `Provide` values keyed by provider name.
- `test_autowired_dependencies_warns_on_existing_name_collision` — direct;
  a name already in `existing` warns with the group name.

Existing `test_group_auto_wiring` and `test_group_duplicate_name_warning` stay
green (behavior preserved). Gate: `just test-ci` (100% line coverage).

## Risk

Low. Internal refactor of a single function plus a one-line bug fix, fully
covered by new and existing tests. The dependency floor moves to
`modern-di>=2.20.0` (already on PyPI); CI resolves it from the registry.
