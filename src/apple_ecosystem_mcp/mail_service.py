from __future__ import annotations

import json
import logging
import os
from typing import Any, Callable

from . import __build_marker__, __version__
from .bridge import run_applescript
from .mail_store import (
    MailSearchQuery,
    MailStoreUnavailable,
    get_mail_snapshot_state,
    list_mail_store_mailboxes,
    refresh_mail_snapshot,
    search_mail_store,
)

MAIL_SEARCH_DEFAULT = 20
MAIL_SEARCH_MAX = 100
MAIL_PREVIEW_CHARS = 200
MAIL_PROVIDER_AUTO = "auto"
MAIL_PROVIDER_LOCAL = "local"
MAIL_PROVIDER_APPLESCRIPT = "applescript"
MAIL_RECENT_DEFAULT_FIELDS = ("subject", "sender")
_logger = logging.getLogger("apple_ecosystem_mcp.bridge")


def _parse_json(raw: str) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Malformed AppleScript JSON output: {exc.msg}") from exc


def _nn(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str) and (value == "" or value == "missing value"):
        return None
    return value


def _mail_provider_mode(filters: dict) -> str:
    value = filters.get("provider")
    if value is None:
        value = filters.get("mail_provider")
    if value is None:
        value = os.environ.get("APPLE_ECOSYSTEM_MCP_MAIL_PROVIDER", MAIL_PROVIDER_AUTO)
    mode = str(value).strip().lower()
    if mode in {"store", "sqlite", "native", "local"}:
        return MAIL_PROVIDER_LOCAL
    if mode in {"legacy", "script", "applescript"}:
        return MAIL_PROVIDER_APPLESCRIPT
    return MAIL_PROVIDER_AUTO


def _can_search_mail_store(
    query: str,
    search_fields: list[str],
    filters: dict,
    *,
    since: str | None,
    before: str | None,
    mailbox_id: str | None,
) -> bool:
    if "body" in search_fields:
        return False
    supported_filters = {
        "from_addr",
        "to_addr",
        "cc_addr",
        "unread",
        "flagged",
        "has_attachments",
        "account_name",
        "mailbox_ids",
        "provider",
        "mail_provider",
    }
    if any(key not in supported_filters for key in filters):
        return False
    effective_filters = [key for key in filters if key not in {"provider", "mail_provider"}]
    return bool(query or effective_filters or since or before or mailbox_id)


def _search_with_mail_store(
    *,
    query: str,
    mailbox_id: str | None,
    limit: int,
    since: str | None,
    before: str | None,
    search_fields: list[str],
    filters: dict,
    db_path: Any = None,
) -> list[dict[str, Any]]:
    mailbox_ids = filters.get("mailbox_ids") or []
    if not isinstance(mailbox_ids, list):
        mailbox_ids = []
    search = MailSearchQuery(
        query=query,
        limit=limit,
        since=since,
        before=before,
        mailbox_id=mailbox_id,
        mailbox_ids=tuple(str(item) for item in mailbox_ids),
        search_subject="subject" in search_fields,
        search_sender="sender" in search_fields,
        unread=filters.get("unread") if isinstance(filters.get("unread"), bool) else None,
        flagged=filters.get("flagged") if isinstance(filters.get("flagged"), bool) else None,
        has_attachments=(
            filters.get("has_attachments")
            if isinstance(filters.get("has_attachments"), bool)
            else None
        ),
        from_addr=filters.get("from_addr") or None,
        to_addr=filters.get("to_addr") or None,
        cc_addr=filters.get("cc_addr") or None,
    )
    try:
        return search_mail_store(search, db_path=db_path)
    except TypeError:
        if db_path is None:
            return search_mail_store(search)
        raise


def _list_store_mailboxes(*, db_path: Any = None) -> list[dict[str, Any]]:
    try:
        return list_mail_store_mailboxes(db_path=db_path)
    except TypeError:
        if db_path is None:
            return list_mail_store_mailboxes()
        raise


def _mailbox_inventory(
    mailbox_inventory_fn: Callable[[], list[dict]] | None,
) -> list[dict[str, Any]]:
    if mailbox_inventory_fn is None:
        return []
    try:
        rows = mailbox_inventory_fn()
    except RuntimeError:
        return []
    return [row for row in rows if isinstance(row, dict)]


def _is_recency_style_search(query: str, filters: dict) -> bool:
    if query.strip():
        return False
    mailbox_ids = filters.get("mailbox_ids")
    return not mailbox_ids or isinstance(mailbox_ids, list)


