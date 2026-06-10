# Testing Guide: MAIL-001 through MAIL-006

This guide provides commands to test the new mail features locally.

## Quick Start

### 1. Run Local Unit Tests

All tests use mocks and run without requiring Mail access:

```bash
# Run all mail tests
uv run pytest tests/tools/test_mail.py -v

# Run just the new feature tests
uv run pytest tests/tools/test_mail.py -k "MAIL" -v

# Run specific feature tests
uv run pytest tests/tools/test_mail.py::test_mail_search_with_from_filter -v
uv run pytest tests/tools/test_mail.py::test_mail_search_with_before_filter -v
uv run pytest tests/tools/test_mail.py::test_mail_list_mailboxes_includes_path -v
```

### 2. Run Feature Demo Script

Interactive demonstration with mock data:

```bash
uv run python test_features_local.py
```

This shows how each feature works with sample data:
- MAIL-001: RFC Message-ID in move/flag/delete
- MAIL-002: Advanced filters
- MAIL-003: Body search
- MAIL-004: Mailbox path hierarchy
- MAIL-005: Attachments in search
- MAIL-006: Date range filtering

### 3. Direct API Testing with Claude

Create a test prompt like:

```
Test these mail search features:
1. Search for "invoice" with from_addr filter for "sales@example.com"
2. Search for "meeting" with unread=True and has_attachments=True
3. Search "report" in body with search_fields=["body"]
4. List mailboxes and show their paths
5. Search from 2026-04-01 to 2026-05-01
```

## Feature-by-Feature Testing

### MAIL-001: Canonical RFC Message-ID

**What changed**: Move/flag/delete operations now prefer RFC Message-ID first.

**Test commands**:
```bash
# Test that RFC IDs work in move/flag/delete (unit tests)
uv run pytest tests/tools/test_mail.py::test_mail_move_accepts_rfc_id -v
uv run pytest tests/tools/test_mail.py::test_mail_flag_accepts_rfc_id -v
uv run pytest tests/tools/test_mail.py::test_mail_delete_accepts_rfc_id -v

# Test that search returns valid IDs
uv run pytest tests/tools/test_mail.py::test_mail_search_id_always_present -v
```

**API Usage**:
```python
# RFC IDs work transparently now
mail_move_message("<msg-12345@example.com>", "mb-archive")
mail_flag_message("<msg-12345@example.com>", True)
mail_delete("<msg-12345@example.com>")
```

---

### MAIL-002: Advanced Filters

**What changed**: New `filters` dict parameter with multiple filter options.

**Available filters**:
- `from_addr`: str - filter by sender
- `to_addr`: str - filter by recipient
- `cc_addr`: str - filter by CC
- `unread`: bool - only unread (True) or read (False)
- `flagged`: bool - only flagged (True) or unflagged (False)
- `has_attachments`: bool - only with (True) or without (False)
- `account_name`: str - filter by account name
- `mailbox_ids`: list[str] - filter by specific mailboxes

**Test commands**:
```bash
# Test individual filters
uv run pytest tests/tools/test_mail.py::test_mail_search_with_from_filter -v
uv run pytest tests/tools/test_mail.py::test_mail_search_with_unread_filter -v
uv run pytest tests/tools/test_mail.py::test_mail_search_with_flagged_filter -v
uv run pytest tests/tools/test_mail.py::test_mail_search_with_has_attachments_filter -v
uv run pytest tests/tools/test_mail.py::test_mail_search_with_account_name_filter -v
uv run pytest tests/tools/test_mail.py::test_mail_search_with_mailbox_ids_list -v

# Test multiple filters together
uv run pytest tests/tools/test_mail.py::test_mail_search_multiple_filters -v

# Test backward compatibility (no filters)
uv run pytest tests/tools/test_mail.py::test_mail_search_no_filters_backward_compat -v
```

**API Usage**:
```python
# Single filter
mail_search("invoice", filters={"from_addr": "sales@example.com"})

# Multiple filters
mail_search(
    "meeting",
    filters={
        "unread": True,
        "flagged": True,
        "has_attachments": True,
        "account_name": "Work",
    }
)

# Mailbox IDs list
mail_search("report", filters={"mailbox_ids": ["mb-inbox", "mb-archive"]})
```

---

### MAIL-003: Body Search

**What changed**: New `search_fields` parameter to control which fields are searched.

**Options**:
- Default `["subject"]` - searches subject only
- `["subject", "body"]` - searches both
- `["body"]` - searches body only

**Test commands**:
```bash
# Test default (subject only)
uv run pytest tests/tools/test_mail.py::test_mail_search_default_search_fields_subject_only -v

# Test with body field
uv run pytest tests/tools/test_mail.py::test_mail_search_with_body_field -v

# Test body only
uv run pytest tests/tools/test_mail.py::test_mail_search_with_body_field_only -v
```

**API Usage**:
```python
# Subject only (default)
mail_search("invoice")  # Same as before

# Subject and body
mail_search("invoice", search_fields=["subject", "body"])

# Body only
mail_search("invoice", search_fields=["body"])

# Combined with other filters
mail_search(
    "Q2 results",
    search_fields=["body"],
    filters={"from_addr": "finance@example.com"}
)
```

---

### MAIL-004: Mailbox Path Hierarchy

**What changed**: `mail_list_mailboxes` now returns a `path` field showing hierarchical mailbox structure.

