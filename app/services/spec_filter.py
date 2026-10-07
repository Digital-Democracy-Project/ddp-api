"""Split the generated OpenAPI document into the public and admin documents (API-11).

Which routes are admin routes is decided from the built spec's paths, never from
route objects: FastAPI 0.141 wraps routers added with include_router in objects
that have no `path`, so filtering routes by path silently kept the admin routes
on the public page and left /admin/openapi.json empty.
"""

_SCHEMA_REF = "#/components/schemas/"


def is_admin_path(path: str) -> bool:
    return path == "/admin" or path.startswith("/admin/")


def _refs(node, found: set) -> None:
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith(_SCHEMA_REF):
            found.add(ref[len(_SCHEMA_REF):])
        for value in node.values():
            _refs(value, found)
    elif isinstance(node, list):
        for item in node:
            _refs(item, found)


def filter_paths(spec: dict, keep) -> None:
    """Keep only paths where keep(path) is true, and drop the component schemas
    no remaining path uses, so the other document's models do not show up here."""
    spec["paths"] = {p: item for p, item in spec["paths"].items() if keep(p)}
    schemas = spec.get("components", {}).get("schemas", {})
    needed: set = set()
    _refs(spec["paths"], needed)
    pending = list(needed)
    while pending:
        name = pending.pop()
        found: set = set()
        _refs(schemas.get(name, {}), found)
        pending.extend(found - needed)
        needed |= found
    for name in set(schemas) - needed:
        del schemas[name]