def _group_mailboxes_by_account(
    inventory: list[dict[str, Any]],
    *,
    account_name: str | None = None,
    inbox_only: bool,
) -> list[tuple[str, list[dict[str, Any]]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in inventory:
        account = _nn(item.get("account_name"))
        path = _nn(item.get("path"))
        if not account or not path:
            continue
        if account_name and str(account) != account_name:
            continue
        grouped.setdefault(str(account), []).append(item)

    plans: list[tuple[str, list[dict[str, Any]]]] = []
    for account, items in grouped.items():
        candidates = items
        if inbox_only:
            inboxes = [item for item in items if item.get("default_candidate")]
            if inboxes:
                candidates = inboxes
        plans.append((account, candidates))
    return plans


def _mail_store_mailboxes_by_account(
    inventory: list[dict[str, Any]],
    *,
    db_path: Any = None,
) -> dict[str, list[dict[str, Any]]]:
    try:
        store_mailboxes = _list_store_mailboxes(db_path=db_path)
    except MailStoreUnavailable:
        return {}

    inventory_paths: dict[str, set[str]] = {}
    for account, items in _group_mailboxes_by_account(inventory, inbox_only=False):
        inventory_paths[account] = {str(item.get("path")) for item in items if item.get("path")}

    token_groups: dict[str, list[dict[str, Any]]] = {}
    for item in store_mailboxes:
        token = _nn(item.get("account_token"))
        path = _nn(item.get("mailbox_path"))
        if not token or not path:
            continue
        token_groups.setdefault(str(token), []).append(item)

    matched: dict[str, list[dict[str, Any]]] = {}
    for rows in token_groups.values():
        row_paths = {str(item.get("mailbox_path")) for item in rows if item.get("mailbox_path")}
        best_account: str | None = None
        best_score = 0
        tie = False
        for account, paths in inventory_paths.items():
            score = len(row_paths & paths)
            if score > best_score:
                best_account = account
                best_score = score
                tie = False
            elif score and score == best_score:
                tie = True
        if best_account and best_score > 0 and not tie:
            matched.setdefault(best_account, []).extend(rows)
    return matched


def _infer_store_account_label(rows: list[dict[str, Any]]) -> str | None:
    if not rows:
        return None
    label = _nn(rows[0].get("account_name"))
    if label:
        return str(label)
    token = str(rows[0].get("account_token") or "")
    if token.startswith("local://"):
        return None
    return token or None


def _store_only_mailboxes_by_account(*, db_path: Any = None) -> dict[str, list[dict[str, Any]]]:
    try:
        store_mailboxes = _list_store_mailboxes(db_path=db_path)
    except MailStoreUnavailable:
        return {}

    token_groups: dict[str, list[dict[str, Any]]] = {}
    for item in store_mailboxes:
        token = _nn(item.get("account_token"))
        if not token:
            continue
        token_groups.setdefault(str(token), []).append(item)

    matched: dict[str, list[dict[str, Any]]] = {}
    unnamed = 1
    for rows in token_groups.values():
        label = _infer_store_account_label(rows)
        if label is None:
            continue
        if label in matched:
            label = f"{label} {unnamed}"
            unnamed += 1
        matched[label] = rows
    return matched


def _looks_like_store_mailbox_id(value: Any) -> bool:
    text = _nn(value)
    if not text:
        return False
    return "://" in str(text)


def _resolve_scoped_store_mailbox_ids(
    mailbox_values: list[Any],
    *,
    scoped_account: str | None,
    inventory: list[dict[str, Any]],
    db_path: Any = None,
) -> tuple[list[str], str | None]:
    raw_values = [str(item) for item in mailbox_values if _nn(item)]
    if not raw_values:
        return [], scoped_account

    if all(_looks_like_store_mailbox_id(value) for value in raw_values):
        return raw_values, scoped_account

    store_groups = _mail_store_mailboxes_by_account(inventory, db_path=db_path)
    if not store_groups:
        store_groups = _store_only_mailboxes_by_account(db_path=db_path)

    candidate_accounts = [scoped_account] if scoped_account else list(store_groups.keys())
    normalized_inputs = {value.casefold() for value in raw_values}
    matched_ids: list[str] = []
    matched_account: str | None = scoped_account

    for account in candidate_accounts:
        store_mailboxes = store_groups.get(account) or []
        account_matches = [
            str(item.get("mailbox_url"))
            for item in store_mailboxes
            if item.get("mailbox_url")
            and (
                str(item.get("mailbox_url")).casefold() in normalized_inputs
                or str(item.get("mailbox_path") or "").casefold() in normalized_inputs
            )
        ]
        if account_matches:
            matched_ids.extend(account_matches)
            if matched_account is None:
                matched_account = account
            if scoped_account:
                break

    if matched_ids:
        deduped: list[str] = []
        seen: set[str] = set()
        for value in matched_ids:
            if value in seen:
                continue
            seen.add(value)
            deduped.append(value)
        return deduped, matched_account

    return raw_values, scoped_account


def _sort_mail_results(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda item: str(item.get("date") or ""), reverse=True)


def _mailbox_id_groups_for_applescript_recent(
    inventory: list[dict[str, Any]],
    *,
    account_name: str | None = None,
) -> list[tuple[str, list[str]]]:
    grouped = _group_mailboxes_by_account(
        inventory,
        account_name=account_name,
        inbox_only=True,
    )
    plans: list[tuple[str, list[str]]] = []
    for account, items in grouped:
        mailbox_ids = [str(item.get("id")) for item in items if item.get("id")]
        if mailbox_ids:
            plans.append((account, mailbox_ids))
    return plans


def _search_mail_store_scoped(
    *,
    query: str,
    mailbox_id: str | None,
    limit: int,
    since: str | None,
    before: str | None,
    search_fields: list[str],
    filters: dict,
    mailbox_inventory_fn: Callable[[], list[dict]] | None,
    db_path: Any = None,
) -> list[dict[str, Any]]:
    scoped_account = filters.get("account_name")
    if not scoped_account and not _is_recency_style_search(query, filters):
        return _search_with_mail_store(
            query=query,
            mailbox_id=mailbox_id,
            limit=limit,
            since=since,
            before=before,
            search_fields=search_fields,
            filters=filters,
            db_path=db_path,
        )

    inventory = _mailbox_inventory(mailbox_inventory_fn)
    explicit_mailbox_ids = filters.get("mailbox_ids")
    if mailbox_id or explicit_mailbox_ids:
        scoped_filters = dict(filters)
        resolved_ids, resolved_account = _resolve_scoped_store_mailbox_ids(
            list(explicit_mailbox_ids) if isinstance(explicit_mailbox_ids, list) else [],
            scoped_account=scoped_account,
            inventory=inventory,
            db_path=db_path,
        )
        if resolved_ids:
            scoped_filters["mailbox_ids"] = resolved_ids
        elif "mailbox_ids" in scoped_filters and explicit_mailbox_ids is not None:
            scoped_filters["mailbox_ids"] = list(explicit_mailbox_ids)
        if resolved_account:
            scoped_filters["account_name"] = resolved_account
        rows = _search_with_mail_store(
            query=query,
            mailbox_id=mailbox_id,
            limit=limit,
            since=since,
            before=before,
            search_fields=search_fields,
            filters=scoped_filters,
            db_path=db_path,
        )
        if resolved_account:
            for row in rows:
                if isinstance(row, dict) and not row.get("account_name"):
                    row["account_name"] = resolved_account
        return rows

    inbox_only = _is_recency_style_search(query, filters)
    inventory_groups: dict[str, list[dict[str, Any]]] = {}
    store_groups: dict[str, list[dict[str, Any]]] = {}
    if inventory:
        inventory_groups = dict(
            _group_mailboxes_by_account(
                inventory,
                account_name=scoped_account,
                inbox_only=False,
            )
        )
        store_groups = _mail_store_mailboxes_by_account(inventory, db_path=db_path)
    if not store_groups:
        store_groups = _store_only_mailboxes_by_account(db_path=db_path)
    account_names = [scoped_account] if scoped_account else list(store_groups.keys())
    if scoped_account and scoped_account not in store_groups:
        raise MailStoreUnavailable(
            "mail_account_scope_unavailable",
            "Mail account scope could not be verified from local Mail account metadata",
        )
    if not account_names:
        return _search_with_mail_store(
            query=query,
            mailbox_id=mailbox_id,
            limit=limit,
            since=since,
            before=before,
            search_fields=search_fields,
            filters=filters,
            db_path=db_path,
        )

    collected: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    per_group_limit = limit
    if len(account_names) > 1:
        per_group_limit = max(limit, 10)

    base_filters = dict(filters)
    base_filters.pop("account_name", None)
    for account in account_names:
        store_mailboxes = store_groups.get(account) or []
        inventory_mailboxes = inventory_groups.get(account) or []
        if not store_mailboxes:
            continue
        if inbox_only:
            default_paths = {
                str(item.get("path"))
                for item in inventory_mailboxes
                if item.get("default_candidate") and item.get("path")
            }
            if not default_paths:
                default_paths = {
                    str(item.get("mailbox_path"))
                    for item in store_mailboxes
                    if str(item.get("mailbox_path") or "").casefold() == "inbox"
                }
            if default_paths:
                scoped_store_mailboxes = [
                    item for item in store_mailboxes if str(item.get("mailbox_path")) in default_paths
                ]
            else:
                scoped_store_mailboxes = store_mailboxes
        else:
            scoped_store_mailboxes = store_mailboxes
        if not scoped_store_mailboxes:
            continue
        scoped_filters = dict(base_filters)
        scoped_filters["mailbox_ids"] = [
            str(item.get("mailbox_url"))
            for item in scoped_store_mailboxes
            if item.get("mailbox_url")
        ]
        rows = _search_with_mail_store(
            query=query,
            mailbox_id=None,
            limit=per_group_limit,
            since=since,
            before=before,
            search_fields=search_fields,
            filters=scoped_filters,
            db_path=db_path,
        )
        for row in rows:
            if not isinstance(row, dict):
                continue
            row.setdefault("account_name", account)
            if not row.get("account_name"):
                row["account_name"] = account
            key = (str(row.get("id") or ""), str(row.get("internal_id") or ""))
            if key in seen:
                continue
            seen.add(key)
            collected.append(row)
    if not collected:
        return _search_with_mail_store(
            query=query,
            mailbox_id=mailbox_id,
            limit=limit,
            since=since,
            before=before,
            search_fields=search_fields,
            filters=filters,
            db_path=db_path,
        )
    return _sort_mail_results(collected)[:limit]


def _search_mail_store_with_snapshot_fallback(
    *,
    query: str,
    mailbox_id: str | None,
    limit: int,
    since: str | None,
    before: str | None,
    search_fields: list[str],
    filters: dict,
    mailbox_inventory_fn: Callable[[], list[dict]] | None,
) -> list[dict[str, Any]]:
    try:
        data = _search_mail_store_scoped(
            query=query,
            mailbox_id=mailbox_id,
            limit=limit,
            since=since,
            before=before,
            search_fields=search_fields,
            filters=filters,
            mailbox_inventory_fn=mailbox_inventory_fn,
        )
        _logger.debug(
            "mail_store build=%s version=%s query=%r since=%s before=%s result_count=%s",
            __build_marker__,
            __version__,
            query,
            since,
            before,
            len(data),
        )
        return data[:limit]
    except MailStoreUnavailable as exc:
        _logger.debug(
            "mail_store build=%s version=%s query=%r failed code=%s message=%s",
            __build_marker__,
            __version__,
            query,
            exc.code,
            str(exc),
        )
        snapshot_state = get_mail_snapshot_state()
        if snapshot_state is not None:
            snapshot_db_path = snapshot_state.get("snapshot_db_path")
            if snapshot_db_path:
                try:
                    data = _search_mail_store_scoped(
                        query=query,
                        mailbox_id=mailbox_id,
                        limit=limit,
                        since=since,
                        before=before,
                        search_fields=search_fields,
                        filters=filters,
                        mailbox_inventory_fn=mailbox_inventory_fn,
                        db_path=snapshot_db_path,
                    )
                    _logger.debug(
                        "mail_store_snapshot build=%s version=%s query=%r since=%s before=%s result_count=%s",
                        __build_marker__,
                        __version__,
                        query,
                        since,
                        before,
                        len(data),
                    )
                    return data[:limit]
                except MailStoreUnavailable as snapshot_exc:
                    _logger.debug(
                        "mail_store_snapshot build=%s version=%s query=%r failed code=%s message=%s",
                        __build_marker__,
                        __version__,
                        query,
                        snapshot_exc.code,
                        str(snapshot_exc),
                    )
        raise exc


def _mail_store_degraded_state(exc: MailStoreUnavailable) -> dict[str, Any]:
    snapshot_state = get_mail_snapshot_state()
    if snapshot_state is not None:
        state = {
            "error": "mail_snapshot_unavailable",
            "message": "Live Mail metadata is unavailable and the current snapshot could not be used.",
            "recoverable": True,
            "provider": "mail_store",
            "live_error": exc.code,
            "snapshot_available": True,
        }
    else:
        state = {
            "error": "mail_snapshot_required",
            "message": "Live Mail metadata is unavailable. Run refresh_mail_snapshot to create a temporary Mail snapshot for reads.",
            "recoverable": True,
            "provider": "mail_store",
            "live_error": exc.code,
            "snapshot_available": False,
        }
    if exc.code == "mail_store_permission_denied":
        state["next_step"] = (
            "Run apple-ecosystem-mcp mail refresh-snapshot from Terminal, or grant Full Disk Access to the installed runtime."
        )
        state["settings_path"] = "System Settings > Privacy & Security > Full Disk Access"
    return state


def _run_applescript_search(
    *,
    query: str,
    mailbox_id: str | None,
    capped: int,
    since: str | None,
    before: str | None,
    search_fields: list[str],
    filters: dict,
    recent_mode: bool,
    timeout: int = 35,
) -> list[dict[str, Any]]:
    args = _build_search_args(
        query=query,
        mailbox_id=mailbox_id,
        capped=capped,
        since=since,
        before=before,
        search_fields=search_fields,
        filters=filters,
        recent_mode=recent_mode,
    )
    raw = run_applescript(_SEARCH_SCRIPT, *args, timeout=timeout)
    data = _parse_json(raw) or []
    if not isinstance(data, list):
        raise RuntimeError("Unexpected mail_search payload shape")
    for item in data:
        if isinstance(item, dict) and isinstance(item.get("preview"), str):
            item["preview"] = item["preview"][:MAIL_PREVIEW_CHARS]
    return data[:capped]


def _search_mail_applescript_scoped(
    *,
    query: str,
    mailbox_id: str | None,
    limit: int,
    since: str | None,
    before: str | None,
    search_fields: list[str],
    filters: dict,
    recent_mode: bool,
    mailbox_inventory_fn: Callable[[], list[dict]] | None,
) -> list[dict[str, Any]]:
    if not recent_mode or query or mailbox_id or filters.get("mailbox_ids"):
        return _run_applescript_search(
            query=query,
            mailbox_id=mailbox_id,
            capped=limit,
            since=since,
            before=before,
            search_fields=search_fields,
            filters=filters,
            recent_mode=recent_mode,
        )

    inventory = _mailbox_inventory(mailbox_inventory_fn)
    plans = _mailbox_id_groups_for_applescript_recent(
        inventory,
        account_name=filters.get("account_name"),
    )
    _logger.debug(
        "mail_recent build=%s version=%s scoped_plans=%s since=%s before=%s account_filter=%s",
        __build_marker__,
        __version__,
        [(account, len(mailbox_ids)) for account, mailbox_ids in plans],
        since,
        before,
        filters.get("account_name"),
    )
    if not plans:
        return _run_applescript_search(
            query=query,
            mailbox_id=mailbox_id,
            capped=limit,
            since=since,
            before=before,
            search_fields=search_fields,
            filters=filters,
            recent_mode=recent_mode,
        )

    collected: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    last_timeout: RuntimeError | None = None
    for account, mailbox_ids in plans:
        scoped_query_specs: list[dict[str, Any]] = []
        base_filters = dict(filters)
        base_filters["account_name"] = account
        base_filters["mailbox_ids"] = mailbox_ids
        if since and "unread" not in base_filters:
            scoped_query_specs = [
                {"filters": {**base_filters, "unread": True}, "limit": max(limit, 10)},
                {"filters": {**base_filters, "unread": False}, "limit": max(limit, 10)},
            ]
        else:
            scoped_query_specs = [{"filters": base_filters, "limit": max(limit, 10)}]

        for spec in scoped_query_specs:
            try:
                rows = _run_applescript_search(
                    query=query,
                    mailbox_id=None,
                    capped=spec["limit"],
                    since=since,
                    before=before,
                    search_fields=search_fields,
                    filters=spec["filters"],
                    recent_mode=recent_mode,
                    timeout=12,
                )
            except RuntimeError as exc:
                if "timed out" not in str(exc).lower():
                    raise
                last_timeout = exc
                _logger.debug(
                    "mail_recent build=%s account=%s mailbox_scope=%s unread=%s timeout=true",
                    __build_marker__,
                    account,
                    mailbox_ids,
                    spec["filters"].get("unread"),
                )
                continue
            _logger.debug(
                "mail_recent build=%s account=%s mailbox_scope=%s unread=%s result_count=%s",
                __build_marker__,
                account,
                mailbox_ids,
                spec["filters"].get("unread"),
                len(rows),
            )

            for row in rows:
                if not isinstance(row, dict):
                    continue
                if not row.get("account_name"):
                    row["account_name"] = account
                key = (str(row.get("id") or ""), str(row.get("internal_id") or ""))
                if key in seen:
                    continue
                seen.add(key)
                collected.append(row)

        if not any(
            str(item.get("account_name") or "") == account
            for item in collected
        ):
            fallback_filters = dict(filters)
            fallback_filters["account_name"] = account
            fallback_filters.pop("mailbox_ids", None)
            _logger.debug(
                "mail_recent build=%s account=%s mailbox_scope_empty=true retrying_account_only",
                __build_marker__,
                account,
            )
            fallback_specs: list[dict[str, Any]]
            if since and "unread" not in fallback_filters:
                fallback_specs = [
                    {"filters": {**fallback_filters, "unread": True}, "limit": max(limit, 10)},
                    {"filters": {**fallback_filters, "unread": False}, "limit": max(limit, 10)},
                ]
            else:
                fallback_specs = [{"filters": fallback_filters, "limit": max(limit, 10)}]
            for spec in fallback_specs:
                try:
                    rows = _run_applescript_search(
                        query=query,
                        mailbox_id=None,
                        capped=spec["limit"],
                        since=since,
                        before=before,
                        search_fields=search_fields,
                        filters=spec["filters"],
                        recent_mode=recent_mode,
                        timeout=12,
                    )
                except RuntimeError as exc:
                    if "timed out" not in str(exc).lower():
                        raise
                    last_timeout = exc
                    _logger.debug(
                        "mail_recent build=%s account=%s account_only unread=%s timeout=true",
                        __build_marker__,
                        account,
                        spec["filters"].get("unread"),
                    )
                    continue
                _logger.debug(
                    "mail_recent build=%s account=%s account_only unread=%s result_count=%s",
                    __build_marker__,
                    account,
                    spec["filters"].get("unread"),
                    len(rows),
                )
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    if not row.get("account_name"):
                        row["account_name"] = account
                    key = (str(row.get("id") or ""), str(row.get("internal_id") or ""))
                    if key in seen:
                        continue
                    seen.add(key)
                    collected.append(row)

    if collected:
        return _sort_mail_results(collected)[:limit]
    if last_timeout is not None:
        raise last_timeout
    return _run_applescript_search(
        query=query,
        mailbox_id=mailbox_id,
        capped=limit,
        since=since,
        before=before,
        search_fields=search_fields,
        filters=filters,
        recent_mode=recent_mode,
    )


def _build_search_args(
    *,
    query: str,
    mailbox_id: str | None,
    capped: int,
    since: str | None,
    before: str | None,
    search_fields: list[str],
    filters: dict,
    recent_mode: bool,
) -> list[str]:
    args = [
        query,
        mailbox_id or "",
        since or "",
        str(capped),
        filters.get("from_addr") or "",
        "1" if filters.get("unread") is True else ("0" if filters.get("unread") is False else ""),
        "1" if filters.get("flagged") is True else ("0" if filters.get("flagged") is False else ""),
        "1" if filters.get("has_attachments") is True else ("0" if filters.get("has_attachments") is False else ""),
        filters.get("account_name") or "",
        "1" if "body" in search_fields else "0",
        before or "",
    ]

    mailbox_ids = filters.get("mailbox_ids") or []
    args.append(str(len(mailbox_ids)))
    args.extend(mailbox_ids)

    args.append("1" if "subject" in search_fields else "0")
    args.append("1" if "sender" in search_fields else "0")
    args.append(filters.get("to_addr") or "")
    args.append(filters.get("cc_addr") or "")
    max_scan_total = capped * 40
    if "body" in search_fields:
        max_scan_total = capped * 15
    if filters.get("mailbox_ids") or mailbox_id:
        max_scan_total *= 2
    args.append(str(max(50, min(max_scan_total, 800))))
    args.append("1" if recent_mode else "0")
    return args


def _execute_search(
    *,
    query: str,
    mailbox_id: str | None,
    limit: int,
    since: str | None,
    before: str | None,
    search_fields: list[str] | None,
    filters: dict | None,
    recent_mode: bool,
    mailbox_inventory_fn: Callable[[], list[dict]] | None,
) -> list[dict]:
    query = (query or "").strip()
    capped = max(1, min(int(limit), MAIL_SEARCH_MAX))

    filters = filters or {}
    search_fields = search_fields or ["subject"]
    search_fields = [field.lower() for field in search_fields]
    provider_mode = _mail_provider_mode(filters)

    store_capable = _can_search_mail_store(
        query,
        search_fields,
        filters,
        since=since,
        before=before,
        mailbox_id=mailbox_id,
    )
    if recent_mode and "body" not in search_fields:
        store_capable = True

    if provider_mode == MAIL_PROVIDER_LOCAL and store_capable:
        try:
            return _search_mail_store_with_snapshot_fallback(
                query=query,
                mailbox_id=mailbox_id,
                limit=capped,
                since=since,
                before=before,
                search_fields=search_fields,
                filters=filters,
                mailbox_inventory_fn=mailbox_inventory_fn,
            )
        except MailStoreUnavailable as exc:
            return [_mail_store_degraded_state(exc)]

    try:
        return _search_mail_applescript_scoped(
            query=query,
            mailbox_id=mailbox_id,
            limit=capped,
            since=since,
            before=before,
            search_fields=search_fields,
            filters=filters,
            recent_mode=recent_mode,
            mailbox_inventory_fn=mailbox_inventory_fn,
        )
    except RuntimeError as applescript_exc:
        if provider_mode == MAIL_PROVIDER_APPLESCRIPT or not store_capable:
            raise
        _logger.debug(
            "mail_applescript build=%s version=%s query=%r failed message=%s; trying local store fallback",
            __build_marker__,
            __version__,
            query,
            str(applescript_exc),
        )
        try:
            rows = _search_mail_store_with_snapshot_fallback(
                query=query,
                mailbox_id=mailbox_id,
                limit=capped,
                since=since,
                before=before,
                search_fields=search_fields,
                filters=filters,
                mailbox_inventory_fn=mailbox_inventory_fn,
            )
        except MailStoreUnavailable as store_exc:
            degraded = _mail_store_degraded_state(store_exc)
            degraded["applescript_error"] = str(applescript_exc)
            return [degraded]
        for row in rows:
            if isinstance(row, dict):
                row.setdefault("fallback_provider", "mail_store")
                row.setdefault("primary_provider_error", str(applescript_exc))
        return rows[:capped]


def search_mail(
    query: str,
    *,
    mailbox_id: str | None = None,
    limit: int = MAIL_SEARCH_DEFAULT,
    since: str | None = None,
    before: str | None = None,
    search_fields: list[str] | None = None,
    filters: dict | None = None,
    mailbox_inventory_fn: Callable[[], list[dict]] | None = None,
) -> list[dict]:
    return _execute_search(
        query=query,
        mailbox_id=mailbox_id,
        limit=limit,
        since=since,
        before=before,
        search_fields=search_fields,
        filters=filters,
        recent_mode=False,
        mailbox_inventory_fn=mailbox_inventory_fn,
    )


def recent_mail(
    *,
    limit: int = MAIL_SEARCH_DEFAULT,
    since: str | None = None,
    before: str | None = None,
    mailbox_id: str | None = None,
    filters: dict | None = None,
    mailbox_inventory_fn: Callable[[], list[dict]] | None = None,
) -> list[dict]:
    return _execute_search(
        query="",
        mailbox_id=mailbox_id,
        limit=limit,
        since=since,
        before=before,
        search_fields=list(MAIL_RECENT_DEFAULT_FIELDS),
        filters=filters,
        recent_mode=True,
        mailbox_inventory_fn=mailbox_inventory_fn,
    )


_SEARCH_SCRIPT = r"""
on run argv
    set qry to item 1 of argv
    set mbId to item 2 of argv
    set sinceStr to item 3 of argv
    set limitStr to item 4 of argv
    set fromAddr to item 5 of argv
    set unreadStr to item 6 of argv
    set flaggedStr to item 7 of argv
    set hasAttachStr to item 8 of argv
    set acctNameFilter to item 9 of argv
    set searchBodyStr to item 10 of argv
    set beforeStr to item 11 of argv
    set mbIdsCountStr to item 12 of argv

    set lim to (limitStr as integer)
    set searchBody to searchBodyStr is "1"
    set mbIdsCount to (mbIdsCountStr as integer)
    set mbIds to {}
    set mbIdsIdx to 13
    repeat mbIdsCount times
        set end of mbIds to item mbIdsIdx of argv
        set mbIdsIdx to mbIdsIdx + 1
    end repeat

    set searchSubjectStr to item mbIdsIdx of argv
    set searchSubject to searchSubjectStr is "1"
    set searchSenderStr to item (mbIdsIdx + 1) of argv
    set searchSender to searchSenderStr is "1"
    set toAddr to item (mbIdsIdx + 2) of argv
    set ccAddr to item (mbIdsIdx + 3) of argv
    set maxScanTotal to (item (mbIdsIdx + 4) of argv) as integer
    set recentMode to (item (mbIdsIdx + 5) of argv) is "1"

    set hasFilters to false
    if recentMode or unreadStr is not "" or flaggedStr is not "" or hasAttachStr is not "" or fromAddr is not "" or toAddr is not "" or ccAddr is not "" or acctNameFilter is not "" or mbIdsCount > 0 then
        set hasFilters to true
    end if

    if qry is "" and not hasFilters then
        return "[]"
    end if

    set output to "["
    set firstItem to true
    set count_ to 0
    set scannedTotal to 0

    tell application "Mail"
        repeat with acct in accounts
            if scannedTotal ≥ maxScanTotal then exit repeat
            set acctName to name of acct
            set checkAcctFilter to acctNameFilter is "" or acctName is acctNameFilter

            if checkAcctFilter then
                repeat with mb in mailboxes of acct
                    if scannedTotal ≥ maxScanTotal then exit repeat
                    set shouldSearch to false
                    if mbIdsCount > 0 then
                        set mbIdStr to ""
                        try
                            set mbIdStr to id of mb as text
                        end try
                        if mbIdStr is "" then
                            try
                                set mbIdStr to name of mb as string
                            end try
                        end if
                        repeat with mbIdToCheck in mbIds
                            if mbIdStr is mbIdToCheck then
                                set shouldSearch to true
                                exit repeat
                            end if
                        end repeat
                    else if mbId is "" then
                        set shouldSearch to true
                    else
                        set mbIdStr to ""
                        try
                            set mbIdStr to id of mb as text
                        end try
                        if mbIdStr is "" then
                            try
                                set mbIdStr to name of mb as string
                            end try
                        end if
                        if mbIdStr is mbId then
                            set shouldSearch to true
                        end if
                    end if

                    if shouldSearch then
                        set msgList to {}
                        set mCount to 0
                        try
                            if fromAddr is not "" then
                                if unreadStr is "1" then
                                    set msgList to (messages of mb whose read status is false and sender contains fromAddr)
                                else if unreadStr is "0" then
                                    set msgList to (messages of mb whose read status is true and sender contains fromAddr)
                                else
                                    set msgList to (messages of mb whose sender contains fromAddr)
                                end if
                            else if unreadStr is "1" then
                                set msgList to (messages of mb whose read status is false)
                            else if unreadStr is "0" then
                                set msgList to (messages of mb whose read status is true)
                            else
                                set msgList to messages of mb
                            end if
                            set mCount to count of msgList
                        end try

                        set scanLim to mCount
                        if hasFilters then
                            if scanLim > 250 then set scanLim to 250
                        else
                            if scanLim > 500 then set scanLim to 500
                        end if

                        repeat with offset_ from 0 to (scanLim - 1)
                            if count_ ≥ lim then exit repeat
                            if scannedTotal ≥ maxScanTotal then exit repeat
                            set idx_ to (mCount - offset_)
                            if idx_ < 1 then exit repeat
                            set scannedTotal to scannedTotal + 1

                            set msg to missing value
                            try
                                set msg to item idx_ of msgList
                            end try
                            if msg is missing value then
                            else
                                set subj to ""
                                try
                                    set subj to subject of msg as string
                                end try
                                set snd to ""
                                if searchSender then
                                    try
                                        set snd to sender of msg as string
                                    end try
                                end if

                                set queryMatch to false
                                if qry is "" then
                                    set queryMatch to true
                                else if searchSubject and my containsCI(subj, qry) then
                                    set queryMatch to true
                                else if searchSender and my containsCI(snd, qry) then
                                    set queryMatch to true
                                else if searchBody then
                                    set bodyText to ""
                                    try
                                        set bodyText to content of msg
                                    end try
                                    if my containsCI(bodyText, qry) then
                                        set queryMatch to true
                                    end if
                                end if

                                if queryMatch then
                                        set msgDate to ""
                                        try
                                            set msgDate to (date received of msg) as «class isot» as string
                                        end try

                                        set dateInRange to true
                                        if sinceStr is not "" and (msgDate is "" or msgDate < sinceStr) then
                                            set dateInRange to false
                                            if recentMode then exit repeat
                                        end if
                                        if beforeStr is not "" and (msgDate is "" or msgDate > beforeStr) then
                                            set dateInRange to false
                                        end if

                                        if dateInRange then
                                            set unreadMatch to true
                                            if unreadStr is not "" then
                                                set isUnread to not (read status of msg)
                                                if unreadStr is "1" then
                                                    set unreadMatch to isUnread
                                                else
                                                    set unreadMatch to not isUnread
                                                end if
                                            end if

                                            set flaggedMatch to true
                                            if flaggedStr is not "" then
                                                set isFlagged to flagged status of msg
                                                if flaggedStr is "1" then
                                                    set flaggedMatch to isFlagged
                                                else
                                                    set flaggedMatch to not isFlagged
                                                end if
                                            end if

                                            set attachMatch to true
                                            if hasAttachStr is not "" then
                                                set hasAttach to (count of mail attachments of msg) > 0
                                                if hasAttachStr is "1" then
                                                    set attachMatch to hasAttach
                                                else
                                                    set attachMatch to not hasAttach
                                                end if
                                            end if

                                            set fromMatch to true
                                            if fromAddr is not "" then
                                                set snd to ""
                                                try
                                                    set snd to sender of msg as string
                                                end try
                                                set fromMatch to my containsCI(snd, fromAddr)
                                            end if

                                            set toMatch to true
                                            if toAddr is not "" then
                                                set toAddresses to ""
                                                try
                                                    repeat with r in (to recipients of msg)
                                                        set toAddresses to toAddresses & (address of r as string) & " "
                                                    end repeat
                                                end try
                                                set toMatch to my containsCI(toAddresses, toAddr)
                                            end if

                                            set ccMatch to true
                                            if ccAddr is not "" then
                                                set ccAddresses to ""
                                                try
                                                    repeat with r in (cc recipients of msg)
                                                        set ccAddresses to ccAddresses & (address of r as string) & " "
                                                    end repeat
                                                end try
                                                set ccMatch to my containsCI(ccAddresses, ccAddr)
                                            end if

                                            if unreadMatch and flaggedMatch and attachMatch and fromMatch and toMatch and ccMatch then
                                                set snd to ""
                                                try
                                                    set snd to sender of msg as string
                                                end try
                                                set mid to ""
                                                try
                                                    set mid to message id of msg as string
                                                end try
                                                set internalId to ""
                                                try
                                                    set internalId to id of msg as string
                                                end try
                                                if mid is "" then set mid to internalId
                                                set preview to ""
                                                set thisMbId to ""
                                                try
                                                    set thisMbId to id of mb as string
                                                end try
                                                set hasAttach to (count of mail attachments of msg) > 0

                                                if not firstItem then set output to output & ","
                                                set firstItem to false
                                                set output to output & "{\"id\":" & my jsonString(mid) & ",\"internal_id\":" & my jsonString(internalId) & ",\"subject\":" & my jsonString(subj) & ",\"sender\":" & my jsonString(snd) & ",\"date\":" & my jsonString(msgDate) & ",\"preview\":" & my jsonString(preview) & ",\"mailbox_id\":" & my jsonString(thisMbId) & ",\"account_name\":" & my jsonString(acctName) & ",\"has_attachments\":" & (hasAttach as string) & "}"
                                                set count_ to count_ + 1
                                            end if
                                        end if
                                end if
                            end if
                        end repeat
                        if count_ ≥ lim then exit repeat
                    end if
                end repeat
            end if
            if count_ ≥ lim then exit repeat
            if scannedTotal ≥ maxScanTotal then exit repeat
        end repeat
    end tell
    return output & "]"
end run

on containsCI(hay, needle)
    try
        ignoring case
            return (hay contains needle)
        end ignoring
    on error
        return false
    end try
end containsCI

on jsonString(s)
    if s is missing value then return "null"
    set t to s as string
    set AppleScript's text item delimiters to "\\"
    set parts to text items of t
    set AppleScript's text item delimiters to "\\\\"
    set t to parts as string
    set AppleScript's text item delimiters to "\""
    set parts to text items of t
    set AppleScript's text item delimiters to "\\\""
    set t to parts as string
    set AppleScript's text item delimiters to return
    set parts to text items of t
    set AppleScript's text item delimiters to "\\n"
    set t to parts as string
    set AppleScript's text item delimiters to linefeed
    set parts to text items of t
    set AppleScript's text item delimiters to "\\n"
    set t to parts as string
    set AppleScript's text item delimiters to tab
    set parts to text items of t
    set AppleScript's text item delimiters to "\\t"
    set t to parts as string
    set AppleScript's text item delimiters to ""
    return "\"" & t & "\""
end jsonString
"""
