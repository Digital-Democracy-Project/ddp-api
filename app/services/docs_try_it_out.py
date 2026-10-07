"""Turn off "Try it out" for write actions on the public /docs page (API-9).

public_openapi() marks every mutating operation `x-ddp-write` except the
read-scoped POSTs listed below; a small Swagger UI plugin hides the Try it out
button on marked operations. A route is blocked by default, so a new write
route is covered without being listed anywhere. This changes the docs page
only: auth, scopes and the API itself are untouched, and a caller can still
send any request directly.
"""

MUTATING = {"post", "put", "patch", "delete"}

# POST routes that only need a read key, so Try it out stays on for them.
# tests/test_docs_try_it_out.py checks each one against its real auth dependency.
READ_ONLY_POSTS: set[tuple[str, str]] = {
    ("post", "/get_tokens"),
    ("post", "/get_users"),
    ("post", "/get_events"),
    ("post", "/user_updates"),
    ("post", "/votebot/chat"),
    ("post", "/votebot/chat/stream"),
    ("post", "/webflow/check/org-missing-fields"),
    ("post", "/webflow/check/duplicates"),
}

_PLUGIN_JS = """const BlockWriteTryItOut = () => ({
        wrapComponents: {
            operation: (Original, system) => (props) => {
                const info = props.operation;
                const blocked = info && info.getIn && info.getIn(["op", "x-ddp-write"]) === true;
                return system.React.createElement(
                    Original, blocked ? Object.assign({}, props, {operation: info.set("allowTryItOut", false)}) : props);
            },
        },
    });
    """


def mark_write_operations(spec: dict) -> None:
    """Flag every mutating operation in `spec` that is not a read-only POST."""
    for path, item in spec["paths"].items():
        for method, op in item.items():
            if method in MUTATING and (method, path) not in READ_ONLY_POSTS:
                op["x-ddp-write"] = True


def with_write_block(html: str) -> str:
    """Add the plugin to FastAPI's Swagger UI page. Raises if the template changed."""
    start, presets = "const ui = SwaggerUIBundle({", "presets: ["
    if start not in html or presets not in html:
        raise RuntimeError("Swagger UI page template changed; update with_write_block()")
    html = html.replace(start, _PLUGIN_JS + start, 1)
    return html.replace(presets, "plugins: [BlockWriteTryItOut],\n    " + presets, 1)
