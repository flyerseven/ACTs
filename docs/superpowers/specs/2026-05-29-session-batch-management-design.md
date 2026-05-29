# Session Batch Management — Design Spec

**Date:** 2026-05-29
**Status:** Approved

## Overview

Add batch management capabilities to the Session sidebar: select multiple sessions and perform delete/move-group operations, plus group-level batch operations via right-click menu.

## Decisions

- **Approach:** Both checkbox multi-select + group-level operations (Option C)
- **Checkbox visibility:** Toggle via toolbar "批量管理" button (Option B — batch mode)
- **Group menu:** Batch delete + batch move to group (Option B — consistent with session menu)

## Architecture

Minimal changes, reusing existing components:

| File | Change Level | Description |
|---|---|---|
| `src/ui/session_tree_widget.py` | Major | Add `_batch_mode`, checkboxes per item, batch action bar, group batch menu items |
| `src/ui/main_window.py` | Medium | Add batch confirmation dialogs, batch delete/move logic, connect signals |
| `src/core/session.py` | Minimal | Optional `delete_batch()` static method |

**No changes to:** models.py, session_panel.py, file_store.py

## Data Flow

```
SessionTreeWidget (checkbox selection → collected session_ids)
    ↓ signal: batch_delete_requested / batch_move_requested
MainWindow (confirmation dialog → loop call Session.delete / edit_session_meta)
    ↓
FileStore / Session (persist → refresh tree)
```

## UI Design

### Batch Mode Toggle
- Toolbar: "批量管理" button enters batch mode
- In batch mode: button text changes to "完成" (Done)
- Every session item shows a checkbox on the left
- Bottom action bar appears: "删除 (N)" + "移动到..." buttons

### Checkbox States
- Empty: unchecked, gray border
- Checked: blue fill with white checkmark
- Action buttons disabled when count = 0

### Group Right-Click Menu (extended)
- Existing: 重命名分组, 删除分组
- **New:** separator + 删除本组全部会话 + 移动本组到其他分组

## Interaction Flow

1. User clicks "批量管理" → enters batch mode, checkboxes appear
2. User checks session checkboxes → action bar counter updates
3. User clicks "删除 (N)" or "移动到..." → confirmation dialog
4. Operation executes → auto-exit batch mode, refresh list
5. User can also click "完成" to exit without action

## Edge Cases

| Scenario | Handling |
|---|---|
| 0 items selected | Action buttons grayed out |
| Active chat session deleted | Clear right-side chat panel in MainWindow |
| Target group = source group | Silently skip that item |
| Partial failure | Continue, report "成功 X, 失败 Y" |
| Tab switch during batch mode | Auto-exit batch mode |
