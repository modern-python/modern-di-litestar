# No `Annotated`-marker injection path; `FromDI` returns Litestar's `Provide`

Litestar binds handler parameters itself, so this package uses only the connection half of
`modern_di.integrations` - `classify_connection`, which `build_di_container` uses to derive a child
container's scope and context, and `Marker.resolve` inside `FromDI` - and ships no `@inject`
decorator, never calling `parse_markers` or `resolve_markers`. `FromDI` returns a real
`litestar.di.Provide`, named in a handler's `dependencies={...}` or, with `autowired_groups`, bound
by parameter name. A decorator would put a second signature scanner over the one Litestar already
runs, with its own binding rules to keep in agreement, and since every call site is already a
`Provide`, deleting it would reveal no hidden complexity. This is the native-DI path modern-di's
[integration guide](https://github.com/modern-python/modern-di/blob/main/docs/integrations/writing-integrations.md)
prescribes for FastAPI, FastStream and Litestar; parity with the decorator-path integrations keeps
the alternative coming back, and it becomes a real adapter only where Litestar binds no parameters
at all, as in a background task or a CLI entry point.
