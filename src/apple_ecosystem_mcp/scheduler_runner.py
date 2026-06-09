from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Callable

from .scheduled_tasks import ScheduledTask, ScheduledTaskStore, get_scheduled_tasks_path


ConnectorFunc = Callable[..., Any]


@dataclass(frozen=True)
class WorkflowRunResult:
    task_name: str
    task_type: str
    output_path: Path
    content: str
    generated_at: datetime


@dataclass(frozen=True)
class WorkflowConnectors:
    calendar_list_events: ConnectorFunc
    mail_search: ConnectorFunc
    reminders_lists: ConnectorFunc
    reminders_list: ConnectorFunc
    icloud_search: ConnectorFunc


SUPPORTED_WORKFLOW_NAMES = (
    "daily_briefing",
    "tomorrow_preview",
    "overdue_reminders_review",
    "unread_priority_mail_review",
    "receipt_finder",
    "weekly_planning_digest",
)


class WorkflowRunError(RuntimeError):
    """Raised when a scheduled workflow cannot be executed."""


class SchedulerRunner:
    """Run read-only scheduled workflows and write Markdown reports."""

    def __init__(self, *, connectors: WorkflowConnectors | None = None) -> None:
        self.connectors = connectors or _default_connectors()

    def run_task(
        self,
        task: ScheduledTask,
        *,
        now: datetime | None = None,
    ) -> WorkflowRunResult:
        generated_at = now or datetime.now().astimezone()
        if task.task_type not in SUPPORTED_WORKFLOW_NAMES:
            raise WorkflowRunError(f"Unsupported scheduled workflow {task.task_type!r}")

        output_path = resolve_output_path(task)
        content = self._render(task, generated_at=generated_at)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content, encoding="utf-8")
        return WorkflowRunResult(
            task_name=task.name,
            task_type=task.task_type,
            output_path=output_path,
            content=content,
            generated_at=generated_at,
        )

    def run_task_by_name(
        self,
        name: str,
        *,
        store: ScheduledTaskStore | None = None,
        now: datetime | None = None,
    ) -> WorkflowRunResult:
        task_store = store or ScheduledTaskStore()
        task = task_store.get_task(name)
        if task is None:
            raise WorkflowRunError(f"Scheduled task {name!r} does not exist")
        return self.run_task(task, now=now)

    def _render(self, task: ScheduledTask, *, generated_at: datetime) -> str:
        handler = getattr(self, f"_render_{task.task_type}", None)
        if handler is None:
            raise WorkflowRunError(f"Unsupported scheduled workflow {task.task_type!r}")
        return handler(task, generated_at=generated_at)

    def _render_daily_briefing(self, task: ScheduledTask, *, generated_at: datetime) -> str:
        today = generated_at.date()
        start, end = _day_window(today)
        events = _sorted_events(
            self.connectors.calendar_list_events(
                start.isoformat(),
                end.isoformat(),
                calendar_uid=_optional_text(task.config.get("calendar_uid")),
                limit=_config_int(task.config, "calendar_limit", default=25),
            )
        )
        overdue = self._overdue_reminders(task, generated_at=generated_at)
        unread_mail = _sorted_mail(
            self.connectors.mail_search(
                _optional_text(task.config.get("mail_query"), default=""),
                limit=_config_int(task.config, "mail_limit", default=10),
                since=start.isoformat(),
                search_fields=["subject", "sender"],
                filters={"unread": True},
            )
        )
        return _markdown_report(
            title="Daily Briefing",
            task=task,
            generated_at=generated_at,
            sections=[
                _events_section(f"Calendar for {today.isoformat()}", events),
                _reminders_section("Overdue reminders", overdue),
                _mail_section("Unread priority mail", unread_mail),
            ],
        )

    def _render_tomorrow_preview(self, task: ScheduledTask, *, generated_at: datetime) -> str:
        tomorrow = generated_at.date() + timedelta(days=1)
        start, end = _day_window(tomorrow)
        events = _sorted_events(
            self.connectors.calendar_list_events(
                start.isoformat(),
                end.isoformat(),
                calendar_uid=_optional_text(task.config.get("calendar_uid")),
                limit=_config_int(task.config, "calendar_limit", default=25),
            )
        )
        reminders = [
            reminder
            for reminder in self._open_reminders(task)
            if _matches_due_date(reminder.get("due"), tomorrow)
        ]
        return _markdown_report(
            title="Tomorrow Preview",
            task=task,
            generated_at=generated_at,
            sections=[
                _events_section(f"Tomorrow's events ({tomorrow.isoformat()})", events),
                _reminders_section("Reminders due tomorrow", reminders),
            ],
        )

    def _render_overdue_reminders_review(
        self,
        task: ScheduledTask,
        *,
        generated_at: datetime,
    ) -> str:
        overdue = self._overdue_reminders(task, generated_at=generated_at)
        return _markdown_report(
            title="Overdue Reminders Review",
            task=task,
            generated_at=generated_at,
            sections=[_reminders_section("Overdue reminders", overdue)],
        )

    def _render_unread_priority_mail_review(
        self,
        task: ScheduledTask,
        *,
        generated_at: datetime,
    ) -> str:
        filters: dict[str, Any] = {"unread": True}
        if "flagged" in task.config:
            filters["flagged"] = bool(task.config["flagged"])
        mail = _sorted_mail(
            self.connectors.mail_search(
                _optional_text(task.config.get("mail_query"), default=""),
                limit=_config_int(task.config, "mail_limit", default=20),
                since=_lookback_start(generated_at, days=_config_int(task.config, "lookback_days", default=7)),
                search_fields=["subject", "sender"],
                filters=filters,
            )
        )
        return _markdown_report(
            title="Unread Priority Mail Review",
            task=task,
            generated_at=generated_at,
            sections=[_mail_section("Unread mail", mail)],
        )

    def _render_receipt_finder(self, task: ScheduledTask, *, generated_at: datetime) -> str:
        query = _optional_text(task.config.get("query"), default="receipt")
        mail_hits = _sorted_mail(
            self.connectors.mail_search(
                query,
                limit=_config_int(task.config, "mail_limit", default=20),
                since=_lookback_start(generated_at, days=_config_int(task.config, "lookback_days", default=30)),
                search_fields=["subject", "sender", "body"],
                filters=task.config.get("mail_filters") if isinstance(task.config.get("mail_filters"), dict) else None,
            )
        )
        files = _sorted_files(
            self.connectors.icloud_search(
                query,
                path=_optional_text(task.config.get("icloud_path"), default="/"),
                content_search=bool(task.config.get("content_search", False)),
            )
        )
        return _markdown_report(
            title="Receipt Finder",
            task=task,
            generated_at=generated_at,
            sections=[
                _mail_section("Mail matches", mail_hits),
                _files_section("iCloud matches", files),
            ],
        )

    def _render_weekly_planning_digest(
        self,
        task: ScheduledTask,
        *,
        generated_at: datetime,
    ) -> str:
        start = datetime.combine(generated_at.date(), time.min, tzinfo=generated_at.tzinfo)
        end = start + timedelta(days=_config_int(task.config, "days", default=7))
        events = _sorted_events(
            self.connectors.calendar_list_events(
                start.isoformat(),
                end.isoformat(),
                calendar_uid=_optional_text(task.config.get("calendar_uid")),
                limit=_config_int(task.config, "calendar_limit", default=50),
            )
        )
        reminders = [
            reminder
            for reminder in self._open_reminders(task)
            if _due_on_or_before(reminder.get("due"), end.date())
        ]
        unread_mail = _sorted_mail(
            self.connectors.mail_search(
                _optional_text(task.config.get("mail_query"), default=""),
                limit=_config_int(task.config, "mail_limit", default=10),
                since=start.isoformat(),
                search_fields=["subject", "sender"],
                filters={"unread": True},
            )
        )
        return _markdown_report(
            title="Weekly Planning Digest",
            task=task,
            generated_at=generated_at,
            sections=[
                _events_section("Upcoming events", events),
                _reminders_section("Open reminders due soon", reminders),
                _mail_section("Unread mail to keep in view", unread_mail),
            ],
        )

    def _open_reminders(self, task: ScheduledTask) -> list[dict[str, Any]]:
        targets = _reminder_targets(task.config, self.connectors.reminders_lists(include_metadata=True))
        per_list_limit = _config_int(task.config, "reminders_limit_per_list", default=25)
        reminders: list[dict[str, Any]] = []
        for target in targets:
            item = self.connectors.reminders_list(
                list_name=target.get("name"),
                reminders_list_id=target.get("id"),
                completed=False,
                limit=per_list_limit,
            )
            if isinstance(item, list):
                reminders.extend(reminder for reminder in item if isinstance(reminder, dict))
        return _sorted_reminders(reminders)

    def _overdue_reminders(self, task: ScheduledTask, *, generated_at: datetime) -> list[dict[str, Any]]:
        today = generated_at.date()
        return [
            reminder
            for reminder in self._open_reminders(task)
            if _is_overdue(reminder.get("due"), today)
        ]


