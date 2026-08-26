"""Regenerate schemas/route-ledger.schema.json from the pydantic models.

Run after any change to schema.py:  python3 scripts/gen_schema.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from carbonroute.schema import Ledger  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "schemas" / "route-ledger.schema.json"


def main() -> None:
    schema = Ledger.model_json_schema(by_alias=True, mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = "https://github.com/yktsnd/carbonroute/schemas/route-ledger.schema.json"
    schema["title"] = "carbonroute route ledger"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
