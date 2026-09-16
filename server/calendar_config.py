"""Layout configuration loading and persistence.

The layout of the rendered image is fully described by a YAML document. The
shipped defaults live in ``config.default.yaml``; the web ``/config`` page edits
a separate user copy so the defaults are never destroyed.
"""

from __future__ import annotations

import copy
import os
import threading
from pathlib import Path

import yaml

SERVER_DIR = Path(__file__).resolve().parent

DEFAULT_CONFIG_PATH = SERVER_DIR / "config.default.yaml"


def _config_path() -> Path:
    override = os.environ.get("EINK_CONFIG_PATH")
    if override:
        return Path(override)
    return SERVER_DIR / "config" / "config.yaml"


class ConfigStore:
    """Reads and writes the layout YAML with an in-process cache."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path else _config_path()
        self._lock = threading.Lock()
        self._cache: dict | None = None
        self._stamp: tuple[int, int] | None = None

    def defaults(self) -> dict:
        with DEFAULT_CONFIG_PATH.open("r", encoding="utf-8") as handle:
            return yaml.safe_load(handle)

    def text(self) -> str:
        """The stored document as the admin wrote it, or the shipped defaults.

        Returning the file verbatim rather than a re-serialised copy keeps any
        comments and the admin's key order intact between edits.
        """
        if self.path.exists():
            return self.path.read_text(encoding="utf-8")
        return yaml.safe_dump(
            self.defaults(), sort_keys=False, default_flow_style=False
        )

    def _current_stamp(self) -> tuple[int, int] | None:
        """Identify the file on disk, so edits made outside the app are seen."""
        try:
            stat = self.path.stat()
        except FileNotFoundError:
            return None
        return (stat.st_mtime_ns, stat.st_size)

    def load(self, reload: bool = False) -> dict:
        """Return the effective configuration.

        Falls back to the shipped defaults when no user copy exists. The file is
        re-read when it has changed underneath, so editing it (or deleting it to
        reset) takes effect without a restart.
        """
        with self._lock:
            stamp = self._current_stamp()
            if self._cache is not None and not reload and stamp == self._stamp:
                return copy.deepcopy(self._cache)

            if self.path.exists():
                with self.path.open("r", encoding="utf-8") as handle:
                    loaded = yaml.safe_load(handle) or {}
                effective = _merge_sections(self.defaults(), loaded)
            else:
                effective = self.defaults()

            self._cache = effective
            self._stamp = stamp
            return copy.deepcopy(effective)

    def save(self, document: dict, text: str | None = None) -> None:
        """Persist a configuration document.

        ``text`` is written verbatim when given, so comments and key order the
        admin typed survive the round trip; otherwise the document is
        serialised. Either way, ``load()`` sees the section-merged result.
        """
        effective = _merge_sections(self.defaults(), document)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".yaml.tmp")
        if text is not None:
            tmp.write_text(text, encoding="utf-8")
        else:
            with tmp.open("w", encoding="utf-8") as handle:
                yaml.safe_dump(
                    effective, handle, sort_keys=False, default_flow_style=False
                )
        tmp.replace(self.path)
        with self._lock:
            self._cache = effective
            self._stamp = self._current_stamp()

    def reset(self) -> dict:
        """Delete the user copy and return the shipped defaults."""
        with self._lock:
            if self.path.exists():
                self.path.unlink()
            self._cache = None
            self._stamp = None
        return self.load()


def _merge_sections(base: dict, override: dict) -> dict:
    """Merge one level deep only: each top-level section replaces ``base`` whole.

    Merging all the way down a section would make it impossible to remove a key
    from it: the entry deleted in the admin's copy would simply reappear from the
    defaults, so a line commented out on the /config page would silently come
    back. One level is enough for the shipped defaults to supply sections a
    partial document omits, without turning every section into an un-deletable
    union of its defaults and its overrides.
    """
    result = copy.deepcopy(base)
    for key, value in (override or {}).items():
        result[key] = copy.deepcopy(value)
    return result


def resolve_font_path(relative: str) -> str:
    """Resolve a font path from the config against the server directory."""
    candidate = Path(relative)
    if candidate.is_absolute():
        return str(candidate)
    return str(SERVER_DIR / relative)