def run_scheduled_task(
    task: ScheduledTask,
    *,
    now: datetime | None = None,
    connectors: WorkflowConnectors | None = None,
) -> WorkflowRunResult:
    return SchedulerRunner(connectors=connectors).run_task(task, now=now)


def run_scheduled_task_by_name(
    name: str,
    *,
    store: ScheduledTaskStore | None = None,
    now: datetime | None = None,
    connectors: WorkflowConnectors | None = None,
) -> WorkflowRunResult:
    return SchedulerRunner(connectors=connectors).run_task_by_name(name, store=store, now=now)


def run_scheduler(
    name: str | None = None,
    *,
    store: ScheduledTaskStore | None = None,
    now: datetime | None = None,
    connectors: WorkflowConnectors | None = None,
) -> list[WorkflowRunResult]:
    """Run one named task, or all enabled tasks for launchd-triggered runs."""
    task_store = store or ScheduledTaskStore()
    runner = SchedulerRunner(connectors=connectors)
    if name is not None:
        return [runner.run_task_by_name(name, store=task_store, now=now)]
    return [runner.run_task(task, now=now) for task in task_store.list_tasks(include_disabled=False)]


def resolve_output_path(task: ScheduledTask) -> Path:
    if task.output_path:
        raw_path = Path(task.output_path).expanduser()
        if raw_path.is_absolute():
            return raw_path
        return get_scheduled_tasks_path().parent / raw_path
    return get_scheduled_tasks_path().parent / "scheduled-task-reports" / f"{task.name}.md"


