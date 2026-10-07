"""Merges live OpenAPI specs from proxied downstream services into ddp-api's
own generated docs.

ddp_sync_proxy.py, openstates_proxy.py, and broker_proxy.py are catch-all
proxies -- FastAPI can only describe them by their generic `{path}` shape,
not the real request/response schemas of whatever they're forwarding to.
This module fetches each downstream service's own OpenAPI spec and splices
its path items and component schemas into ddp-api's spec, remounted under
the proxy's public prefix. ddp-sync and the local OpenStates api-v3 are
plain FastAPI apps exposing one at /openapi.json; ddp-broker-py is Django +
drf-spectacular, exposing one at /api/schema/ instead.

Each fetch is cached in-memory with a TTL: fetching on every /docs load
would be slow and would make the public docs page depend on all three
downstream services being reachable. A stale cache or a failed fetch
degrades gracefully -- the generic catch-all entry for that proxy is left
in place untouched.
"""

import logging
import time
from typing import Callable, Optional

import httpx

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = 300
_cache: dict[str, tuple[float, Optional[dict]]] = {}

# Request-body examples for proxied write routes, keyed by (method, public path).
# Downstream specs ship none, so Swagger would pre-fill "string"/0 (API-7).
# These are for NON-DESTRUCTIVE testing: run unmodified, an example must never
# write or delete real data. Routes with a dry_run flag set it true; the rest
# use values the downstream rejects before any write.
_NIL_UUID = "00000000-0000-0000-0000-000000000000"
_BODY_EXAMPLES: dict[tuple[str, str], dict] = {
    ("post", "/sync/unified"): {
        "content_type": "bill",
        "mode": "single",
        "slug": "example-do-not-use",
        "dry_run": True,
    },
    # ddp-sync /trigger routes with a JSON body. Both batch-style routes honour
    # dry_run ("preview scope without dispatching anything"), so it is true.
    ("post", "/trigger/bill-artifact-generation"): {
        "jurisdiction_iso2": "FL",
        "session_code": "2026F",
        "artifact_types": ["bill_summary"],
        "include_org_research": False,
        "include_concept_statements": False,
        "limit": 1,
        "retry_failed": False,
        "dry_run": True,
    },
    ("post", "/trigger/legbot-analyze-bill-full"): {
        "bill_openstates_id": _NIL_UUID,
        "jurisdiction": "FL",
        "session_code": "2026F",
        "gov_id": "HB1",
        "bill_source": "https://example.invalid/",
        "artifact_types": ["bill_summary"],
        "include_org_research": False,
        "include_concept_statements": False,
        "retry_failed": False,
        "dry_run": True,
    },
    # No dry_run on this one. ddp-sync rejects the unknown artifact_type (400)
    # and, past that, the all-zero bill id (404), both before any write.
    ("post", "/trigger/legbot-analyze-bill"): {
        "bill_openstates_id": _NIL_UUID,
        "jurisdiction": "FL",
        "session_code": "2026F",
        "bill_source": "https://example.invalid/",
        "artifact_type": "EXAMPLE-DO-NOT-USE",
    },
    # ddp-broker-py has no dry-run mode. Every broker example below is rejected
    # with a 400 by the broker's serializer/view BEFORE any write: the bill
    # ("ZZ", all-zero UUID) or parent row they point at cannot exist, or one
    # required field is deliberately invalid. Do not "fix" the invalid fields
    # on the two marked below -- those routes do no existence check, so a valid
    # body would create a row.
    ("post", "/broker/api/bill-artifacts/"): {
        "bill_openstates_id": _NIL_UUID,
        "jurisdiction": "ZZ",
        "session_code": "0000",
        "version_note": "EXAMPLE-DO-NOT-USE",
        "artifact_type": "bill_summary",
        "content": "EXAMPLE",
    },
    ("post", "/broker/api/bill-versions/"): {
        "bill_openstates_id": _NIL_UUID,
        "jurisdiction": "ZZ",
        "session_code": "0000",
        "version_note": "EXAMPLE-DO-NOT-USE",
    },
    # Omits the two classification fields; rejected before any lookup or sync.
    ("post", "/broker/api/bills/ensure/"): {
        "jurisdiction": "ZZ",
        "session_code": "0000",
        "gov_id": "HB1",
    },
    ("post", "/broker/api/bill-promotion-requests/"): {
        "gov_id": "HB1",
        "jurisdiction_iso2": "ZZ",
        "session_code": "0000",
    },
    # INERT ONLY BECAUSE statements IS EMPTY: no bill existence check here.
    ("post", "/broker/api/concept-statement-sets/"): {
        "gov_id": "HB1",
        "jurisdiction_iso2": "ZZ",
        "session_code": "0000",
        "statements": [],
    },
    ("post", "/broker/api/concept-votes/"): {
        "statement_set_id": 0,
        "statement_index": 0,
        "choice": "pass",
        "visitor_id": "EXAMPLE-DO-NOT-USE",
    },
    ("post", "/broker/api/flags/"): {
        "target_content_type": "bill",
        "target_id": 0,
        "reason": "other",
    },
    # The next two have no body in the broker's own schema; injected here.
    ("post", "/broker/api/bill-organization-positions/"): {
        "bill_openstates_id": _NIL_UUID,
        "jurisdiction": "ZZ",
        "session_code": "0000",
        "version_note": "EXAMPLE-DO-NOT-USE",
        "invocation_id": _NIL_UUID,
        "org_name": "EXAMPLE-DO-NOT-USE",
        "position": "support",
        "citation_url": "https://example.invalid/",
    },
    # INERT ONLY BECAUSE positions_found_count IS NEGATIVE: no bill check here.
    ("post", "/broker/api/bill-organization-research-runs/"): {
        "bill_openstates_id": _NIL_UUID,
        "jurisdiction": "ZZ",
        "session_code": "0000",
        "invocation_id": _NIL_UUID,
        "positions_found_count": -1,
    },
}

