"""Turn off "Try it out" for write actions on the public /docs page (API-9).

public_openapi() marks every mutating operation `x-ddp-write` except the
read-scoped POSTs listed below; a small Swagger UI plugin hides the Try it out
button on marked operations. A route is blocked by default, so a new write
route is covered without being listed anywhere. This changes the docs page
only: auth, scopes and the API itself are untouched, and a caller can still
send any request directly.
"""

MUTATING = {"post", "put", "patch", "delete"}

# The public /docs page loads Swagger UI from this exact version, never a floating
# `@5`: the plugin below depends on Swagger UI internals, and a new 5.x release that
# changes them would bring every write button back with no error and no failing test.
# 5.33.1 is the version the API-9 browser check passed on (released 2026-10-01).
#
# To upgrade on purpose: change SWAGGER_UI_VERSION, run the app locally, open /docs,
# expand every operation (click each summary) and confirm that GET operations and the
# READ_ONLY_POSTS below have "Try it out" and every other POST/PUT/PATCH/DELETE has none.
# Only then merge. tests/test_docs_try_it_out.py fails if the page stops using an exact version.
SWAGGER_UI_VERSION = "5.33.1"
_SWAGGER_UI_CDN = f"https://cdn.jsdelivr.net/npm/swagger-ui-dist@{SWAGGER_UI_VERSION}"
SWAGGER_UI_JS_URL = f"{_SWAGGER_UI_CDN}/swagger-ui-bundle.js"
SWAGGER_UI_CSS_URL = f"{_SWAGGER_UI_CDN}/swagger-ui.css"

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
