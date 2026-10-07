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


def test_legislator_bio_sync_defaults_to_dry_run(monkeypatch):
    downstream = {
        "paths": {
            "/ddp-sync/v1/trigger/legislator-bio-sync": {
                "post": {"parameters": [{"name": "dry_run", "in": "query", "schema": {"type": "boolean", "default": False}}]}
            }
        }
    }
    spec = _merge(monkeypatch, downstream, dso.merge_ddp_sync)
    param = spec["paths"]["/trigger/legislator-bio-sync"]["post"]["parameters"][0]
    assert param["schema"]["default"] is True


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


# The real public paths of the proxied write routes that get an example,
# written out independently of the map so a typo in the map cannot hide.
EXPECTED_EXAMPLE_KEYS = {
    ("post", "/sync/unified"),
    ("post", "/trigger/bill-artifact-generation"),
    ("post", "/trigger/legbot-analyze-bill"),
    ("post", "/trigger/legbot-analyze-bill-full"),
    ("post", "/broker/api/bill-artifacts/"),
    ("post", "/broker/api/bill-versions/"),
    ("post", "/broker/api/bills/ensure/"),
    ("post", "/broker/api/bill-promotion-requests/"),
    ("post", "/broker/api/concept-statement-sets/"),
    ("post", "/broker/api/concept-votes/"),
    ("post", "/broker/api/flags/"),
    ("post", "/broker/api/bill-organization-positions/"),
    ("post", "/broker/api/bill-organization-research-runs/"),
}


def test_example_keys_are_the_real_public_paths():
    assert set(dso._BODY_EXAMPLES) == EXPECTED_EXAMPLE_KEYS


def test_every_example_key_is_consumed_by_the_merge(monkeypatch):
    """Run each key through the real merge (path prefix rewrite included) and
    require the example to attach."""
    prefixes = {"/sync": "/ddp-sync/v1", "/trigger": "/ddp-sync/v1", "/broker": ""}
    merges = {"/sync": dso.merge_ddp_sync, "/trigger": dso.merge_ddp_sync, "/broker": dso.merge_broker}
    for (method, path), example in dso._BODY_EXAMPLES.items():
        root = "/" + path.split("/")[1]
        downstream_path = prefixes[root] + (path[len("/broker"):] if root == "/broker" else path)
        spec = _merge(monkeypatch, {"paths": {downstream_path: {method: {"summary": "x"}}}}, merges[root])
        body = spec["paths"][path][method]["requestBody"]["content"]["application/json"]
        assert body["example"] == example, f"{method.upper()} {path} was not applied"
