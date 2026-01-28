# Playbook Builder UI - Implementation Test Plan

## Phase 1: Core Infrastructure ✅
- [x] Created EmptyState component
- [x] Created PlaybookActionItem component
- [x] Created PlaybookCanvas component
- [x] Created ActionPalette component
- [x] Created ActionPaletteItem component
- [x] Updated PlaybookEditorPage to 3-column layout
- [x] Updated backend to return proper action type metadata

## Phase 2: Drag-and-Drop ✅
- [x] Added drag functionality to ActionPaletteItem
- [x] Added drop handling to PlaybookCanvas
- [x] Integrated vuedraggable for reordering
- [x] Added drag handle and delete button to action items
- [x] Connected to playbookStore for state management

## Phase 3: Core Action Configuration ✅
- [x] Created ActionConfigPanel with tabs
- [x] Created ActionConfigForm router
- [x] Created TargetInput shared component
- [x] Created StrategySelector shared component
- [x] Created ClickActionForm
- [x] Created KeyboardActionForm
- [x] Created WaitActionForm
- [x] Created ScreenshotActionForm
- [x] Created CommandActionForm
- [x] Created GenericActionForm fallback
- [x] Updated PlaybookEditorPage to use ActionConfigPanel

## Phase 4: Save/Load & Polish ✅
- [x] Implemented Save functionality
- [x] Implemented Load functionality
- [x] Implemented Export to YAML download
- [x] Added unsaved changes indicator
- [x] Added keyboard shortcuts (Ctrl+S, Delete)
- [x] Updated header with playbook name input

## Manual Testing Checklist

### Basic Flow
1. Open http://localhost:5173/#/playbook-editor
2. Verify 3-column layout displays correctly
3. Verify action palette shows categories: GUI Actions, Control Flow, Data Actions, System Actions
4. Click on an action in palette - should add to canvas
5. Drag action from palette to canvas - should add to canvas
6. Verify empty state message when no actions exist
7. Add multiple actions, verify they display with index numbers

### Drag-and-Drop
1. Add 3-4 actions to canvas
2. Hover over action - verify drag handle and delete button appear
3. Drag action by handle - verify reordering works
4. Click delete button - verify action removed with toast notification
5. Drag action from palette - verify it's added at the end

### Action Configuration
1. Click on action in canvas - verify it's highlighted
2. Verify config panel shows action-specific form
3. **Click Action**: Change target type (image/text), verify updates reflected
4. **Keyboard Action**: Switch between "Type Text" and "Press Keys" modes
5. **Wait Action**: Change duration, verify updates
6. **Screenshot Action**: Toggle region capture, modify region values
7. **Command Action**: Enter command, modify timeout
8. Verify description field in Settings tab
9. Verify screenshot before/after checkboxes work
10. Verify Variables tab shows available variables

### Save/Load
1. Enter playbook name: "test-playbook"
2. Add 2-3 actions with different configurations
3. Press Ctrl+S or click Save button
4. Verify toast notification shows "Playbook Saved"
5. Verify dirty indicator disappears
6. Make a change - verify dirty indicator appears
7. Click Load button, enter "test-playbook"
8. Verify playbook loads with all actions and configurations
9. Click Export button - verify YAML file downloads

### Keyboard Shortcuts
1. Add action, make change, press Ctrl+S - verify save works
2. Select action, press Delete - verify action removed

### Validation (Future Phase)
- Not implemented yet - will be added in validation phase

## Known Issues / Future Enhancements
- Load functionality uses prompt() - should have proper dialog
- No variable editor yet - need VariablesPanel component
- No validation yet - will be added in Phase 4
- Forms for remaining action types (Drag, Scroll, Loop, etc.) not implemented yet - use GenericActionForm

## Files Created
1. `/adare-web/src/components/common/EmptyState.vue`
2. `/adare-web/src/components/common/TargetInput.vue`
3. `/adare-web/src/components/common/StrategySelector.vue`
4. `/adare-web/src/components/playbook/ActionPalette.vue`
5. `/adare-web/src/components/playbook/ActionPaletteItem.vue`
6. `/adare-web/src/components/playbook/PlaybookCanvas.vue`
7. `/adare-web/src/components/playbook/PlaybookActionItem.vue`
8. `/adare-web/src/components/playbook/ActionConfigPanel.vue`
9. `/adare-web/src/components/playbook/ActionConfigForm.vue`
10. `/adare-web/src/components/actions/ClickActionForm.vue`
11. `/adare-web/src/components/actions/KeyboardActionForm.vue`
12. `/adare-web/src/components/actions/WaitActionForm.vue`
13. `/adare-web/src/components/actions/ScreenshotActionForm.vue`
14. `/adare-web/src/components/actions/CommandActionForm.vue`
15. `/adare-web/src/components/actions/GenericActionForm.vue`

## Files Modified
1. `/adare-web/src/views/PlaybookEditorPage.vue` - Updated to 3-column layout with ActionConfigPanel
2. `/adare/adare/webapi/main.py` - Updated action types endpoint to return proper metadata

## Total Lines of Code Added
~1,500 lines across 17 files
