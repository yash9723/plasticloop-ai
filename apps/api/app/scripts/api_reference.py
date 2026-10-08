"""Generates docs/API_REFERENCE.md from the live OpenAPI document, so the reference cannot drift from the code.

    docker compose exec -T api python -m app.scripts.api_reference > docs/API_REFERENCE.md
"""

from collections import defaultdict

from app.main import app

INTRO = """# API reference

Generated from the running application's OpenAPI document (`python -m app.scripts.api_reference`). The interactive version
with request/response schemas is served at **`/docs`** (Swagger UI) and the raw schema at **`/api/v1/openapi.json`**.

* Base path: `/api/v1`. Browsers reach it through the web app (`/api/v1/*` is proxied), so everything is same-origin.
* Auth: `POST /api/v1/auth/login` returns a 15-minute access token (send `Authorization: Bearer <token>`) and sets an httpOnly
  refresh cookie; `POST /api/v1/auth/refresh` (with header `X-Requested-With: plasticloop`) rotates it.
* Devices: `Authorization: Device <device_id>:<device_key>` on `POST /api/v1/devices/telemetry` only.
* Errors: always `{"error": {"code", "message", "details", "request_id"}}`; cross-tenant ids return 404, missing roles 403.
* Lists: `page`, `page_size` (≤ 200), `sort` (field, `-` prefix for descending) → `{"items", "total", "page", "page_size"}`.
* Weights are kilograms (3 decimals), money is integer paise, timestamps are ISO-8601 with offset.
"""


def main() -> None:
    spec = app.openapi()
    by_tag: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    for path, ops in spec["paths"].items():
        for method, op in ops.items():
            tag = (op.get("tags") or ["other"])[0]
            by_tag[tag].append((method.upper(), path, (op.get("summary") or "").replace("|", "\\|")))
    lines = [INTRO, f"{sum(len(v) for v in by_tag.values())} operations in {len(by_tag)} groups.\n"]
    for tag in sorted(by_tag):
        lines.append(f"\n## {tag}\n\n| Method | Path | Summary |\n|---|---|---|")
        for method, path, summary in sorted(by_tag[tag], key=lambda x: (x[1], x[0])):
            lines.append(f"| `{method}` | `{path}` | {summary} |")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