# Query-parameter defaults that make a route's unmodified "Try it out" a preview.
_PARAM_DEFAULTS: dict[tuple[str, str, str], object] = {
    ("post", "/sync/unified/all", "dry_run"): True,
    ("post", "/trigger/legislator-bio-sync", "dry_run"): True,
}

# Routes that start a real job the moment Execute is clicked and have no
# dry-run mode or input to make safe (API-7). A warning is a reminder, not a
# block; API-9 covers blocking. tests/test_downstream_spec_guard.py fails when
# a route like this is added downstream without being listed here.
_JOB_WARNING = (
    "**WARNING: this starts a real job.** Clicking Execute runs it immediately. "
    "There is no preview mode and nothing to fill in. Only click Execute if you mean to run it."
)
_JOB_STARTERS: set[tuple[str, str]] = {
    ("post", "/trigger/user-sync"),
    ("post", "/trigger/full-sync"),
    ("post", "/trigger/bill-version-check"),
    ("post", "/trigger/bill-status-sync"),
    ("post", "/trigger/votebot-eval"),
    ("post", "/trigger/grantbot-scrape-funders"),
    ("post", "/openstates/ddp/search/refresh"),
}


async def _fetch_spec(url: str, cache_key: str) -> Optional[dict]:
    now = time.time()
    cached = _cache.get(cache_key)
    if cached and now - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]

    spec: Optional[dict] = None
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            # drf-spectacular's SpectacularAPIView defaults to YAML for a
            # generic Accept header (FastAPI's own /openapi.json ignores this
            # and always returns JSON regardless, so it's harmless there).
            response = await client.get(
                url, headers={"Accept": "application/vnd.oai.openapi+json, application/json"}
            )
            response.raise_for_status()
            spec = response.json()
    except Exception as e:
        logger.warning("Could not fetch downstream OpenAPI spec from %s: %s", url, e)

    _cache[cache_key] = (now, spec)
    return spec


def _rewrite_schema_refs(node, rename: dict):
    """Recursively rewrite '#/components/schemas/X' refs using the rename map."""
    if isinstance(node, dict):
        if isinstance(node.get("$ref"), str):
            prefix = "#/components/schemas/"
            if node["$ref"].startswith(prefix):
                old_name = node["$ref"][len(prefix):]
                new_name = rename.get(old_name, old_name)
                node = {**node, "$ref": prefix + new_name}
        return {k: _rewrite_schema_refs(v, rename) for k, v in node.items()}
    if isinstance(node, list):
        return [_rewrite_schema_refs(item, rename) for item in node]
    return node


def _merge_schemas(base_spec: dict, downstream_schemas: dict, namespace: str) -> dict:
    """Copy downstream component schemas into base_spec under a namespaced
    name (to avoid collisions across services), returning the
    {old_name: new_name} rename map used to rewrite $refs."""
    rename = {name: f"{namespace}{name}" for name in downstream_schemas}
    base_spec.setdefault("components", {}).setdefault("schemas", {})
    for old_name, schema in downstream_schemas.items():
        base_spec["components"]["schemas"][rename[old_name]] = _rewrite_schema_refs(schema, rename)
    return rename


def _apply_examples(path: str, operations: dict) -> None:
    """Add this module's safe examples/defaults to a merged path item."""
    for method, op in operations.items():
        if not isinstance(op, dict):
            continue
        if (method, path) in _JOB_STARTERS:
            op["description"] = f"{_JOB_WARNING}\n\n{op.get('description', '')}".rstrip()
        example = _BODY_EXAMPLES.get((method, path))
        if example is not None:
            # A route whose downstream spec declares no body still takes JSON.
            request_body = op.setdefault(
                "requestBody", {"content": {"application/json": {"schema": {"type": "object"}}}}
            )
            for media in request_body.get("content", {}).values():
                media["example"] = example
        for param in op.get("parameters", []):
            key = (method, path, param.get("name"))
            if key in _PARAM_DEFAULTS:
                param.setdefault("schema", {})["default"] = _PARAM_DEFAULTS[key]