def _default_connectors() -> WorkflowConnectors:
    from .tools.calendar import calendar_list_events
    from .tools.icloud import icloud_search
    from .tools.mail import mail_search
    from .tools.reminders import reminders_list, reminders_lists

    return WorkflowConnectors(
        calendar_list_events=calendar_list_events,
        mail_search=mail_search,
        reminders_lists=reminders_lists,
        reminders_list=reminders_list,
        icloud_search=icloud_search,
    )


def _day_window(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min)
    return start, start + timedelta(days=1)


def _lookback_start(now: datetime, *, days: int) -> str:
    start = now - timedelta(days=max(0, days))
    return start.isoformat()


def _optional_text(value: Any, *, default: str | None = None) -> str | None:
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def _config_int(config: dict[str, Any], key: str, *, default: int) -> int:
    value = config.get(key, default)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _reminder_targets(config: dict[str, Any], available_lists: Any) -> list[dict[str, str | None]]:
    configured_ids = _string_list(config.get("reminder_list_ids"))
    configured_names = _string_list(config.get("reminder_list_names"))
    available: list[dict[str, str | None]] = []
    if isinstance(available_lists, list):
        for item in available_lists:
            if isinstance(item, dict):
                available.append(
                    {"id": _optional_text(item.get("id")), "name": _optional_text(item.get("name"))}
                )
            elif isinstance(item, str):
                available.append({"id": None, "name": item})

    if configured_ids or configured_names:
        matched: list[dict[str, str | None]] = []
        for item in available:
            if item["id"] in configured_ids or item["name"] in configured_names:
                matched.append(item)
        return matched
    return available


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    items: list[str] = []
    for item in value:
        text = _optional_text(item)
        if text:
            items.append(text)
    return items


