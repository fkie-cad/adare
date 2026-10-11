# ADARE Web: Vue-to-React Frontend Rewrite

**Date:** 2026-04-09
**Status:** Approved

## Goal

Replace the Vue 3 + PrimeVue frontend in `adare-web/` with a React frontend matching the `adare-server/frontend_react/` tech stack, adding a collapsible sidebar layout and a 4-variant theme system (light/dark x default/teal).

## Tech Stack

Matching `adare-server/frontend_react/` exactly:

| Concern | Library | Version |
|---|---|---|
| UI Framework | React + React DOM | 19.x |
| Language | TypeScript | ~5.9 |
| Build | Vite + @vitejs/plugin-react | 8.x |
| Routing | @tanstack/react-router | latest |
| Server State | @tanstack/react-query | 5.x |
| Client State | Zustand | 5.x |
| HTTP | Axios | 1.x |
| Styling | Tailwind CSS | 4.x |
| Component Variants | class-variance-authority (CVA) | 0.7.x |
| Class Merging | clsx + tailwind-merge | latest |
| Icons | lucide-react | latest |
| UI Primitives | @radix-ui/react-slot, @radix-ui/react-dialog, etc. | latest |
| Font | @fontsource-variable/inter | latest |
| Drag & Drop | @dnd-kit/core + @dnd-kit/sortable | latest |
| Forms | react-hook-form + zod | latest |

## Directory Structure

```
adare-web/
├── index.html
├── package.json
├── tsconfig.json
├── vite.config.ts
└── src/
    ├── main.tsx                    # Entry point
    ├── app.tsx                     # QueryClient + Router providers
    ├── api/
    │   ├── client.ts              # Axios instance with interceptors
    │   ├── endpoints.ts           # API path constants
    │   └── hooks/
    │       ├── use-sessions.ts    # useQuery/useMutation for sessions
    │       ├── use-checkpoints.ts
    │       ├── use-playbook.ts
    │       └── use-actions.ts
    ├── components/
    │   ├── layout/
    │   │   ├── main-layout.tsx    # Sidebar + content wrapper
    │   │   ├── sidebar.tsx        # Collapsible sidebar component
    │   │   └── sidebar-item.tsx   # Single nav item
    │   ├── ui/                    # Reusable primitives (Radix + CVA)
    │   │   ├── button.tsx
    │   │   ├── card.tsx
    │   │   ├── input.tsx
    │   │   ├── badge.tsx
    │   │   ├── dialog.tsx
    │   │   ├── textarea.tsx
    │   │   ├── separator.tsx
    │   │   ├── tooltip.tsx
    │   │   ├── progress.tsx
    │   │   ├── scroll-area.tsx
    │   │   └── theme-toggle.tsx
    │   ├── session/
    │   │   ├── session-card.tsx
    │   │   ├── start-session-dialog.tsx
    │   │   └── connection-status.tsx
    │   ├── playbook/
    │   │   ├── action-palette.tsx
    │   │   ├── action-palette-item.tsx
    │   │   ├── playbook-canvas.tsx
    │   │   ├── playbook-action-item.tsx
    │   │   ├── action-config-panel.tsx
    │   │   └── action-config-form.tsx
    │   ├── actions/
    │   │   ├── click-action-form.tsx
    │   │   ├── keyboard-action-form.tsx
    │   │   ├── wait-action-form.tsx
    │   │   ├── screenshot-action-form.tsx
    │   │   ├── command-action-form.tsx
    │   │   └── generic-action-form.tsx
    │   ├── checkpoint/
    │   │   └── checkpoint-panel.tsx
    │   ├── execution/
    │   │   └── execution-log.tsx
    │   └── shared/
    │       ├── empty-state.tsx
    │       ├── target-input.tsx
    │       └── strategy-selector.tsx
    ├── pages/
    │   ├── home.tsx
    │   ├── session-list.tsx
    │   ├── session-detail.tsx
    │   └── playbook-editor.tsx
    ├── routes/
    │   └── route-tree.tsx
    ├── stores/
    │   ├── theme-store.ts         # mode (light/dark/system) + colorScheme (default/teal)
    │   ├── sidebar-store.ts       # collapsed boolean
    │   ├── playbook-store.ts      # editor state: actions[], selection, isDirty, variables
    │   ├── execution-store.ts     # append-only execution log (client state, not server-fetched)
    │   └── websocket-store.ts     # per-session connection state
    ├── services/
    │   └── websocket.ts           # WebSocketClient + WebSocketManager classes
    ├── types/
    │   ├── api.ts                 # ApiResponse, request/response types
    │   ├── action.ts              # Action types, targets, strategies, metadata
    │   └── session.ts             # Session, checkpoint, VM status types
    ├── lib/
    │   └── utils.ts               # cn() = clsx + twMerge
    └── styles/
        └── globals.css            # Tailwind config + 4 theme variable sets
```