def _merge_paths(
    base_spec: dict,
    downstream_paths: dict,
    path_map: Callable[[str], Optional[str]],
    rename: dict,
    tag: str,
    op_id_prefix: str,
    description_banner: Optional[str] = None,
) -> bool:
    """path_map(old_path) -> new_path, or None to skip a path that isn't
    actually reachable through this proxy. Returns True if anything merged."""
    merged_any = False
    for old_path, path_item in downstream_paths.items():
        new_path = path_map(old_path)
        if new_path is None:
            continue
        rewritten = _rewrite_schema_refs(path_item, rename)
        for op in rewritten.values():
            if not isinstance(op, dict):
                continue
            op["tags"] = [tag]
            # The downstream service's own auth scheme is internal-only --
            # callers authenticate to ddp-api with its bearer token instead.
            op["security"] = [{"HTTPBearer": []}]
            if "operationId" in op:
                op["operationId"] = f"{op_id_prefix}{op['operationId']}"
            if description_banner:
                op["description"] = f"{description_banner}\n\n{op.get('description', '')}".rstrip()
        _apply_examples(new_path, rewritten)
        base_spec["paths"][new_path] = rewritten
        merged_any = True
    return merged_any


async def merge_ddp_sync(base_spec: dict, service_url: str) -> None:
    """Splice ddp-sync's real /sync/* and /trigger/* schemas into base_spec,
    replacing the generic /sync/{path} and /trigger/{path} catch-all entries."""
    spec = await _fetch_spec(f"{service_url}/openapi.json", "ddp_sync")
    if not spec:
        return

    rename = _merge_schemas(base_spec, spec.get("components", {}).get("schemas", {}), "DdpSync")
    api_prefix = "/ddp-sync/v1"

    def path_map(old_path: str) -> Optional[str]:
        if not old_path.startswith(api_prefix):
            return None
        rest = old_path[len(api_prefix):] or "/"
        if rest == "/sync" or rest.startswith("/sync/") or rest == "/trigger" or rest.startswith("/trigger/"):
            return rest
        return None

    merged = _merge_paths(
        base_spec, spec.get("paths", {}), path_map, rename, tag="ddp-sync", op_id_prefix="ddp_sync__"
    )
    if merged:
        base_spec["paths"].pop("/sync/{path}", None)
        base_spec["paths"].pop("/trigger/{path}", None)


async def merge_openstates(base_spec: dict, service_url: str) -> None:
    """Splice DDP's own self-hosted OpenStates api-v3 instance's real schemas
    into base_spec, replacing the generic /openstates/{path} catch-all entry.
    This is NOT the public openstates.org API -- it's DDP's own fork/data,
    which just happens to reuse api-v3's schema. That proxy has no path
    restriction, so every one of its routes is remounted under /openstates."""
    spec = await _fetch_spec(f"{service_url}/openapi.json", "openstates")
    if not spec:
        return

    rename = _merge_schemas(base_spec, spec.get("components", {}).get("schemas", {}), "OpenStatesV3")

    def path_map(old_path: str) -> Optional[str]:
        return f"/openstates{old_path}"

    merged = _merge_paths(
        base_spec,
        spec.get("paths", {}),
        path_map,
        rename,
        tag="ddp-openstates",
        op_id_prefix="openstates__",
        description_banner=(
            "**DDP's own self-hosted OpenStates instance — not the public openstates.org API.** "
            "Runs DDP's own scrapers against DDP's own database; reuses api-v3's schema/codebase only."
        ),
    )
    if merged:
        base_spec["paths"].pop("/openstates/{path}", None)


async def merge_broker(base_spec: dict, service_url: str) -> None:
    """Splice ddp-broker-py's real schemas into base_spec, replacing the
    generic /broker/{path} catch-all entry. Like openstates_proxy.py, this
    proxy has no path restriction, so every one of its routes is remounted
    under /broker. ddp-broker-py is Django + drf-spectacular (not FastAPI),
    so its schema lives at /api/schema/, not /openapi.json."""
    spec = await _fetch_spec(f"{service_url}/api/schema/", "broker")
    if not spec:
        return

    rename = _merge_schemas(base_spec, spec.get("components", {}).get("schemas", {}), "Broker")

    def path_map(old_path: str) -> Optional[str]:
        return f"/broker{old_path}"

    merged = _merge_paths(base_spec, spec.get("paths", {}), path_map, rename, tag="broker", op_id_prefix="broker__")
    if merged:
        base_spec["paths"].pop("/broker/{path}", None)