def _parse_due(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _is_overdue(value: Any, today: date) -> bool:
    due = _parse_due(value)
    return due is not None and due.date() < today


def _matches_due_date(value: Any, target: date) -> bool:
    due = _parse_due(value)
    return due is not None and due.date() == target


def _due_on_or_before(value: Any, target: date) -> bool:
    due = _parse_due(value)
    return due is not None and due.date() <= target


def _sorted_events(events: Any) -> list[dict[str, Any]]:
    items = [event for event in events if isinstance(event, dict)] if isinstance(events, list) else []
    return sorted(items, key=lambda item: str(item.get("start") or ""))


def _sorted_mail(messages: Any) -> list[dict[str, Any]]:
    items = [message for message in messages if isinstance(message, dict)] if isinstance(messages, list) else []
    return sorted(items, key=lambda item: str(item.get("date") or ""), reverse=True)


def _sorted_reminders(reminders: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(reminders, key=lambda item: (str(item.get("due") or "9999"), str(item.get("title") or "")))


def _sorted_files(files: Any) -> list[dict[str, Any]]:
    items = [item for item in files if isinstance(item, dict)] if isinstance(files, list) else []
    return sorted(items, key=lambda item: str(item.get("path") or item.get("name") or ""))


def _markdown_report(
    *,
    title: str,
    task: ScheduledTask,
    generated_at: datetime,
    sections: list[str],
) -> str:
    body = "\n\n".join(section for section in sections if section.strip())
    return (
        f"# {title}\n\n"
        f"- Task: `{task.name}`\n"
        f"- Workflow: `{task.task_type}`\n"
        f"- Generated: `{generated_at.isoformat()}`\n\n"
        f"{body}\n"
    )


def _events_section(title: str, events: list[dict[str, Any]]) -> str:
    if not events:
        return f"## {title}\n\nNo events found.\n"
    lines = [f"## {title}", ""]
    for event in events:
        label = str(event.get("title") or "Untitled event")
        start = str(event.get("start") or "unknown start")
        end = str(event.get("end") or "unknown end")
        calendar_name = _optional_text(event.get("calendar_name"))
        location = _optional_text(event.get("location"))
        suffix = []
        if calendar_name:
            suffix.append(calendar_name)
        if location:
            suffix.append(location)
        tail = f" ({'; '.join(suffix)})" if suffix else ""
        lines.append(f"- **{label}**: {start} -> {end}{tail}")
    return "\n".join(lines) + "\n"


def _reminders_section(title: str, reminders: list[dict[str, Any]]) -> str:
    if not reminders:
        return f"## {title}\n\nNo reminders found.\n"
    lines = [f"## {title}", ""]
    for reminder in reminders:
        label = str(reminder.get("title") or "Untitled reminder")
        due = str(reminder.get("due") or "no due date")
        list_name = _optional_text(reminder.get("list_name"))
        suffix = f" ({list_name})" if list_name else ""
        lines.append(f"- **{label}**: due {due}{suffix}")
    return "\n".join(lines) + "\n"


def _mail_section(title: str, messages: list[dict[str, Any]]) -> str:
    if not messages:
        return f"## {title}\n\nNo messages found.\n"
    lines = [f"## {title}", ""]
    for message in messages:
        subject = str(message.get("subject") or "(no subject)")
        sender = _optional_text(message.get("sender"), default="unknown sender")
        received = _optional_text(message.get("date"), default="unknown date")
        preview = _optional_text(message.get("preview"))
        line = f"- **{subject}** from {sender} at {received}"
        if preview:
            line += f": {preview}"
        lines.append(line)
    return "\n".join(lines) + "\n"


def _files_section(title: str, files: list[dict[str, Any]]) -> str:
    if not files:
        return f"## {title}\n\nNo files found.\n"
    lines = [f"## {title}", ""]
    for item in files:
        name = str(item.get("name") or item.get("path") or "Unnamed file")
        path = _optional_text(item.get("path"))
        kind = _optional_text(item.get("kind"))
        suffix = []
        if path:
            suffix.append(path)
        if kind:
            suffix.append(kind)
        tail = f" ({'; '.join(suffix)})" if suffix else ""
        lines.append(f"- **{name}**{tail}")
    return "\n".join(lines) + "\n"
