"""/docs examples are for non-destructive testing only (API-7).

Every mutating operation with a JSON body must ship an example, and no example
may switch dry-run off or a destructive flag on. Built from ddp-api's own
routes only, so it needs no downstream service.
"""
import pytest
from fastapi.openapi.utils import get_openapi

from app.main import app

MUTATING = {"post", "put", "patch", "delete"}
# Flags whose True value makes a request destructive or outward-facing.
DESTRUCTIVE_FLAGS = {
    "delete_anomalous",
    "migrate_content",
    "force_remove_references",
    "send_zapier_hooks",
}


def _spec():
    return get_openapi(title="t", version="0", routes=app.routes)


def _body_examples(spec, operation):
    """Return (has_json_body, examples) for an operation."""
    content = (operation.get("requestBody") or {}).get("content", {}).get("application/json")
    if not content:
        return False, []
    schema = content["schema"]
    if "$ref" in schema:
        schema = spec["components"]["schemas"][schema["$ref"].rsplit("/", 1)[-1]]
    examples = list(schema.get("examples") or []) + list(content.get("examples", {}).values())
    if "example" in schema:
        examples.append(schema["example"])
    return True, examples


def _mutating_operations():
    spec = _spec()
    for path, item in spec["paths"].items():
        for method, operation in item.items():
            if method in MUTATING:
                yield spec, f"{method.upper()} {path}", operation


@pytest.mark.parametrize("spec,label,operation", list(_mutating_operations()), ids=lambda v: v if isinstance(v, str) else "")
def test_json_body_has_safe_example(spec, label, operation):
    has_body, examples = _body_examples(spec, operation)
    if not has_body:
        pytest.skip("no JSON body")
    assert examples, f"{label} has a JSON body but no example"
    for example in examples:
        assert example.get("dry_run", True) is True, f"{label} example turns dry_run off"
        for flag in DESTRUCTIVE_FLAGS:
            assert example.get(flag) is not True, f"{label} example sets {flag}=true"
