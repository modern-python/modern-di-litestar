# modern-di-litestar

A [Litestar](https://litestar.dev) integration for
[`modern-di`](https://github.com/modern-python/modern-di): a plugin that ties a container's
lifecycle to the app, opens a scoped child container per HTTP request and per websocket session,
and hands Litestar's own dependency injection the values providers produce.

## Language

A term is listed only when there is a synonym to reject, or a meaning subtle enough that code and
docs must agree on it. General programming vocabulary does not belong here, however heavily this
package uses it.

The domain terms are `modern-di`'s — `Container`, `Provider`, `Group`, `Scope`, `Resolution`,
`Override`, `Connection`. That project's `CONTEXT.md` is the authority for all of them; nothing here
redefines one. Litestar's own words (`Provide`, `dependencies`, `Request`, `WebSocket`, plugin,
handler) keep Litestar's meanings. The three below are this package's own.

**Autowiring**:
Registering every provider of a `Group` as a Litestar dependency, so a handler can name one as a
parameter without a per-route `dependencies={...}` entry. `autowired_groups` on the plugin turns it
on; `FromDI` is the explicit counterpart, naming one provider at one call site.
_Avoid_: auto-registration, auto-wiring — the API spells it `autowired_groups`, and prose that
drifts to "auto-registers" reads as a different mechanism from the one flag that controls it.

**Autowired name**:
The class attribute a provider is declared under in its `Group`, including one inherited from a base
`Group`. That name — not the provider's bound type — is the Litestar dependency key, so it is what a
handler parameter must match and what collides between groups.

**Root container**:
The `Container` the plugin owns: attached to `app.state`, opened and closed by the Litestar
lifespan, and the parent of every per-connection child. The concept is `modern-di`'s; local to this
package is only where it lives.
_Avoid_: app-level container — "app-level" reads as `Scope.APP` and blurs the container with the
scope it happens to sit at.
