"""Repeated tool-call loop detection."""

from __future__ import annotations

import hashlib
import json
from collections import Counter, deque
from collections.abc import Mapping
from typing import Any

from .failure import LoopDetectedError


class RepeatedToolDetector:
    def __init__(self, *, maximum_repeats: int = 3, window_size: int = 8) -> None:
        if maximum_repeats < 2:
            raise ValueError("maximum_repeats must be at least two")
        if window_size < maximum_repeats:
            raise ValueError("window_size must be at least maximum_repeats")
        self._maximum_repeats = maximum_repeats
        self._history: deque[str] = deque(maxlen=window_size)

    def record(self, tool_name: str, arguments: Mapping[str, Any]) -> None:
        if not tool_name.strip():
            raise ValueError("tool_name must not be blank")
        encoded = json.dumps(arguments, sort_keys=True, separators=(",", ":"), default=str)
        fingerprint = hashlib.sha256(f"{tool_name}:{encoded}".encode()).hexdigest()
        self._history.append(fingerprint)
        if Counter(self._history)[fingerprint] >= self._maximum_repeats:
            raise LoopDetectedError(f"repeated tool call detected: {tool_name}")

    def reset(self) -> None:
        self._history.clear()
