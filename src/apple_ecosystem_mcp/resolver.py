from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from .preferences import PreferencesStore, TargetPreference


def _normalize_text(value: str) -> str:
    return " ".join(value.strip().split()).casefold()


def _optional_normalized(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return _normalize_text(text)


@dataclass(frozen=True)
class ResolvedTarget:
    scope: str
    source: str
    item: dict[str, Any]
    query: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "scope": self.scope,
            "source": self.source,
            "query": self.query,
            "target": dict(self.item),
        }


class ResolverError(RuntimeError):
    code = "resolver_error"

    def __init__(self, scope: str, message: str, *, query: str | None = None) -> None:
        super().__init__(message)
        self.scope = scope
        self.query = query
        self.message = message

    def to_dict(self) -> dict[str, Any]:
        return {"error": self.code, "scope": self.scope, "query": self.query, "message": self.message}


class TargetNotFoundError(ResolverError):
    code = "target_not_found"


class AmbiguousTargetError(ResolverError):
    code = "target_ambiguous"

    def __init__(
        self,
        scope: str,
        query: str,
        candidates: Iterable[Mapping[str, Any]],
    ) -> None:
        self.candidates = [dict(candidate) for candidate in candidates]
        super().__init__(scope, f"Multiple {scope} targets matched {query!r}", query=query)

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data["candidates"] = self.candidates
        return data


class ReadOnlyTargetError(ResolverError):
    code = "target_read_only"

    def __init__(self, scope: str, item: Mapping[str, Any], *, query: str | None = None) -> None:
        self.item = dict(item)
        name = self.item.get("name", self.item.get("id", "target"))
        super().__init__(scope, f"{scope} target {name!r} is read-only", query=query)

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data["target"] = self.item
        return data


def resolve_target(
    query: str | None,
    inventory: Iterable[Mapping[str, Any]],
    *,
    scope: str,
    preferences: PreferencesStore | None = None,
    require_writable: bool = False,
    use_default: bool = True,
) -> ResolvedTarget:
    """Resolve a friendly target reference against inventory and preferences."""

    items = [dict(item) for item in inventory]
    stripped_query = query.strip() if query is not None else None

    if stripped_query:
        resolved = _resolve_with_query(stripped_query, items, scope=scope, preferences=preferences)
    elif use_default and preferences is not None:
        preference = preferences.get_default(scope)
        if preference is None:
            raise TargetNotFoundError(scope, f"No default configured for {scope}")
        resolved = ResolvedTarget(
            scope=scope,
            source="default",
            query=None,
            item=_resolve_preference_target(scope, preference, items),
        )
    else:
        raise TargetNotFoundError(scope, f"No {scope} target provided", query=query)

    if require_writable and resolved.item.get("writable") is False:
        raise ReadOnlyTargetError(scope, resolved.item, query=resolved.query)
    return resolved


def _resolve_with_query(
    query: str,
    items: list[dict[str, Any]],
    *,
    scope: str,
    preferences: PreferencesStore | None,
) -> ResolvedTarget:
    direct_match = _match_direct(query, items)
    if direct_match is not None:
        return ResolvedTarget(scope=scope, source=direct_match[0], query=query, item=direct_match[1])

    if preferences is not None:
        alias = preferences.get_alias(scope, query)
        if alias is not None:
            return ResolvedTarget(
                scope=scope,
                source="alias",
                query=query,
                item=_resolve_preference_target(scope, alias.target, items, query=query),
            )

    named_matches = _named_matches(query, items)
    if len(named_matches) == 1:
        return ResolvedTarget(scope=scope, source="name", query=query, item=named_matches[0])
    if len(named_matches) > 1:
        raise AmbiguousTargetError(scope, query, named_matches)

    partial_matches = _partial_matches(query, items)
    if len(partial_matches) == 1:
        return ResolvedTarget(scope=scope, source="partial", query=query, item=partial_matches[0])
    if len(partial_matches) > 1:
        raise AmbiguousTargetError(scope, query, partial_matches)

    raise TargetNotFoundError(scope, f"No {scope} target matched {query!r}", query=query)


def _resolve_preference_target(
    scope: str,
    preference: TargetPreference,
    items: list[dict[str, Any]],
    *,
    query: str | None = None,
) -> dict[str, Any]:
    by_id = [item for item in items if str(item.get("id")) == preference.id]
    if len(by_id) == 1:
        return by_id[0]

    preference_name = _normalize_text(preference.name)
    preference_account = _optional_normalized(preference.account_name)
    preference_path = _optional_normalized(preference.path)
    fallback_matches = []
    for item in items:
        name = _optional_normalized(item.get("name"))
        account = _optional_normalized(item.get("account_name"))
        path = _optional_normalized(item.get("path"))
        kind = _optional_normalized(item.get("kind"))
        if name != preference_name:
            continue
        if preference_account is not None and account != preference_account:
            continue
        if preference_path is not None and path != preference_path:
            continue
        if kind is not None and kind != _normalize_text(preference.kind):
            continue
        fallback_matches.append(item)

    if len(fallback_matches) == 1:
        return fallback_matches[0]
    if len(fallback_matches) > 1:
        raise AmbiguousTargetError(scope, query or preference.name, fallback_matches)
    raise TargetNotFoundError(scope, f"Stored {scope} preference is no longer available", query=query)


def _match_direct(query: str, items: list[dict[str, Any]]) -> tuple[str, dict[str, Any]] | None:
    by_id = [item for item in items if str(item.get("id")) == query]
    if len(by_id) == 1:
        return ("id", by_id[0])

    by_path = [item for item in items if item.get("path") == query]
    if len(by_path) == 1:
        return ("path", by_path[0])

    normalized_query = _normalize_text(query)
    path_matches = [item for item in items if _optional_normalized(item.get("path")) == normalized_query]
    if len(path_matches) == 1:
        return ("path", path_matches[0])

    return None


def _named_matches(query: str, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized_query = _normalize_text(query)
    matches = []
    for item in items:
        if _optional_normalized(item.get("name")) == normalized_query:
            matches.append(item)
            continue

        account = _optional_normalized(item.get("account_name"))
        name = _optional_normalized(item.get("name"))
        if account and name:
            for combined in (
                f"{account}/{name}",
                f"{account}:{name}",
                f"{account} {name}",
            ):
                if combined == normalized_query:
                    matches.append(item)
                    break
    return matches


def _partial_matches(query: str, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized_query = _normalize_text(query)
    matches = []
    for item in items:
        fields = [
            _optional_normalized(item.get("name")),
            _optional_normalized(item.get("path")),
            _optional_normalized(item.get("account_name")),
        ]
        if any(field is not None and normalized_query in field for field in fields):
            matches.append(item)
    return matches