## Theme System

### Two Independent Axes

1. **Mode**: `light | dark | system` — stored in `localStorage` as `adare-mode`
2. **Color scheme**: `default | teal` — stored in `localStorage` as `adare-color-scheme`

### CSS Application

Applied via classes on `<html>`:
- Light Default: no classes (base)
- Dark Default: `class="dark"`
- Light Teal: `class="teal"`
- Dark Teal: `class="dark teal"`

### Color Tokens (globals.css)

Using oklch for perceptual uniformity, matching adare-server convention.

**Light Default (base `:root`):**

| Token | Value | Hex approx |
|---|---|---|
| `--color-background` | white | `#ffffff` |
| `--color-foreground` | slate-900 | `#0f172a` |
| `--color-card` | white | `#ffffff` |
| `--color-sidebar` | slate-50 | `#f8fafc` |
| `--color-primary` | ADARE teal | `#009374` |
| `--color-primary-foreground` | white | `#ffffff` |
| `--color-secondary` | blue | `#1976D2` |
| `--color-border` | slate-200 | `#e2e8f0` |
| `--color-muted` | slate-100 | `#f1f5f9` |
| `--color-muted-foreground` | slate-500 | `#64748b` |
| `--color-accent` | light teal | `#e6f7f3` |
| `--color-destructive` | red | `#C10015` |

**Dark Default (`.dark`):**

| Token | Value | Hex approx |
|---|---|---|
| `--color-background` | dark blue-slate | `#0c1620` |
| `--color-foreground` | slate-200 | `#e2e8f0` |
| `--color-card` | slate-teal | `#132232` |
| `--color-sidebar` | darkest | `#0a1219` |
| `--color-primary` | teal | `#009374` |
| `--color-primary-foreground` | white | `#e2e8f0` |
| `--color-border` | muted teal-gray | `#1e3a4a` |
| `--color-muted` | dark slate | `#162535` |
| `--color-muted-foreground` | slate-teal | `#8ba4b8` |
| `--color-accent` | dark teal | `#0d2b2b` |

**Light Teal (`.teal`):**

| Token | Value | Hex approx |
|---|---|---|
| `--color-background` | teal-tinted white | `#f0faf8` |
| `--color-foreground` | deep teal | `#0a3d2e` |
| `--color-card` | light teal | `#e8f5f2` |
| `--color-sidebar` | teal-50 | `#e0f0ed` |
| `--color-border` | teal-200 | `#b8e0d4` |
| `--color-muted` | teal-50 | `#d4ede6` |
| `--color-muted-foreground` | teal-600 | `#3d7a6a` |

**Dark Teal (`.dark.teal`):**

| Token | Value | Hex approx |
|---|---|---|
| `--color-background` | deep dark teal | `#021a1a` |
| `--color-foreground` | teal-white | `#d0eded` |
| `--color-card` | dark teal | `#0a2e2e` |
| `--color-sidebar` | darkest teal | `#011414` |
| `--color-border` | teal border | `#134040` |
| `--color-muted` | dark teal | `#082424` |
| `--color-muted-foreground` | muted teal | `#7ab8b8` |

### Theme Store (Zustand)

```typescript
type Mode = 'light' | 'dark' | 'system'
type ColorScheme = 'default' | 'teal'

interface ThemeState {
  mode: Mode
  colorScheme: ColorScheme
  setMode: (mode: Mode) => void
  setColorScheme: (scheme: ColorScheme) => void
}
```

Applies classes to `document.documentElement`:
- Toggles `dark` class based on resolved mode
- Toggles `teal` class based on colorScheme
- Listens to `prefers-color-scheme` media query when mode is `system`

### Theme Controls in Sidebar Footer