**Test commands**:
```bash
# Test path field exists
uv run pytest tests/tools/test_mail.py::test_mail_list_mailboxes_includes_path -v

# Test nested paths
uv run pytest tests/tools/test_mail.py::test_mail_list_mailboxes_nested_path -v
```

**API Usage**:
```python
mailboxes = mail_list_mailboxes()
for mb in mailboxes:
    print(f"{mb['name']:15} | Path: {mb['path']}")
    
# Example output:
# INBOX           | Path: INBOX
# Archive         | Path: Archive
# 2024            | Path: Archive/2024
# Q1              | Path: Archive/2024/Q1
# Sent Items      | Path: Sent Items
```

**Response shape** (now includes `path`):
```json
{
  "name": "2024",
  "id": "mailbox-id-123",
  "account_name": "iCloud",
  "path": "Archive/2024"
}
```

---

### MAIL-005: Attachments in Search Results

**What changed**: `mail_search` now includes `has_attachments` boolean in each result.

**Test commands**:
```bash
# Test has_attachments field
uv run pytest tests/tools/test_mail.py::test_mail_search_returns_has_attachments_field -v

# Test it's a boolean
uv run pytest tests/tools/test_mail.py::test_mail_search_has_attachments_is_boolean -v
```

**API Usage**:
```python
results = mail_search("proposals")

# Filter results locally if needed
with_attachments = [r for r in results if r['has_attachments']]
print(f"Found {len(with_attachments)} results with attachments")

# Or filter server-side
results = mail_search(
    "proposals",
    filters={"has_attachments": True}
)
```

**Response includes** (in each result):
```json
{
  "id": "<msg-123@example.com>",
  "subject": "Quarterly report",
  "sender": "reports@example.com",
  "date": "2026-04-15T10:00:00",
  "has_attachments": true,
  ...
}
```

---

### MAIL-006: Date Range Filtering

**What changed**: New `before` parameter for upper-bound date filtering; works with existing `since`.

**Test commands**:
```bash
# Test before filter
uv run pytest tests/tools/test_mail.py::test_mail_search_with_before_filter -v

# Test both since and before
uv run pytest tests/tools/test_mail.py::test_mail_search_with_since_and_before -v
```

**API Usage**:
```python
# Just since (existing behavior)
mail_search("invoice", since="2026-04-01T00:00:00")

# Just before (new)
mail_search("invoice", before="2026-05-01T00:00:00")

# Date range (both)
mail_search(
    "monthly report",
    since="2026-04-01T00:00:00",
    before="2026-05-01T00:00:00"
)

# Combined with filters
mail_search(
    "test",
    since="2026-04-01T00:00:00",
    before="2026-05-01T00:00:00",
    filters={"unread": True}
)
```

---

## Testing in Claude Desktop (Local)

### Setup

1. **Update your Claude Desktop config** to use the local development version:

   Edit `~/.claude/user-settings.json` and add:
   ```json
   {
     "mcpServers": {
       "apple-ecosystem-mcp-local": {
         "type": "stdio",
         "command": "uv",
         "args": ["run", "--no-project", "-p", "/Users/abhinav/projects/git/apple-ecosystem-mcp", "python", "-m", "apple_ecosystem_mcp"],
         "disabled": false
       }
     }
   }
   ```

2. **Restart Claude Desktop** to load the new server.

3. **Test in Claude** with prompts like:

```
Search my mail for "invoice" from "sales@example.com" that I haven't read yet
with attachments, between April and May 2026.
```

### Live Testing Checklist

Once connected, test:

- [ ] **MAIL-001**: Move/flag/delete messages using RFC IDs (should work transparently)
- [ ] **MAIL-002**: Use filters in natural language and see results filtered
- [ ] **MAIL-003**: Search for text in message bodies with natural language
- [ ] **MAIL-004**: Ask Claude to list mailbox hierarchy
- [ ] **MAIL-005**: Ask which emails have attachments
- [ ] **MAIL-006**: Search within date ranges

---

## Backward Compatibility

All new features are **completely backward compatible**:

```python
# Old code still works exactly as before
mail_search("invoice")
mail_search("test", mailbox_id="inbox-123")
mail_search("q", since="2026-04-01T00:00:00")

# New features are opt-in with keyword args
mail_search("q", filters={"unread": True}, search_fields=["body"], before="2026-05-01T00:00:00")
```

---

## Full Test Suite

Run the complete test suite to verify all 174 tests pass:

```bash
# Run all tests (excluding live tests that need real Mail access)
uv run pytest tests/ -k "not live" -v

# Run just mail tests
uv run pytest tests/tools/test_mail.py -v

# Run with coverage
uv run pytest tests/tools/test_mail.py --cov=apple_ecosystem_mcp.tools.mail
```

---

## Troubleshooting

### "mail_search() got unexpected keyword argument 'filters'"

This means you're running the old code. Make sure you:
1. Are on the `feature/mail-advanced-search` branch
2. Have run `uv sync --dev` to install the local version
3. Are testing with the local code, not a published version

### AppleScript permission errors in Claude Desktop

If you see "AppleScript failed (exit -1743)" in Claude:
1. Grant Mail full disk access in System Preferences
2. Restart Claude Desktop
3. Try again

### "Message not found" with RFC IDs

This shouldn't happen with the new code. If it does:
1. Make sure the message ID is correct
2. Check that the message still exists in the account
3. Try using `mail_search` to verify the ID format first
