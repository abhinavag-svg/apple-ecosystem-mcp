# Test Commands Reference

Copy and paste these commands to test the MAIL-001 through MAIL-006 features locally.

## 🚀 Quick Demo (No Mail Access Required)

This is the fastest way to see all features working:

```bash
# Shows all 6 features with sample output
uv run python test_features_local.py
```

Expected output: ✅ All 6 features demonstrated with mock data

---

## 🧪 Unit Tests (No Mail Access Required)

Test the implementation using mocked AppleScript:

```bash
# All mail tests (55 tests)
uv run pytest tests/tools/test_mail.py -v

# Just the new feature tests
uv run pytest tests/tools/test_mail.py::test_mail_search_with_from_filter -v
uv run pytest tests/tools/test_mail.py::test_mail_search_with_unread_filter -v
uv run pytest tests/tools/test_mail.py::test_mail_search_with_flagged_filter -v
uv run pytest tests/tools/test_mail.py::test_mail_search_with_has_attachments_filter -v
uv run pytest tests/tools/test_mail.py::test_mail_search_with_account_name_filter -v
uv run pytest tests/tools/test_mail.py::test_mail_search_with_mailbox_ids_list -v
uv run pytest tests/tools/test_mail.py::test_mail_search_multiple_filters -v
uv run pytest tests/tools/test_mail.py::test_mail_search_with_body_field -v
uv run pytest tests/tools/test_mail.py::test_mail_search_with_before_filter -v
uv run pytest tests/tools/test_mail.py::test_mail_search_with_since_and_before -v
uv run pytest tests/tools/test_mail.py::test_mail_list_mailboxes_includes_path -v
uv run pytest tests/tools/test_mail.py::test_mail_search_returns_has_attachments_field -v

# RFC ID tests (MAIL-001)
uv run pytest tests/tools/test_mail.py::test_mail_move_accepts_rfc_id -v
uv run pytest tests/tools/test_mail.py::test_mail_flag_accepts_rfc_id -v
uv run pytest tests/tools/test_mail.py::test_mail_delete_accepts_rfc_id -v
```

Expected: All tests pass ✅

---

## 🔬 Full Test Suite

Verify nothing is broken:

```bash
# All tests except live ones that need real Mail
uv run pytest tests/ -k "not live" -v

# Count: 174 tests should pass
```

Expected: 174 / 174 passing ✅

---

## 📊 Test Coverage

See code coverage for mail.py:

```bash
uv run pytest tests/tools/test_mail.py --cov=apple_ecosystem_mcp.tools.mail --cov-report=term-missing
```

---

## 🎯 Test Specific Features

### MAIL-001: RFC Message-ID

```bash
# Verify move/flag/delete work with RFC IDs
uv run pytest tests/tools/test_mail.py::test_mail_move_accepts_rfc_id -v
uv run pytest tests/tools/test_mail.py::test_mail_flag_accepts_rfc_id -v
uv run pytest tests/tools/test_mail.py::test_mail_delete_accepts_rfc_id -v
uv run pytest tests/tools/test_mail.py::test_mail_search_id_always_present -v
```

### MAIL-002: Advanced Filters

```bash
# Test each filter type
uv run pytest tests/tools/test_mail.py -k "filter" -v

# Or specific filters
uv run pytest tests/tools/test_mail.py::test_mail_search_with_from_filter -v
uv run pytest tests/tools/test_mail.py::test_mail_search_with_unread_filter -v
uv run pytest tests/tools/test_mail.py::test_mail_search_with_flagged_filter -v
uv run pytest tests/tools/test_mail.py::test_mail_search_with_has_attachments_filter -v
uv run pytest tests/tools/test_mail.py::test_mail_search_with_account_name_filter -v
uv run pytest tests/tools/test_mail.py::test_mail_search_with_mailbox_ids_list -v
uv run pytest tests/tools/test_mail.py::test_mail_search_multiple_filters -v
uv run pytest tests/tools/test_mail.py::test_mail_search_no_filters_backward_compat -v
```

### MAIL-003: Body Search