- **Mode toggle**: 3-segment button (Sun / Moon / Monitor icons) for light/dark/system
- **Color scheme toggle**: 2-segment button (Palette / Droplets icons) for default/teal

## Layout: Collapsible Sidebar

### Structure

```
┌─────────────┬─────────────────────────────────────┐
│  Sidebar    │                                     │
│  (240/64px) │         Page Content                │
│             │         (scrollable)                │
│  Logo       │                                     │
│  ─────────  │                                     │
│  Nav Items  │                                     │
│             │                                     │
│             │                                     │
│  ─────────  │                                     │
│  Theme      │                                     │
│  Collapse   │                                     │
└─────────────┴─────────────────────────────────────┘
```

### Sidebar States

**Expanded (240px):**
- ADARE logo/title at top
- Nav items: icon (20px) + label text
- Active item: teal background highlight
- Hover: subtle background
- Separator before footer section
- Theme controls (mode + color scheme)
- Collapse button (ChevronLeft icon)

**Collapsed (64px):**
- Small "A" logo
- Nav items: icon only, centered
- Tooltip on hover showing label
- Theme: icon-only toggles
- Expand button (ChevronRight icon)

### Sidebar Store (Zustand)

```typescript
interface SidebarState {
  collapsed: boolean
  toggle: () => void
}
```

Persisted to `localStorage` as `adare-sidebar-collapsed`.

### Transition

- `transition-all duration-200` on sidebar width
- Content area adjusts via CSS `margin-left` or `flex`

## Pages

### 1. Home Page (`/`)

Same content as Vue version:
- Hero section with gradient (kept as branded accent)
- Feature cards: Dev Sessions, Playbook Editor, Quick Start
- Feature grid: Drag & Drop, Real-time Testing, Checkpoints, YAML Export
- Tailwind styling instead of scoped CSS

### 2. Session List (`/sessions`)

- Page header: title + action buttons (Start New, Cleanup Stale, Refresh)
- Session card grid (responsive)
- Each card: status badge, project/experiment info, session ID, action count, uptime
- Empty state when no sessions
- Start Session dialog (react-hook-form + zod validation)
- Loading state with spinner

### 3. Session Detail (`/session/$id`)

3-panel layout within the content area:

```
┌──────────┬──────────────────────┬──────────────┐
│ Action   │  Quick Execute       │ Checkpoints  │
│ Palette  │  (YAML input)        │              │
│          │                      │ Variables    │
│ (search) │  ─────────────────   │              │
│ (accord) │  Playbook Builder    │ Execution    │
│          │  (placeholder)       │ Log          │
└──────────┴──────────────────────┴──────────────┘
```

- WebSocket connection managed by websocket-store
- Real-time updates: checkpoints, execution log entries
- TanStack Query cache invalidation on WS events
- Action buttons: Soft Reset, Hard Reset, Stop Session

### 4. Playbook Editor (`/playbook/editor`)

3-column layout:

```
┌──────────┬──────────────────────┬──────────────┐
│ Action   │  Playbook Canvas     │ Action       │
│ Palette  │  (drag-drop area)    │ Config       │
│          │                      │ Panel        │
│ (search) │  (dnd-kit sortable)  │ (tabs)       │
│ (groups) │                      │              │
└──────────┴──────────────────────┴──────────────┘
```

- @dnd-kit/core for drag from palette to canvas
- @dnd-kit/sortable for reordering on canvas
- Keyboard shortcuts: Ctrl+S (save), Delete (remove action)
- Config panel with tabs: Action Config, Settings, Variables
- Dynamic form selection based on action type

## API Layer

### Axios Client (`api/client.ts`)

Same pattern as adare-server:
- Base URL: `/api` (Vite proxy in dev)
- Request interceptor: add timestamp for cache-busting
- Response interceptor: extract data, handle errors

