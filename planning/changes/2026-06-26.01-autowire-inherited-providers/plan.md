# autowire-inherited-providers — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the `id()`-keyed reverse lookup in `ModernDIPlugin.on_app_init`
with a directly-testable `_autowired_dependencies` function consuming
`modern_di.Group.get_named_providers()`, fixing the `KeyError` when autowiring a
Group that inherits providers.

**Spec:** [`design.md`](./design.md)

**Branch:** `fix/autowire-inherited-providers`

**Commit strategy:** Per-task commits.

## Global Constraints

- `modern-di>=2.20.0,<3` — `Group.get_named_providers()` exists only from 2.20.0.
- Run tests via `just test [args]`; the 100% line-coverage gate is `just test-ci` — never call `pytest` directly.
- `just lint-ci` is the non-fixing gate (eof-fixer, ruff, ty, **and** the planning validator); run it against an already-committed clean tree as the final check.
- Type suppression, if ever needed, is `# ty: ignore` (never `# type: ignore`). None expected.
- All imports at module level. Annotate every test function argument.
- `_autowired_dependencies` is internal: keep it in `modern_di_litestar/main.py`, do NOT add it to `__all__` or re-export from `__init__.py`.
- Preserve behavior exactly except the inheritance fix: warn message `f"Duplicate dependency name '{name}' from group {group.__name__!r}; overwriting."`, the warning's attribution frame (`stacklevel=3` — the `warn` is now one frame deeper inside `_autowired_dependencies` than the original in-place `stacklevel=2`, so 3 points at the same caller), last-write-wins overwrite, and collision detection for both group-vs-group and group-vs-already-registered names.
- This change alters the autowiring capability → it must create/update `architecture/autowiring.md` in this same PR (Task 3), per the planning convention.

---

### Task 1: Bump `modern-di` floor to 2.20.0 and refresh the lockfile

**Files:**
- Modify: `pyproject.toml:20`
- Modify: `uv.lock`

**Interfaces:**
- Produces: `modern_di.Group.get_named_providers()` available at runtime, so Task 2 can consume it.

- [ ] **Step 1: Edit the dependency specifier**

  In `pyproject.toml` line 20, change `"modern-di>=2.19.0,<3"` to `"modern-di>=2.20.0,<3"`. The full line becomes:

  ```toml
  dependencies = ["litestar>=2.23,<3", "modern-di>=2.20.0,<3"]
  ```

- [ ] **Step 2: Upgrade only modern-di in the lockfile and sync**

  ```bash
  uv lock --upgrade-package modern-di
  uv sync --all-extras --group lint
  ```
  Expected: resolves `modern-di==2.20.0` (or newer 2.x) and installs it.

- [ ] **Step 3: Verify the accessor is importable**

  ```bash
  uv run --no-sync python -c "from modern_di import Group; print(Group.get_named_providers)"
  ```
  Expected: prints a bound method (no `AttributeError`).

- [ ] **Step 4: Verify the existing suite still passes**

  Run: `just test`
  Expected: PASS — no behavior changed yet.

- [ ] **Step 5: Commit**

  ```bash
  git add pyproject.toml uv.lock
  git commit -m "chore: require modern-di>=2.20.0 for get_named_providers"
  ```

---

### Task 2: Extract `_autowired_dependencies` and fix inherited-provider autowiring (TDD)

**Files:**
- Modify: `modern_di_litestar/main.py` (the `on_app_init` autowiring loop)
- Test: `tests/test_groups.py`

**Interfaces:**
- Consumes: `modern_di.Group.get_named_providers() -> dict[str, AbstractProvider]` (Task 1).
- Produces: `_autowired_dependencies(groups: list[type[Group]], *, existing: typing.Iterable[str] = ()) -> dict[str, Provide]` — module-level in `main.py`. One `litestar.di.Provide` per provider keyed by declared name; warns (not raises) on each name already in `existing` or seen in an earlier group; last write wins.

