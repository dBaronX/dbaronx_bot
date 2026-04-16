from typing import Any, Dict


class SessionStore:
    def __init__(self) -> None:
        self._store: Dict[str, Dict[str, Any]] = {}

    def get(self, key: str) -> Dict[str, Any]:
        return self._store.setdefault(key, {})

    def set(self, key: str, value: Dict[str, Any]) -> None:
        self._store[key] = value

    def clear(self, key: str) -> None:
        self._store.pop(key, None)


session_store = SessionStore()