"""Guard for proxied ddp-sync routes on /docs (API-7).

test_downstream_examples.py pins the example map; this runs the real merge over
a snapshot of ddp-sync's own OpenAPI spec and fails on any mutating route that
would reach /docs unsafe: a JSON body with no example, a dry_run that is not
true, or a job that starts on Execute with no warning.

The snapshot is ddp-sync origin/main at faa9630. It does not follow ddp-sync by
itself: when ddp-sync adds a route, regenerate it (mount its `triggers` and
`sync_unified` routers on a bare FastAPI app under /ddp-sync/v1 and dump
`app.openapi()`) and this test names whatever the new route is missing.
"""
import asyncio
import copy
import json
from pathlib import Path

from app.services import downstream_openapi as dso

MUTATING = {"post", "put", "patch", "delete"}
SNAPSHOT = Path(__file__).parent / "fixtures" / "ddp_sync_main_openapi.json"


def _merged(monkeypatch, downstream):
    async def fake_fetch(url, cache_key):
        return copy.deepcopy(downstream)

    monkeypatch.setattr(dso, "_fetch_spec", fake_fetch)
    base = {"paths": {}, "components": {"schemas": {}}}
    asyncio.run(dso.merge_ddp_sync(base, "http://downstream"))
    return base


def _starts_job_on_execute(op):
    """No body, no required input, and no dry-run switch left in the safe position."""
    params = op.get("parameters", [])
    if op.get("requestBody") or any(p.get("required") for p in params):
        return False
    for p in params:
        default = p.get("schema", {}).get("default")
        if (p["name"] == "dry_run" and default is True) or (p["name"] == "mode" and default == "dry-run"):
            return False
    return True


def violations(spec):
    found = []
    for path, item in spec["paths"].items():
        for method, op in item.items():
            if method not in MUTATING:
                continue
            label = f"{method.upper()} {path}"
            for media in (op.get("requestBody") or {}).get("content", {}).values():
                example = media.get("example")
                if example is None:
                    found.append(f"{label}: JSON body has no example")
                elif example.get("dry_run", True) is not True:
                    found.append(f"{label}: example turns dry_run off")
            for p in op.get("parameters", []):
                if p["name"] == "dry_run" and p.get("schema", {}).get("default") is not True:
                    found.append(f"{label}: dry_run does not default to true")
            if _starts_job_on_execute(op) and dso._JOB_WARNING not in op.get("description", ""):
                found.append(f"{label}: starts a job on Execute with no warning")
    return found


def test_merged_ddp_sync_routes_are_safe(monkeypatch):
    snapshot = json.loads(SNAPSHOT.read_text())
    spec = _merged(monkeypatch, snapshot)
    assert len(spec["paths"]) > 15, "snapshot did not merge"
    assert violations(spec) == []


def test_guard_catches_an_example_that_was_removed(monkeypatch):
    snapshot = json.loads(SNAPSHOT.read_text())
    monkeypatch.delitem(dso._BODY_EXAMPLES, ("post", "/trigger/legbot-analyze-bill"))
    assert any("legbot-analyze-bill:" in v and "no example" in v for v in violations(_merged(monkeypatch, snapshot)))


def test_guard_catches_a_destructive_example(monkeypatch):
    snapshot = json.loads(SNAPSHOT.read_text())
    key = ("post", "/trigger/bill-artifact-generation")
    monkeypatch.setitem(dso._BODY_EXAMPLES, key, {**dso._BODY_EXAMPLES[key], "dry_run": False})
    assert any("example turns dry_run off" in v for v in violations(_merged(monkeypatch, snapshot)))


def test_guard_catches_a_dry_run_that_defaults_to_false(monkeypatch):
    snapshot = json.loads(SNAPSHOT.read_text())
    monkeypatch.delitem(dso._PARAM_DEFAULTS, ("post", "/trigger/legislator-bio-sync", "dry_run"))
    assert any("legislator-bio-sync" in v and "dry_run" in v for v in violations(_merged(monkeypatch, snapshot)))


def test_guard_catches_a_job_starter_with_no_warning(monkeypatch):
    snapshot = json.loads(SNAPSHOT.read_text())
    monkeypatch.setattr(dso, "_JOB_STARTERS", dso._JOB_STARTERS - {("post", "/trigger/user-sync")})
    assert any("/trigger/user-sync" in v and "no warning" in v for v in violations(_merged(monkeypatch, snapshot)))


def test_openstates_search_refresh_is_warned(monkeypatch):
    async def fake_fetch(url, cache_key):
        return {"paths": {"/ddp/search/refresh": {"post": {"summary": "x"}}}}

    monkeypatch.setattr(dso, "_fetch_spec", fake_fetch)
    base = {"paths": {}, "components": {"schemas": {}}}
    asyncio.run(dso.merge_openstates(base, "http://downstream"))
    assert dso._JOB_WARNING in base["paths"]["/openstates/ddp/search/refresh"]["post"]["description"]
