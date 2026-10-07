"""filter_paths splits one generated spec into public and admin documents (API-11)."""
from app.services.spec_filter import filter_paths, is_admin_path


def _spec():
    ref = lambda name: {"$ref": f"#/components/schemas/{name}"}
    return {
        "paths": {
            "/admin/keys": {"post": {"requestBody": {"content": {"application/json": {"schema": ref("KeyIn")}}}}},
            "/things": {"get": {"responses": {"200": {"content": {"application/json": {"schema": ref("Thing")}}}}}},
        },
        "components": {
            "schemas": {
                "KeyIn": {"properties": {"opts": ref("KeyOpts")}},
                "KeyOpts": {},
                "Thing": {"properties": {"part": ref("Part")}},
                "Part": {},
                "Unused": {},
            },
            "securitySchemes": {"HTTPBearer": {"type": "http"}},
        },
    }


def test_is_admin_path():
    assert is_admin_path("/admin") and is_admin_path("/admin/keys")
    assert not is_admin_path("/administration") and not is_admin_path("/voatz/users/{org_id}")


def test_public_view_drops_admin_paths_and_their_schemas():
    spec = _spec()
    filter_paths(spec, lambda p: not is_admin_path(p))
    assert list(spec["paths"]) == ["/things"]
    assert set(spec["components"]["schemas"]) == {"Thing", "Part"}  # nested ref kept, unused dropped
    assert "HTTPBearer" in spec["components"]["securitySchemes"]


def test_admin_view_keeps_only_admin_paths_and_nested_schemas():
    spec = _spec()
    filter_paths(spec, is_admin_path)
    assert list(spec["paths"]) == ["/admin/keys"]
    assert set(spec["components"]["schemas"]) == {"KeyIn", "KeyOpts"}
