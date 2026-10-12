"""待处理列表的记忆：列表一变就悄悄存一份，正常关闭时清掉。

只有在崩溃或者被强杀之后，下次打开才会看到上次剩下的东西。
"""

from __future__ import annotations

import json

from ..settings import APP_DIR

SESSION_PATH = APP_DIR / "session.json"


def save(payload: dict) -> None:
    try:
        SESSION_PATH.parent.mkdir(parents=True, exist_ok=True)
        SESSION_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def load() -> dict:
    try:
        data = json.loads(SESSION_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def clear() -> None:
    try:
        SESSION_PATH.unlink()
    except OSError:
        pass
