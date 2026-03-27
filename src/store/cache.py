"""File-backed JSON cache scaffold."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Any

from src.config import CACHE_DIR, CACHE_ENABLED


class JsonCache:
    """Simple JSON cache for deterministic artifacts."""

    def __init__(self, cache_dir: Path = CACHE_DIR) -> None:
        self.cache_dir = cache_dir

    def _path_for(self, key: str) -> Path:
        digest = sha256(key.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{digest}.json"

    def get(self, key: str) -> dict[str, Any] | None:
        """Return the cached JSON payload when present."""

        if not CACHE_ENABLED:
            return None

        path = self._path_for(key)
        if not path.exists():
            return None

        return json.loads(path.read_text(encoding="utf-8"))

    def set(self, key: str, payload: dict[str, Any]) -> None:
        """Persist a JSON payload under the supplied key."""

        if not CACHE_ENABLED:
            return

        self.cache_dir.mkdir(parents=True, exist_ok=True)
        path = self._path_for(key)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
