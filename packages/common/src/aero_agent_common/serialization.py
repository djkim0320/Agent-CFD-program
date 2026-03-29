from __future__ import annotations

import json
from typing import Any


def json_dumps(value: Any, *, indent: int = 2) -> str:
    return json.dumps(value, indent=indent, ensure_ascii=True, sort_keys=True, default=str)


def json_loads(text: str) -> Any:
    return json.loads(text)
