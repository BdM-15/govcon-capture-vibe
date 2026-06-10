"""Helpers for stripping streamed or complete <think> reasoning blocks."""

from __future__ import annotations

import re

_THINK_BLOCK = re.compile(r"<think>.*?</think>\s*", re.DOTALL | re.IGNORECASE)
_UNCLOSED_THINK = re.compile(r"<think>.*$", re.DOTALL | re.IGNORECASE)


def strip_think(text: str) -> str:
    """Remove <think>...</think> blocks from complete string."""
    if not text or "<think>" not in text.lower():
        return text
    cleaned = _THINK_BLOCK.sub("", text)
    cleaned = _UNCLOSED_THINK.sub("", cleaned)
    return cleaned.lstrip()


class ThinkStripper:
    """Stateful streaming filter that strips <think>...</think> blocks."""

    OPEN = "<think>"
    CLOSE = "</think>"
    _HOLD = len(CLOSE)

    def __init__(self) -> None:
        self._buf = ""
        self._in_think = False

    @property
    def in_think(self) -> bool:
        """True while buffering a <think>...</think> block."""
        return self._in_think

    def feed(self, chunk: str) -> str:
        """Consume one chunk, return safe-to-emit text outside <think>."""
        if not chunk:
            return ""
        self._buf += chunk
        out: list[str] = []
        while True:
            if self._in_think:
                idx = self._buf.find(self.CLOSE)
                if idx == -1:
                    if len(self._buf) > self._HOLD:
                        self._buf = self._buf[-self._HOLD:]
                    return "".join(out)
                self._buf = self._buf[idx + len(self.CLOSE) :].lstrip()
                self._in_think = False
                continue

            idx = self._buf.find(self.OPEN)
            if idx == -1:
                if len(self._buf) > self._HOLD:
                    out.append(self._buf[: -self._HOLD])
                    self._buf = self._buf[-self._HOLD :]
                return "".join(out)
            if idx > 0:
                out.append(self._buf[:idx])
            self._buf = self._buf[idx + len(self.OPEN) :]
            self._in_think = True

    def flush(self) -> str:
        """Drain remaining buffered text at end of stream."""
        if self._in_think:
            self._buf = ""
            return ""
        out = self._buf
        self._buf = ""
        return out


__all__ = ["ThinkStripper", "strip_think"]