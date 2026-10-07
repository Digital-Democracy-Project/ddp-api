"""Public /docs turns off "Try it out" for write actions (API-9).

Every mutating operation is flagged `x-ddp-write` unless it is on the short
READ_ONLY_POSTS list, and the docs page loads the plugin that hides the button
on flagged operations. The plugin itself runs in the browser, so it is checked
by hand (see the PR); these tests pin everything the server decides.
"""
import asyncio

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.middleware.auth import read_auth, write_auth
from app.services import docs_try_it_out as tio
from app.services import downstream_openapi as dso


def _dependencies(dependant, found=None):
    found = set() if found is None else found
    for sub in dependant.dependencies:
        found.add(sub.call)
        _dependencies(sub, found)
    return found


def _local_mutating_routes():
    """(method, path) -> auth dependencies, for ddp-api's own routes.

    FastAPI 0.141 wraps routers added with include_router in objects holding the
    original router; 0.128 (production) keeps plain routes. Handle both.
    """
    routes = {}

    def add(route, prefix=""):
        for method in getattr(route, "methods", None) or ():
            if method.lower() in tio.MUTATING:
                routes[(method.lower(), prefix + route.path)] = _dependencies(route.dependant)

    for top in app.routes:
        if hasattr(top, "original_router"):
            prefix = getattr(top.include_context, "prefix", "") or ""
            for route in top.original_router.routes:
                add(route, prefix)
        else:
            add(top)
    return routes


def read_only_list_problems():
    """Every READ_ONLY_POSTS entry must be a real route that needs only a read key."""
    routes = _local_mutating_routes()
    problems = []
    for key in sorted(tio.READ_ONLY_POSTS):
        deps = routes.get(key)
        if deps is None:
            problems.append(f"{key} is not a route")
        elif write_auth in deps or read_auth not in deps:
            problems.append(f"{key} does not run on a read key alone")
    return problems


def test_read_only_list_only_holds_read_scoped_routes():
    assert read_only_list_problems() == []


def test_a_write_route_on_the_read_only_list_is_caught(monkeypatch):
    monkeypatch.setattr(tio, "READ_ONLY_POSTS", tio.READ_ONLY_POSTS | {("post", "/create_event")})
    assert any("/create_event" in p for p in read_only_list_problems())


def _public_spec(monkeypatch):
    async def no_downstream(url, cache_key):
        return None

    monkeypatch.setattr(dso, "_fetch_spec", no_downstream)
    return TestClient(app).get("/openapi.json").json()


def test_every_mutating_operation_is_blocked_except_read_only_posts(monkeypatch):
    spec = _public_spec(monkeypatch)
    seen_read_only = set()
    for path, item in spec["paths"].items():
        for method, op in item.items():
            if method in tio.MUTATING and (method, path) not in tio.READ_ONLY_POSTS:
                assert op.get("x-ddp-write") is True, f"{method.upper()} {path} can still be tried"
            else:
                assert "x-ddp-write" not in op, f"{method.upper()} {path} is blocked but should not be"
                seen_read_only.add((method, path))
    assert tio.READ_ONLY_POSTS <= seen_read_only, "a read-only POST is missing from the spec"


def test_job_starting_buttons_are_blocked(monkeypatch):
    """The four zero-input job starters from the API-9 ticket."""
    async def downstream(url, cache_key):
        if cache_key == "openstates":
            return {"paths": {"/ddp/search/refresh": {"post": {"summary": "x"}}}}
        return {"paths": {f"/ddp-sync/v1/trigger/{name}": {"post": {"summary": "x"}}
                          for name in ("user-sync", "full-sync", "bill-version-check")}}

    monkeypatch.setattr(dso, "_fetch_spec", downstream)
    base = {"paths": {}, "components": {"schemas": {}}}
    asyncio.run(dso.merge_ddp_sync(base, "http://sync"))
    asyncio.run(dso.merge_openstates(base, "http://openstates"))
    tio.mark_write_operations(base)
    for path in (
        "/trigger/user-sync",
        "/trigger/full-sync",
        "/trigger/bill-version-check",
        "/openstates/ddp/search/refresh",
    ):
        assert base["paths"][path]["post"]["x-ddp-write"] is True, path


def test_docs_page_loads_the_plugin():
    html = TestClient(app).get("/docs").text
    assert "plugins: [BlockWriteTryItOut]" in html
    assert '"persistAuthorization": true' in html


def test_plugin_injection_fails_loudly_on_a_changed_template():
    with pytest.raises(RuntimeError):
        tio.with_write_block("<html>not swagger</html>")
