"""Proxied write routes ship safe /docs examples (API-7).

Downstream specs carry no request-body examples, so the merge injects them.
Examples are for non-destructive testing only: dry_run true where the route has
one, otherwise values the downstream rejects before any write.
"""
import asyncio

from app.services import downstream_openapi as dso


def _merge(monkeypatch, downstream, merge):
    async def fake_fetch(url, cache_key):
        return downstream

    monkeypatch.setattr(dso, "_fetch_spec", fake_fetch)
    base = {"paths": {}, "components": {"schemas": {}}}
    asyncio.run(merge(base, "http://downstream"))
    return base


def test_ddp_sync_unified_example_is_a_dry_run(monkeypatch):
    downstream = {
        "paths": {
            "/ddp-sync/v1/sync/unified": {
                "post": {"requestBody": {"content": {"application/json": {"schema": {"type": "object"}}}}}
            }
        }
    }
    spec = _merge(monkeypatch, downstream, dso.merge_ddp_sync)
    example = spec["paths"]["/sync/unified"]["post"]["requestBody"]["content"]["application/json"]["example"]
    assert example["dry_run"] is True


def test_ddp_sync_batch_defaults_to_dry_run(monkeypatch):
    downstream = {
        "paths": {
            "/ddp-sync/v1/sync/unified/all": {
                "post": {"parameters": [{"name": "dry_run", "in": "query", "schema": {"type": "boolean", "default": False}}]}
            }
        }
    }
    spec = _merge(monkeypatch, downstream, dso.merge_ddp_sync)
    param = spec["paths"]["/sync/unified/all"]["post"]["parameters"][0]
    assert param["schema"]["default"] is True


def test_unlisted_routes_are_left_alone(monkeypatch):
    downstream = {"paths": {"/ddp-sync/v1/sync/other": {"post": {"summary": "x"}}}}
    spec = _merge(monkeypatch, downstream, dso.merge_ddp_sync)
    assert "requestBody" not in spec["paths"]["/sync/other"]["post"]


def test_every_example_is_non_destructive():
    for (method, path), example in dso._BODY_EXAMPLES.items():
        assert example.get("dry_run", True) is True, f"{method.upper()} {path} turns dry_run off"
    for (method, path, name), default in dso._PARAM_DEFAULTS.items():
        if name == "dry_run":
            assert default is True, f"{method.upper()} {path} defaults dry_run off"


def test_unguarded_broker_routes_keep_their_invalid_field():
    """These two broker routes do no existence check; one invalid field is all
    that keeps their example from creating a row."""
    sets = dso._BODY_EXAMPLES[("post", "/broker/api/concept-statement-sets/")]
    runs = dso._BODY_EXAMPLES[("post", "/broker/api/bill-organization-research-runs/")]
    assert sets["statements"] == []
    assert runs["positions_found_count"] < 0


def test_broker_post_with_no_declared_body_gets_one(monkeypatch):
    downstream = {"paths": {"/api/flags/": {"post": {"summary": "x"}}, "/api/bill-organization-positions/": {"post": {"summary": "y"}}}}
    spec = _merge(monkeypatch, downstream, dso.merge_broker)
    body = spec["paths"]["/broker/api/bill-organization-positions/"]["post"]["requestBody"]
    assert body["content"]["application/json"]["example"]["jurisdiction"] == "ZZ"
