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


def _merge_paths(
    base_spec: dict,
    downstream_paths: dict,
    path_map: Callable[[str], Optional[str]],
    rename: dict,
    tag: str,
    op_id_prefix: str,
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
    """Splice api-v3's real schemas into base_spec, replacing the generic
    /openstates/{path} catch-all entry. api-v3's proxy has no path
    restriction, so every one of its routes is remounted under /openstates."""
    spec = await _fetch_spec(f"{service_url}/openapi.json", "openstates")
    if not spec:
        return

    rename = _merge_schemas(base_spec, spec.get("components", {}).get("schemas", {}), "OpenStatesV3")

    def path_map(old_path: str) -> Optional[str]:
        return f"/openstates{old_path}"

    merged = _merge_paths(
        base_spec, spec.get("paths", {}), path_map, rename, tag="openstates", op_id_prefix="openstates__"
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
