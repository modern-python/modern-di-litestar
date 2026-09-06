# No `Annotated`-marker injection path; `FromDI` returns Litestar's `Provide`

**Decision:** this package uses only the connection half of `modern_di.integrations`
(`classify_connection`, `Marker.resolve`). It will not ship an `@inject` decorator, and will not
call `integrations.parse_markers` / `resolve_markers`.

The kit offers two layers. Layer 1 derives a child container's scope and context from a connection;
`build_di_container` uses it. Layer 2 is an `Annotated`-marker injector: a decorator scans a
handler's signature once at decoration time, then resolves each marked parameter per call. It
exists for frameworks with no dependency injection of their own.

Litestar has one. A handler declares `dependencies={"repo": FromDI(...)}`, or names an autowired
provider as a parameter, and Litestar scans the signature and binds each parameter itself. `FromDI`
therefore returns a real `litestar.di.Provide`, and the only modern-di code on the request path is
one `Marker.resolve(container)` call inside it. Adding a decorator would put a second scanner over
the same signature, with its own binding rules to keep in agreement with Litestar's — two mechanisms
answering one question, where today the framework answers it. It also fails the deletion test:
remove the decorator and no complexity reappears, because every call site is already a `Provide`.

This is the native-DI path modern-di's own
[integration guide](https://github.com/modern-python/modern-di/blob/main/docs/integrations/writing-integrations.md)
prescribes for FastAPI, FastStream and Litestar, and the shape settled by
[its ADR 0008](https://github.com/modern-python/modern-di/blob/main/docs/adr/0008-integration-kit-shape.md).
The alternative gets proposed anyway, from parity with the decorator-path integrations, which is why
it is written down rather than re-argued.

**Revisit trigger:** a call site Litestar's own dependency injection cannot reach — a background
task, a CLI entry point, or any callable Litestar never binds parameters for — needs providers
resolved, or a Litestar major release changes or removes the `Provide` seam. Either makes the
decorator path a second real adapter rather than a duplicate of the framework's.