```bash
# Test search_fields parameter
uv run pytest tests/tools/test_mail.py -k "search_fields" -v

# Or individually
uv run pytest tests/tools/test_mail.py::test_mail_search_default_search_fields_subject_only -v
uv run pytest tests/tools/test_mail.py::test_mail_search_with_body_field -v
uv run pytest tests/tools/test_mail.py::test_mail_search_with_body_field_only -v
uv run pytest tests/tools/test_mail.py::test_mail_search_subject_field_only -v
```

### MAIL-004: Mailbox Path

```bash
# Test mailbox path hierarchy
uv run pytest tests/tools/test_mail.py -k "path" -v

# Or individually
uv run pytest tests/tools/test_mail.py::test_mail_list_mailboxes_includes_path -v
uv run pytest tests/tools/test_mail.py::test_mail_list_mailboxes_nested_path -v
```

### MAIL-005: Attachments

```bash
# Test has_attachments field
uv run pytest tests/tools/test_mail.py -k "attachment" -v

# Or individually
uv run pytest tests/tools/test_mail.py::test_mail_search_returns_has_attachments_field -v
uv run pytest tests/tools/test_mail.py::test_mail_search_has_attachments_is_boolean -v
```

### MAIL-006: Date Range

```bash
# Test before filter
uv run pytest tests/tools/test_mail.py -k "before" -v

# Or individually
uv run pytest tests/tools/test_mail.py::test_mail_search_with_before_filter -v
uv run pytest tests/tools/test_mail.py::test_mail_search_with_since_and_before -v
```

---

## 🌐 Live Testing in Claude Desktop

### Step 1: Update Claude Settings

Edit `~/.claude/user-settings.json`:

```json
{
  "mcpServers": {
    "apple-ecosystem-mcp-local": {
      "type": "stdio",
      "command": "uv",
      "args": [
        "run",
        "--no-project",
        "-p",
        "/Users/abhinav/projects/git/apple-ecosystem-mcp",
        "python",
        "-m",
        "apple_ecosystem_mcp"
      ],
      "disabled": false
    }
  }
}
```

### Step 2: Restart Claude Desktop

```bash
# Quit and restart the Claude Desktop app
```

### Step 3: Test with Prompts

Try these prompts in Claude:

```
Search my mail for invoices from sales@example.com
```

```
Find unread emails with attachments from my Work account
```

```
Search for quarterly reports in my email body from April to June 2026
```

```
List my mailbox hierarchy and show folder paths
```

```
Find all flagged emails that are unread
```

```
Search for meeting notes between March 1 and April 30, 2026
```

---

## ✅ Verification Checklist

- [ ] Run `uv run python test_features_local.py` → all 6 features demo
- [ ] Run `uv run pytest tests/tools/test_mail.py -v` → 55 tests pass
- [ ] Run `uv run pytest tests/ -k "not live" -v` → 174 tests pass
- [ ] Review `FEATURES_QUICK_REF.md` for API reference
- [ ] Review `TESTING_GUIDE.md` for detailed examples
- [ ] Optional: Setup Claude Desktop and test live searches
- [ ] Optional: Enable `APPLE_MCP_LIVE_TESTS=1 uv run pytest tests/live/` for real Mail access

---

## 📝 Branch Info

- **Branch**: `feature/mail-advanced-search`
- **Commits**: 2 implementation + 1 testing docs
- **Tests**: 55 mail tests (34 new + 3 updated + 18 existing)
- **Coverage**: All 6 features tested
- **Backward Compatible**: ✅ Yes (100%)

---

## 🐛 Troubleshooting

### Import Error: "No module named 'apple_ecosystem_mcp'"

```bash
# Make sure you're on the feature branch
git branch
# Should show: * feature/mail-advanced-search

# Sync dependencies
uv sync --dev
```

### pytest: command not found

```bash
# Use uv to run pytest
uv run pytest tests/tools/test_mail.py -v
```

### AppleScript permission denied in Claude Desktop

```bash
# Grant Mail full disk access:
# System Preferences > Security & Privacy > Full Disk Access > + Mail.app
# Then restart Claude Desktop
```

### "Mail.app permission denied" running live tests

```bash
# Live tests need real Mail access
# Skip them for now: use -k "not live"
uv run pytest tests/ -k "not live" -v
```

---

## 📞 Need Help?

See the full guides:
- **FEATURES_QUICK_REF.md** - API reference and examples
- **TESTING_GUIDE.md** - Feature-by-feature testing guide with detailed explanations