No auth interceptors needed (ADARE web doesn't have user auth — it connects to a local API server).

### React Query Hooks

Each hook file exports query and mutation hooks:

```typescript
// use-sessions.ts
export function useSessions()                    // useQuery: GET /sessions
export function useSessionState(id: string)      // useQuery: GET /sessions/{id}/state
export function useStartSession()                // useMutation: POST /sessions/start
export function useStopSession()                 // useMutation: POST /sessions/{id}/stop
export function useResetSession()                // useMutation: POST /sessions/{id}/reset
export function useCleanupSessions()             // useMutation: POST /sessions/cleanup

// use-checkpoints.ts
export function useCheckpoints(sessionId: string)      // useQuery
export function useCreateCheckpoint()                   // useMutation
export function useRestoreCheckpoint()                  // useMutation
export function useDeleteCheckpoint()                   // useMutation

// use-actions.ts
export function useActionTypes()                       // useQuery: GET /actions/types
export function useExecuteAction()                     // useMutation
export function useExecutePlaybook()                   // useMutation

// use-playbook.ts
export function useLoadPlaybook(name: string)          // useQuery
export function useSavePlaybook()                      // useMutation
```

## WebSocket Integration

### Architecture

- `WebSocketClient` class: per-session WS connection with auto-reconnect, ping/pong
- `WebSocketManager`: singleton managing multiple clients
- `websocket-store.ts`: Zustand store tracking `{ [sessionId]: boolean }` connection state

### React Query Integration

On WS events, invalidate relevant query caches:
- `checkpoint_created` / `checkpoint_deleted` / `checkpoint_restored` → invalidate `['checkpoints', sessionId]`
- `session_state` → invalidate `['session-state', sessionId]`
- `action_start` / `action_complete` / `action_error` → update execution log (kept in Zustand since it's append-only client state, not server-fetched)

### Connection Lifecycle

- `useEffect` in session-detail page: connect on mount, disconnect on unmount
- Connection status shown in sidebar (global indicator) and session detail header

## Routing

```typescript
// route-tree.tsx
const rootRoute     → MainLayout
  ├── /             → HomePage
  ├── /sessions     → SessionListPage
  ├── /session/$id  → SessionDetailPage
  └── /playbook/editor → PlaybookEditorPage
```

No auth guards needed (local tool, no login).

## Components Ported from Vue

| Vue Component | React Component | Notes |
|---|---|---|
| App.vue | main-layout.tsx + sidebar.tsx | Layout restructured to sidebar |
| HomePage.vue | pages/home.tsx | Tailwind styling |
| SessionsPage.vue | pages/session-list.tsx | PrimeVue → Radix/custom |
| DevSessionPage.vue | pages/session-detail.tsx | Same 3-panel layout |
| PlaybookEditorPage.vue | pages/playbook-editor.tsx | Same 3-column layout |
| ActionPalette.vue | playbook/action-palette.tsx | PrimeVue Accordion → custom |
| ActionPaletteItem.vue | playbook/action-palette-item.tsx | dnd-kit draggable |
| PlaybookCanvas.vue | playbook/playbook-canvas.tsx | dnd-kit sortable |
| PlaybookActionItem.vue | playbook/playbook-action-item.tsx | Same display logic |
| ActionConfigPanel.vue | playbook/action-config-panel.tsx | Tabs → custom/Radix |
| ActionConfigForm.vue | playbook/action-config-form.tsx | Form router |
| ClickActionForm.vue | actions/click-action-form.tsx | react-hook-form |
| KeyboardActionForm.vue | actions/keyboard-action-form.tsx | react-hook-form |
| WaitActionForm.vue | actions/wait-action-form.tsx | react-hook-form |
| ScreenshotActionForm.vue | actions/screenshot-action-form.tsx | react-hook-form |
| CommandActionForm.vue | actions/command-action-form.tsx | react-hook-form |
| GenericActionForm.vue | actions/generic-action-form.tsx | react-hook-form |
| CheckpointPanel.vue | checkpoint/checkpoint-panel.tsx | TanStack Query |
| ExecutionLog.vue | execution/execution-log.tsx | Zustand store |
| VariablesPanel.vue | session detail inline | Simplified |
| EmptyState.vue | shared/empty-state.tsx | Direct port |
| TargetInput.vue | shared/target-input.tsx | react-hook-form |
| StrategySelector.vue | shared/strategy-selector.tsx | react-hook-form |

## Vite Config

```typescript
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/ws': { target: 'ws://127.0.0.1:8000', ws: true },
    },
  },
})
```

## Verification

1. `cd adare-web && npm install && npm run dev` — app starts without errors
2. All 4 pages render and navigate correctly
3. Sidebar collapses/expands with smooth transition
4. All 4 theme variants work (light/dark x default/teal)
5. Theme and sidebar state persist across page refresh
6. `npm run build` — production build succeeds with no TS errors