- [ ] **Step 1: Write the failing integration test (reproduces the KeyError)**

  Append to `tests/test_groups.py`:

  ```python
  def test_autowiring_resolves_inherited_provider() -> None:
      class BaseGroup(Group):
          inherited = providers.Factory(creator=SimpleCreator, kwargs={"dep1": "inherited"})

      class ChildGroup(BaseGroup): ...

      groups = [ChildGroup]
      app = litestar.Litestar(
          debug=True,
          plugins=[modern_di_litestar.ModernDIPlugin(Container(groups=groups), autowired_groups=groups)],
      )

      @litestar.get("/")
      async def read_root(inherited: SimpleCreator) -> None:
          assert isinstance(inherited, SimpleCreator)
          assert inherited.dep1 == "inherited"

      app.register(read_root)

      with TestClient(app=app, raise_server_exceptions=True) as client:
          response = client.get("/")
          assert response.status_code == status_codes.HTTP_200_OK, response.text
  ```

- [ ] **Step 2: Run the test to verify it fails with KeyError**

  Run: `just test tests/test_groups.py -k inherited -v`
  Expected: FAIL — building the app raises `KeyError` from `on_app_init` (the inherited provider's id is absent from `name_by_provider_id`, built from `ChildGroup.__dict__` only).

- [ ] **Step 3: Add the `_autowired_dependencies` function**

  In `modern_di_litestar/main.py`, add this module-level function directly above the `ModernDIPlugin` class (after `_lifespan_manager`):

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

- [ ] **Step 4: Rewire `on_app_init` to use it**

  Replace the autowiring loop in `on_app_init` — these lines:

  ```python
          for group in self.groups:
              name_by_provider_id = {
                  id(v): k for k, v in group.__dict__.items() if isinstance(v, providers.AbstractProvider)
              }
              for provider in group.get_providers():
                  name = name_by_provider_id[id(provider)]
                  if name in app_config.dependencies:
                      warnings.warn(
                          f"Duplicate dependency name '{name}' from group {group.__name__!r}; overwriting.",
                          stacklevel=2,
                      )
                  app_config.dependencies[name] = FromDI(provider)
  ```

  with this single line:

  ```python
          app_config.dependencies.update(_autowired_dependencies(self.groups, existing=app_config.dependencies))
  ```

  Leave the rest of `on_app_init` (context-provider registration, `state.di_container`, the `di_container` Provide, and `lifespan.append`) unchanged.

- [ ] **Step 5: Run the inheritance test to verify it passes**

  Run: `just test tests/test_groups.py -k inherited -v`
  Expected: PASS.

- [ ] **Step 6: Add direct unit tests for the function**

  Append to `tests/test_groups.py` (the `Provide` and `_autowired_dependencies` imports are added in Step 7):

  ```python
  def test_autowired_dependencies_maps_provider_names_to_provides() -> None:
      result = _autowired_dependencies([Dependencies])
      assert isinstance(result["app_factory"], Provide)
      assert {"app_factory", "request_factory", "session_factory"} <= set(result)


  def test_autowired_dependencies_warns_on_existing_name_collision() -> None:
      with warnings.catch_warnings(record=True) as caught:
          warnings.simplefilter("always")
          _autowired_dependencies([Dependencies], existing={"app_factory"})

      collisions = [w for w in caught if issubclass(w.category, UserWarning) and "app_factory" in str(w.message)]
      assert len(collisions) == 1
      assert "Dependencies" in str(collisions[0].message)
  ```

- [ ] **Step 7: Add the test imports**

  At the top of `tests/test_groups.py`, add:

  ```python
  from litestar.di import Provide

  from modern_di_litestar.main import _autowired_dependencies
  ```

  (`warnings`, `litestar`, `status_codes`, `TestClient`, `Container`, `Group`, `providers`, `modern_di_litestar`, and the `tests.dependencies` names are already imported — do not duplicate.)

- [ ] **Step 8: Run the full test file, then the coverage gate**

  Run: `just test tests/test_groups.py -v`
  Expected: PASS — inheritance test, both unit tests, `test_group_auto_wiring`, `test_group_duplicate_name_warning` all green.

  Run: `just test-ci`
  Expected: PASS — 100% line coverage; `_autowired_dependencies` fully covered (warn branch via the collision tests, non-warn via auto-wiring).

- [ ] **Step 9: Verify the lint gate**

  Run: `just lint` then `just lint-ci`
  Expected: `lint-ci` PASS. (`providers` stays imported — it's still used by the module-level `ContextProvider` definitions — so its import does not become unused.)

- [ ] **Step 10: Commit**

  ```bash
  git add modern_di_litestar/main.py tests/test_groups.py
  git commit -m "fix: autowire inherited providers via get_named_providers"
  ```

---

### Task 3: Promote the autowiring capability into `architecture/`

**Files:**
- Create: `architecture/autowiring.md`
- Modify: `architecture/README.md` (Capabilities list)

The planning convention requires the capability truth-home to move in the same
PR as the behavior change. `architecture/` currently has no capability files;
this is the first.

- [ ] **Step 1: Create `architecture/autowiring.md`**

  Write `architecture/autowiring.md` with exactly:

  ```markdown
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
  ```

- [ ] **Step 2: Add the capability to `architecture/README.md`**

  In `architecture/README.md`, replace the `## Capabilities` body — these lines:

  ```markdown
  Capability files are added here as behavior is documented: a change that
  introduces or alters a capability creates or edits its file in the same PR that
  ships the code.

  _None yet — this directory was seeded when the planning convention was adopted;
  the first capability file lands with the next behavioral change._
  ```

  with:

  ```markdown
  Capability files are added here as behavior is documented: a change that
  introduces or alters a capability creates or edits its file in the same PR that
  ships the code.

  - [autowiring.md](autowiring.md) — how `ModernDIPlugin` registers
    `autowired_groups` providers as Litestar dependencies by name.
  ```

- [ ] **Step 3: Verify the lint gate (Markdown EOF + planning validator)**

  Run: `just lint-ci`
  Expected: PASS.

- [ ] **Step 4: Commit**

  ```bash
  git add architecture/autowiring.md architecture/README.md
  git commit -m "docs: document autowiring capability in architecture/"
  ```

---

### Task 4: Finalize the bundle, full gate, push, and PR

**Files:**
- The bundle: `planning/changes/2026-06-26.01-autowire-inherited-providers/` (`design.md`, `plan.md`).

- [ ] **Step 1: Confirm the bundle summary states the realized result**

  The `summary:` in `design.md` already describes the shipped behavior; edit
  only if implementation diverged.

- [ ] **Step 2: Commit the bundle**

  ```bash
  git add planning/changes/2026-06-26.01-autowire-inherited-providers/
  git commit -m "docs: add planning bundle for autowire-inherited-providers"
  ```

- [ ] **Step 3: Run the full non-fixing gate**

  Run: `just check-planning && just lint-ci && just test-ci`
  Expected: `planning: OK`; lint clean; 100% coverage, whole suite green.

- [ ] **Step 4: Confirm a clean working tree**

  Run: `git status --short`
  Expected: empty (no stray `coverage.xml`; it is gitignored).

- [ ] **Step 5: Push and open the PR**

  ```bash
  git push -u origin fix/autowire-inherited-providers
  gh pr create --fill --base main
  ```

  Watch CI (`gh pr checks`). The PR depends on `modern-di 2.20.0`, already on PyPI, so CI resolves it from the registry.

---

## Self-review notes

- **Spec coverage:** dep bump (Task 1), `_autowired_dependencies` + inheritance fix + duplicate-detection preservation + direct unit tests (Task 2), `architecture/autowiring.md` promotion (Task 3), bundle finalize + gate + PR (Task 4).
- **Convention:** Full lane (new internal module, behavior change, non-trivial test design); capability promotion rides in the same PR; bundle committed in-PR; `just check-planning` in the gate.
- **Behavior preservation:** warn message, `stacklevel`, last-write-wins, dual collision detection all retained; only the name source changes (MRO-aware `get_named_providers()`), which is the fix.
- **Type consistency:** `_autowired_dependencies(groups: list[type[Group]], *, existing: typing.Iterable[str] = ()) -> dict[str, Provide]` used identically in `on_app_init` and tests; `Provide` from `litestar.di`, `Group` from `modern_di`, both already imported in `main.py`.
