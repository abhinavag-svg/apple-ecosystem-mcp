from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

APP_NAME = "apple-ecosystem-mcp"
SCHEMA_VERSION = 1


class PreferencesError(RuntimeError):
    """Base class for preference storage errors."""


class PreferencesReadOnlyError(PreferencesError):
    """Raised when preferences cannot be written to local storage."""


def get_preferences_path() -> Path:
    """Return the local preferences file path outside the repo."""
    override = os.environ.get("APPLE_ECOSYSTEM_MCP_CONFIG_DIR")
    if override:
        return Path(override).expanduser() / "preferences.json"

    home = Path.home()
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
    elif os.name == "posix" and sys_platform() == "darwin":
        base = home / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", home / ".config"))

    return base / APP_NAME / "preferences.json"


def sys_platform() -> str:
    return os.environ.get("APPLE_ECOSYSTEM_MCP_PLATFORM", os.sys.platform)


def _normalize_key(value: str) -> str:
    normalized = " ".join(value.strip().split()).casefold()
    if not normalized:
        raise ValueError("key must not be empty")
    return normalized


@dataclass(frozen=True)
class TargetPreference:
    """Stable target reference stored in local preferences."""

    id: str
    name: str
    kind: str
    account_name: str | None = None
    path: str | None = None

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> TargetPreference:
        return cls(
            id=str(data["id"]),
            name=str(data["name"]),
            kind=str(data["kind"]),
            account_name=_optional_string(data.get("account_name")),
            path=_optional_string(data.get("path")),
        )

    def to_dict(self) -> dict[str, str | None]:
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "account_name": self.account_name,
            "path": self.path,
        }


@dataclass(frozen=True)
class AliasPreference:
    """Alias record stored under a normalized alias key."""

    alias: str
    target: TargetPreference

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> AliasPreference:
        return cls(
            alias=str(data["alias"]),
            target=TargetPreference.from_mapping(data["target"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return {"alias": self.alias, "target": self.target.to_dict()}


@dataclass
class PreferencesDocument:
    version: int = SCHEMA_VERSION
    defaults: dict[str, TargetPreference] = field(default_factory=dict)
    aliases: dict[str, dict[str, AliasPreference]] = field(default_factory=dict)

    @classmethod
    def empty(cls) -> PreferencesDocument:
        return cls()

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> PreferencesDocument:
        version = int(data.get("version", SCHEMA_VERSION))
        if version != SCHEMA_VERSION:
            raise PreferencesError(
                f"Unsupported preferences schema version {version}; expected {SCHEMA_VERSION}"
            )

        defaults = {
            str(scope): TargetPreference.from_mapping(target)
            for scope, target in dict(data.get("defaults", {})).items()
        }
        aliases: dict[str, dict[str, AliasPreference]] = {}
        for scope, records in dict(data.get("aliases", {})).items():
            aliases[str(scope)] = {
                str(alias_key): AliasPreference.from_mapping(record)
                for alias_key, record in dict(records).items()
            }

        return cls(version=version, defaults=defaults, aliases=aliases)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "defaults": {scope: target.to_dict() for scope, target in self.defaults.items()},
            "aliases": {
                scope: {alias_key: record.to_dict() for alias_key, record in records.items()}
                for scope, records in self.aliases.items()
            },
        }


class PreferencesStore:
    """Versioned JSON preferences persisted to local user config storage."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path).expanduser() if path is not None else get_preferences_path()

    def load(self) -> PreferencesDocument:
        if not self.path.exists():
            return PreferencesDocument.empty()

        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise PreferencesError(f"Could not read preferences: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise PreferencesError(f"Could not parse preferences JSON: {exc}") from exc

        if not isinstance(raw, dict):
            raise PreferencesError("Preferences file must contain a JSON object")
        return PreferencesDocument.from_dict(raw)

    def save(self, document: PreferencesDocument) -> PreferencesDocument:
        self._ensure_parent_dir()
        payload = json.dumps(document.to_dict(), indent=2, sort_keys=True) + "\n"
        try:
            self.path.write_text(payload, encoding="utf-8")
        except OSError as exc:
            raise PreferencesReadOnlyError(f"Could not write preferences: {exc}") from exc
        return document

    def get_default(self, scope: str) -> TargetPreference | None:
        return self.load().defaults.get(scope)

    def set_default(self, scope: str, target: Mapping[str, Any] | TargetPreference) -> TargetPreference:
        document = self.load()
        preference = _coerce_target(target)
        document.defaults[scope] = preference
        self.save(document)
        return preference

    def clear_default(self, scope: str) -> bool:
        document = self.load()
        existed = scope in document.defaults
        document.defaults.pop(scope, None)
        if existed:
            self.save(document)
        return existed

    def list_aliases(self, scope: str) -> dict[str, AliasPreference]:
        return dict(self.load().aliases.get(scope, {}))

    def get_alias(self, scope: str, alias: str) -> AliasPreference | None:
        return self.load().aliases.get(scope, {}).get(_normalize_key(alias))

    def add_alias(
        self,
        scope: str,
        alias: str,
        target: Mapping[str, Any] | TargetPreference,
    ) -> AliasPreference:
        document = self.load()
        normalized = _normalize_key(alias)
        record = AliasPreference(alias=alias.strip(), target=_coerce_target(target))
        document.aliases.setdefault(scope, {})[normalized] = record
        self.save(document)
        return record

    def remove_alias(self, scope: str, alias: str) -> bool:
        document = self.load()
        records = document.aliases.get(scope, {})
        existed = _normalize_key(alias) in records
        records.pop(_normalize_key(alias), None)
        if not records and scope in document.aliases:
            document.aliases.pop(scope, None)
        if existed:
            self.save(document)
        return existed

    def _ensure_parent_dir(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise PreferencesReadOnlyError(f"Could not create preferences directory: {exc}") from exc


def _coerce_target(target: Mapping[str, Any] | TargetPreference) -> TargetPreference:
    if isinstance(target, TargetPreference):
        return target
    return TargetPreference.from_mapping(target)


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)

