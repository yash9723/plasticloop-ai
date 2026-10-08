"""Write the OpenAPI document used to generate frontend types.

    python -m app.scripts.export_openapi openapi.json
"""

import json
import sys
from pathlib import Path

from app.main import app


def main() -> None:
    doc = json.dumps(app.openapi(), indent=2, ensure_ascii=False)
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(doc + "\n", encoding="utf-8")
        print(f"wrote {sys.argv[1]}")
    else:
        print(doc)


if __name__ == "__main__":
    main()
