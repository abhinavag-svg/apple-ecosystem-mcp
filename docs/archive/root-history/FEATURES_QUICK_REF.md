# Quick Reference: MAIL-001 to MAIL-006

## API Function Signature

```python
mail_search(
    query: str,
    mailbox_id: str | None = None,          # Legacy single mailbox
    limit: int = 20,                         # Default 20, max 100
    since: str | None = None,                # ISO date: "2026-04-01T00:00:00"
    before: str | None = None,               # ISO date: "2026-05-01T00:00:00" [NEW]
    search_fields: list[str] | None = None,  # Default ["subject"] [NEW]
    filters: dict | None = None,             # Advanced filters dict [NEW]
) -> list[dict]:
```

---

## Usage Examples

### MAIL-002: Filters

```python
# Single filter
mail_search("invoice", filters={"from_addr": "sales@example.com"})

# Multiple filters
mail_search(
    "meeting",
    filters={
        "from_addr": "team@example.com",      # Sender contains
        "unread": True,                        # Only unread (True) or read (False)
        "flagged": True,                       # Only flagged (True) or not (False)
        "has_attachments": True,               # Only with attachments
        "account_name": "Work",                # Specific account
        "mailbox_ids": ["mb-1", "mb-2"],       # Specific mailboxes
    }
)

# All filter keys are optional
mail_search("test", filters={})  # Same as mail_search("test")
```

### MAIL-003: Body Search

```python
# Subject only (default)
mail_search("invoice")

# Subject and body
mail_search("invoice", search_fields=["subject", "body"])

# Body only
mail_search("invoice", search_fields=["body"])
```

### MAIL-004: Mailbox Paths

```python
mailboxes = mail_list_mailboxes()

# Response now includes 'path' field:
# {
#   "name": "Q1",
#   "id": "mailbox-123",
#   "account_name": "Work",
#   "path": "Archive/2024/Q1"
# }

for mb in mailboxes:
    print(f"{mb['account_name']:10} → {mb['path']}")
```

### MAIL-005: Attachments

```python
results = mail_search("proposals")

# Each result includes has_attachments boolean:
for msg in results:
    print(f"{'📎' if msg['has_attachments'] else '  '} {msg['subject']}")

# Or filter server-side:
results = mail_search("proposals", filters={"has_attachments": True})
```

### MAIL-006: Date Range

```python
# After April 1
mail_search("invoice", since="2026-04-01T00:00:00")

# Before May 1
mail_search("invoice", before="2026-05-01T00:00:00")

# Between April and May
mail_search(
    "monthly report",
    since="2026-04-01T00:00:00",
    before="2026-05-01T00:00:00"
)
```

### Everything Combined

```python
results = mail_search(
    "quarterly",
    since="2026-04-01T00:00:00",
    before="2026-06-30T23:59:59",
    search_fields=["subject", "body"],
    filters={
        "from_addr": "finance@example.com",
        "unread": False,              # Read only
        "has_attachments": True,
        "account_name": "Work",
        "mailbox_ids": ["mb-archive"],
    }
)

for msg in results:
    att = "📎" if msg["has_attachments"] else "  "
    print(f"{att} {msg['date'][:10]} | {msg['subject']}")
```

---

## Response Fields

### `mail_search()` returns list of:

```python
{
    "id": "<msg-123@example.com>",       # RFC Message-ID (canonical)
    "internal_id": "12345",               # AppleScript internal ID (backward compat)
    "subject": "Q2 Report",
    "sender": "finance@example.com",
    "date": "2026-04-15T10:00:00",        # ISO 8601
    "preview": "Here is the q2 report...", # First 200 chars of body
    "mailbox_id": "mb-archive-123",
    "account_name": "Work",
    "has_attachments": True,               # NEW: boolean
}
```

### `mail_list_mailboxes()` returns list of:

```python
{
    "name": "2024",
    "id": "mailbox-123",
    "account_name": "Work",
    "path": "Archive/2024",               # NEW: hierarchical path
}
```

---

## Testing Commands

```bash
# Run feature demo
uv run python test_features_local.py

# Run specific feature tests
uv run pytest tests/tools/test_mail.py -k "MAIL" -v

# Run all mail tests
uv run pytest tests/tools/test_mail.py -v

# Full test suite
uv run pytest tests/ -k "not live" -v
```

---

## Filter Logic

- **`from_addr`, `to_addr`, `cc_addr`**: Substring match (case-insensitive)
- **`unread`**: `True` = unread messages, `False` = read messages
- **`flagged`**: `True` = flagged messages, `False` = unflagged messages
- **`has_attachments`**: `True` = with attachments, `False` = without
- **`account_name`**: Exact match
- **`mailbox_ids`**: List of mailbox IDs (any match)

If a filter is omitted, it's not applied (ignored).

---

## Important Notes

### Backward Compatibility ✅

All new features are **100% backward compatible**:
- Existing code works unchanged
- New parameters are optional
- Default behavior preserved

### Date Format

Always use ISO 8601 with timezone or UTC indicator:
- ✅ `"2026-04-01T00:00:00"` (recommended)
- ✅ `"2026-04-01T00:00:00Z"` (UTC)
- ❌ `"2026-04-01"` (incomplete, will fail)

### Message IDs

- Use `id` field (RFC Message-ID) for operations
- `internal_id` is kept for compatibility but not recommended
- Both work for move/flag/delete thanks to MAIL-001

### Search Scope

- Default: searches all mailboxes in all accounts
- Can limit to single mailbox with `mailbox_id` (legacy)
- Can limit to multiple with `filters["mailbox_ids"]` (new)

---

## Limits

| Feature | Limit | Notes |
|---------|-------|-------|
| `limit` | 1-100 | Default 20 results |
| `preview` | 200 chars | First 200 chars of body |
| `body` | 8,000 chars | Full body in `mail_get_thread()` |
| Mailbox scan | 5,000 messages | Per mailbox when searching |
| Results | 100 max | Hard cap on results returned |

---

## Error Handling

```python
try:
    results = mail_search("invoice", filters={"from_addr": "sales@example.com"})
except RuntimeError as e:
    # AppleScript permissions or Mail errors
    print(f"Search failed: {e}")
```

Common errors:
- **"Message not found"**: Message doesn't exist or was deleted
- **"AppleScript failed (exit -1743)"**: Mail.app permission denied (System Preferences)
- **"Malformed JSON output"**: Mail returned unexpected data

---

## Performance Tips

1. **Use filters** to reduce results before returning:
   ```python
   # Faster: filtered at source
   mail_search("test", filters={"has_attachments": True})
   
   # Slower: filter after
   results = mail_search("test")
   with_att = [r for r in results if r["has_attachments"]]
   ```

2. **Limit date ranges** for large accounts:
   ```python
   # Searches only 1 month
   mail_search("invoice", 
       since="2026-04-01T00:00:00",
       before="2026-05-01T00:00:00"
   )
   ```

3. **Use mailbox IDs** instead of searching all:
   ```python
   # Faster: single mailbox
   mail_search("test", mailbox_id="mb-archive")
   
   # Slower: all mailboxes
   mail_search("test")
   ```
