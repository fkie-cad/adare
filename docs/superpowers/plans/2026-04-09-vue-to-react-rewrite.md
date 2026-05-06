# ADARE Web: Vue-to-React Frontend Rewrite

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Vue 3 + PrimeVue frontend in `adare-web/` with React 19, matching `adare-server/frontend_react/` patterns, adding collapsible sidebar and 4-variant theme system.

**Architecture:** Scaffold a fresh React + Vite project in `adare-web/`, port all 4 pages and 18 components using the same TanStack/Zustand/Tailwind stack as `adare-server/frontend_react/`. API layer uses React Query hooks wrapping axios. WebSocket service ported as-is. Layout uses collapsible sidebar instead of top header.

**Tech Stack:** React 19, TypeScript 5.9, Vite 8, TanStack Router + Query, Zustand 5, Tailwind CSS 4, CVA, Radix UI, Lucide, @dnd-kit, react-hook-form + zod, axios

**Reference codebase:** `/Users/miq/Documents/Projects/ADARE/adare-server/frontend_react/`

**IMPORTANT:** Work on `dev` branch. Use git worktrees for feature work per CLAUDE.md.

---

## File Map

### Config files (create fresh)
- `adare-web/package.json`
- `adare-web/index.html`
- `adare-web/vite.config.ts`
- `adare-web/tsconfig.json`
- `adare-web/tsconfig.app.json`
- `adare-web/tsconfig.node.json`

### Core source files (create)
- `src/main.tsx` — React entry point
- `src/app.tsx` — QueryClient + Router providers
- `src/lib/utils.ts` — `cn()` utility
- `src/styles/globals.css` — Tailwind + 4 theme variants

### Types (port from Vue, unchanged)
- `src/types/api.ts`
- `src/types/action.ts`
- `src/types/session.ts`

### API layer (new React Query pattern)
- `src/api/client.ts` — Axios instance
- `src/api/endpoints.ts` — Path constants
- `src/api/hooks/use-sessions.ts`
- `src/api/hooks/use-checkpoints.ts`
- `src/api/hooks/use-actions.ts`
- `src/api/hooks/use-playbook.ts`

### Stores (Zustand)
- `src/stores/theme-store.ts` — mode + colorScheme
- `src/stores/sidebar-store.ts` — collapsed state
- `src/stores/playbook-store.ts` — editor state
- `src/stores/execution-store.ts` — execution log

### Services
- `src/services/websocket.ts` — WebSocketClient + Manager (ported from Vue)

### Routes
- `src/routes/route-tree.tsx`
- `src/routes/index.ts`

### Layout components
- `src/components/layout/main-layout.tsx`
- `src/components/layout/sidebar.tsx`
- `src/components/layout/sidebar-item.tsx`

### UI primitives (Radix + CVA)
- `src/components/ui/button.tsx`
- `src/components/ui/card.tsx`
- `src/components/ui/input.tsx`
- `src/components/ui/textarea.tsx`
- `src/components/ui/badge.tsx`
- `src/components/ui/dialog.tsx`
- `src/components/ui/separator.tsx`
- `src/components/ui/tooltip.tsx`
- `src/components/ui/scroll-area.tsx`
- `src/components/ui/theme-toggle.tsx`

### Pages
- `src/pages/home.tsx`
- `src/pages/session-list.tsx`
- `src/pages/session-detail.tsx`
- `src/pages/playbook-editor.tsx`

### Feature components
- `src/components/session/session-card.tsx`
- `src/components/session/start-session-dialog.tsx`
- `src/components/session/connection-status.tsx`
- `src/components/playbook/action-palette.tsx`
- `src/components/playbook/action-palette-item.tsx`
- `src/components/playbook/playbook-canvas.tsx`
- `src/components/playbook/playbook-action-item.tsx`
- `src/components/playbook/action-config-panel.tsx`
- `src/components/playbook/action-config-form.tsx`
- `src/components/actions/click-action-form.tsx`
- `src/components/actions/keyboard-action-form.tsx`
- `src/components/actions/wait-action-form.tsx`
- `src/components/actions/screenshot-action-form.tsx`
- `src/components/actions/command-action-form.tsx`
- `src/components/actions/generic-action-form.tsx`
- `src/components/checkpoint/checkpoint-panel.tsx`
- `src/components/execution/execution-log.tsx`
- `src/components/shared/empty-state.tsx`
- `src/components/shared/target-input.tsx`
- `src/components/shared/strategy-selector.tsx`

---

## Task 1: Delete Vue code and scaffold React project

**Files:**
- Delete: all files in `adare-web/` except `.gitkeep` if any
- Create: `adare-web/package.json`, `adare-web/index.html`, `adare-web/vite.config.ts`, `adare-web/tsconfig.json`, `adare-web/tsconfig.app.json`, `adare-web/tsconfig.node.json`, `adare-web/.gitignore`

- [ ] **Step 1: Remove all Vue source files**

```bash
cd adare-web
rm -rf src/ node_modules/ package.json package-lock.json tsconfig.json tsconfig.*.json vite.config.ts index.html
```

- [ ] **Step 2: Create package.json**

```json
{
  "name": "adare-web",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview",
    "type-check": "tsc --noEmit"
  },
  "dependencies": {
    "@dnd-kit/core": "^6.3.1",
    "@dnd-kit/sortable": "^10.0.0",
    "@dnd-kit/utilities": "^3.2.2",
    "@fontsource-variable/inter": "^5.2.8",
    "@hookform/resolvers": "^5.2.2",
    "@radix-ui/react-dialog": "^1.1.14",
    "@radix-ui/react-separator": "^1.1.7",
    "@radix-ui/react-slot": "^1.2.4",
    "@radix-ui/react-tabs": "^1.1.12",
    "@radix-ui/react-tooltip": "^1.2.7",
    "@tanstack/react-query": "^5.95.2",
    "@tanstack/react-router": "^1.168.8",
    "axios": "^1.14.0",
    "class-variance-authority": "^0.7.1",
    "clsx": "^2.1.1",
    "lucide-react": "^1.7.0",
    "react": "^19.2.4",
    "react-dom": "^19.2.4",
    "react-hook-form": "^7.72.0",
    "tailwind-merge": "^3.5.0",
    "yaml": "^2.3.4",
    "zod": "^4.3.6",
    "zustand": "^5.0.12"
  },
  "devDependencies": {
    "@tailwindcss/vite": "^4.2.2",
    "@types/node": "^24.12.0",
    "@types/react": "^19.2.14",
    "@types/react-dom": "^19.2.3",
    "@vitejs/plugin-react": "^6.0.1",
    "tailwindcss": "^4.2.2",
    "typescript": "~5.9.3",
    "vite": "^8.0.1"
  }
}
```

- [ ] **Step 3: Create index.html**

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <link rel="icon" href="/favicon.ico" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>ADARE Web - Automated Desktop Analysis</title>
    <script>
      (function() {
        var mode = localStorage.getItem('adare-mode') || 'system';
        var scheme = localStorage.getItem('adare-color-scheme') || 'default';
        var dark = mode === 'dark' || (mode === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);
        if (dark) document.documentElement.classList.add('dark');
        if (scheme === 'teal') document.documentElement.classList.add('teal');
      })();
    </script>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 4: Create vite.config.ts**

```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://127.0.0.1:8000',
        ws: true,
      },
    },
  },
})
```

- [ ] **Step 5: Create tsconfig.json**

```json
{
  "files": [],
  "references": [
    { "path": "./tsconfig.app.json" },
    { "path": "./tsconfig.node.json" }
  ]
}
```

- [ ] **Step 6: Create tsconfig.app.json**

```json
{
  "compilerOptions": {
    "tsBuildInfoFile": "./node_modules/.tmp/tsconfig.app.tsbuildinfo",
    "target": "ES2023",
    "useDefineForClassFields": true,
    "lib": ["ES2023", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "types": ["vite/client"],
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "verbatimModuleSyntax": true,
    "moduleDetection": "force",
    "noEmit": true,
    "jsx": "react-jsx",
    "baseUrl": ".",
    "paths": {
      "@/*": ["./src/*"]
    },
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "erasableSyntaxOnly": true,
    "noFallthroughCasesInSwitch": true,
    "noUncheckedSideEffectImports": true
  },
  "include": ["src"]
}
```

- [ ] **Step 7: Create tsconfig.node.json**

```json
{
  "compilerOptions": {
    "tsBuildInfoFile": "./node_modules/.tmp/tsconfig.node.tsbuildinfo",
    "target": "ES2023",
    "lib": ["ES2023"],
    "module": "ESNext",
    "types": ["node"],
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "verbatimModuleSyntax": true,
    "moduleDetection": "force",
    "noEmit": true,
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "erasableSyntaxOnly": true,
    "noFallthroughCasesInSwitch": true,
    "noUncheckedSideEffectImports": true
  },
  "include": ["vite.config.ts"]
}
```

- [ ] **Step 8: Create .gitignore**

```
node_modules
dist
*.local
.vite
```

- [ ] **Step 9: Install dependencies**

```bash
cd adare-web && npm install
```

Expected: `node_modules/` created, no errors.

- [ ] **Step 10: Commit**

```bash
git add -A adare-web/
git commit -m "feat(adare-web): scaffold React project replacing Vue frontend"
```

---

## Task 2: Core infrastructure — globals.css, utils, entry point

**Files:**
- Create: `src/styles/globals.css`, `src/lib/utils.ts`, `src/main.tsx`, `src/app.tsx`

- [ ] **Step 1: Create src/styles/globals.css with 4 theme variants**

```css
@import "tailwindcss";
@import "@fontsource-variable/inter";

@theme {
  /* ===== Light Default (base) ===== */
  --color-background: oklch(1 0 0);
  --color-foreground: oklch(0.145 0.014 255);
  --color-card: oklch(1 0 0);
  --color-card-foreground: oklch(0.145 0.014 255);
  --color-popover: oklch(1 0 0);
  --color-popover-foreground: oklch(0.145 0.014 255);
  --color-primary: oklch(0.55 0.15 168);
  --color-primary-foreground: oklch(0.985 0 0);
  --color-secondary: oklch(0.50 0.15 255);
  --color-secondary-foreground: oklch(0.985 0 0);
  --color-muted: oklch(0.97 0.014 255);
  --color-muted-foreground: oklch(0.556 0.022 257);
  --color-accent: oklch(0.95 0.02 168);
  --color-accent-foreground: oklch(0.25 0.05 168);
  --color-destructive: oklch(0.45 0.22 25);
  --color-destructive-foreground: oklch(0.985 0 0);
  --color-border: oklch(0.922 0.013 255);
  --color-input: oklch(0.922 0.013 255);
  --color-ring: oklch(0.55 0.15 168);
  --color-sidebar: oklch(0.975 0.005 255);
  --color-sidebar-foreground: oklch(0.145 0.014 255);
  --color-sidebar-primary: oklch(0.55 0.15 168);
  --color-sidebar-primary-foreground: oklch(0.985 0 0);
  --color-sidebar-accent: oklch(0.95 0.02 168);
  --color-sidebar-accent-foreground: oklch(0.25 0.05 168);
  --color-sidebar-border: oklch(0.922 0.013 255);
  --color-sidebar-ring: oklch(0.55 0.15 168);
  --color-success: oklch(0.55 0.17 155);
  --color-success-foreground: oklch(0.985 0 0);
  --color-warning: oklch(0.75 0.18 85);
  --color-warning-foreground: oklch(0.25 0.05 85);

  --radius-sm: 0.25rem;
  --radius-md: 0.375rem;
  --radius-lg: 0.5rem;
  --radius-xl: 0.75rem;

  --color-brand: oklch(0.55 0.15 168);
}

/* ===== Dark Default (slate-teal blend) ===== */
.dark {
  --color-background: oklch(0.14 0.02 220);
  --color-foreground: oklch(0.93 0.01 220);
  --color-card: oklch(0.18 0.025 210);
  --color-card-foreground: oklch(0.93 0.01 220);
  --color-popover: oklch(0.18 0.025 210);
  --color-popover-foreground: oklch(0.93 0.01 220);
  --color-primary: oklch(0.55 0.15 168);
  --color-primary-foreground: oklch(0.93 0.01 220);
  --color-secondary: oklch(0.50 0.15 255);
  --color-secondary-foreground: oklch(0.93 0.01 220);
  --color-muted: oklch(0.22 0.025 210);
  --color-muted-foreground: oklch(0.65 0.03 210);
  --color-accent: oklch(0.22 0.04 180);
  --color-accent-foreground: oklch(0.85 0.05 168);
  --color-destructive: oklch(0.55 0.22 25);
  --color-destructive-foreground: oklch(0.93 0.01 220);
  --color-border: oklch(0.28 0.03 210);
  --color-input: oklch(0.28 0.03 210);
  --color-ring: oklch(0.55 0.15 168);
  --color-sidebar: oklch(0.12 0.018 220);
  --color-sidebar-foreground: oklch(0.93 0.01 220);
  --color-sidebar-primary: oklch(0.55 0.15 168);
  --color-sidebar-primary-foreground: oklch(0.93 0.01 220);
  --color-sidebar-accent: oklch(0.22 0.04 180);
  --color-sidebar-accent-foreground: oklch(0.85 0.05 168);
  --color-sidebar-border: oklch(0.28 0.03 210);
  --color-sidebar-ring: oklch(0.55 0.15 168);
  --color-success: oklch(0.55 0.17 155);
  --color-success-foreground: oklch(0.93 0.01 220);
  --color-warning: oklch(0.75 0.18 85);
  --color-warning-foreground: oklch(0.93 0.01 220);
}

/* ===== Light Teal ===== */
.teal {
  --color-background: oklch(0.97 0.02 168);
  --color-foreground: oklch(0.20 0.06 168);
  --color-card: oklch(0.95 0.025 168);
  --color-card-foreground: oklch(0.20 0.06 168);
  --color-popover: oklch(0.95 0.025 168);
  --color-popover-foreground: oklch(0.20 0.06 168);
  --color-muted: oklch(0.92 0.03 168);
  --color-muted-foreground: oklch(0.45 0.06 168);
  --color-accent: oklch(0.90 0.04 168);
  --color-accent-foreground: oklch(0.25 0.06 168);
  --color-border: oklch(0.85 0.04 168);
  --color-input: oklch(0.85 0.04 168);
  --color-sidebar: oklch(0.93 0.03 168);
  --color-sidebar-foreground: oklch(0.20 0.06 168);
  --color-sidebar-accent: oklch(0.88 0.05 168);
  --color-sidebar-accent-foreground: oklch(0.25 0.06 168);
  --color-sidebar-border: oklch(0.85 0.04 168);
}

/* ===== Dark Teal ===== */
.dark.teal {
  --color-background: oklch(0.12 0.04 168);
  --color-foreground: oklch(0.90 0.03 168);
  --color-card: oklch(0.16 0.05 168);
  --color-card-foreground: oklch(0.90 0.03 168);
  --color-popover: oklch(0.16 0.05 168);
  --color-popover-foreground: oklch(0.90 0.03 168);
  --color-muted: oklch(0.20 0.045 168);
  --color-muted-foreground: oklch(0.65 0.06 168);
  --color-accent: oklch(0.22 0.06 168);
  --color-accent-foreground: oklch(0.85 0.05 168);
  --color-border: oklch(0.25 0.05 168);
  --color-input: oklch(0.25 0.05 168);
  --color-sidebar: oklch(0.10 0.035 168);
  --color-sidebar-foreground: oklch(0.90 0.03 168);
  --color-sidebar-accent: oklch(0.22 0.06 168);
  --color-sidebar-accent-foreground: oklch(0.85 0.05 168);
  --color-sidebar-border: oklch(0.25 0.05 168);
}

@layer base {
  body {
    @apply bg-background text-foreground;
    font-family: 'Inter Variable', ui-sans-serif, system-ui, sans-serif;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
  }
}
```

- [ ] **Step 2: Create src/lib/utils.ts**

```typescript
import { type ClassValue, clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
```

- [ ] **Step 3: Create src/main.tsx**

```tsx
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '@/styles/globals.css'
import { App } from '@/app'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
```

- [ ] **Step 4: Create src/app.tsx**

```tsx
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { RouterProvider, createRouter } from '@tanstack/react-router'
import { routeTree } from '@/routes'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
    },
  },
})

const router = createRouter({
  routeTree,
  context: { queryClient },
})

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  )
}
```

- [ ] **Step 5: Commit**

```bash
git add src/styles/globals.css src/lib/utils.ts src/main.tsx src/app.tsx
git commit -m "feat(adare-web): add core infrastructure - globals.css, utils, entry point"
```

---

## Task 3: Type definitions (port from Vue)

**Files:**
- Create: `src/types/api.ts`, `src/types/action.ts`, `src/types/session.ts`

These are pure TypeScript — port as-is from the Vue project with no changes.

- [ ] **Step 1: Create src/types/api.ts**

Copy verbatim from `/Users/miq/Documents/Projects/ADARE/adare-web/src/types/api.ts` (Vue version). The imports reference `./action` and `./session` which will exist in the same directory.

- [ ] **Step 2: Create src/types/action.ts**

Copy verbatim from Vue version. No Vue-specific code.

- [ ] **Step 3: Create src/types/session.ts**

Copy verbatim from Vue version. No Vue-specific code.

- [ ] **Step 4: Commit**

```bash
git add src/types/
git commit -m "feat(adare-web): port type definitions from Vue frontend"
```

---

## Task 4: Zustand stores — theme, sidebar, playbook, execution

**Files:**
- Create: `src/stores/theme-store.ts`, `src/stores/sidebar-store.ts`, `src/stores/playbook-store.ts`, `src/stores/execution-store.ts`

- [ ] **Step 1: Create src/stores/theme-store.ts**

```typescript
import { create } from 'zustand'

type Mode = 'light' | 'dark' | 'system'
type ColorScheme = 'default' | 'teal'

interface ThemeState {
  mode: Mode
  colorScheme: ColorScheme
  setMode: (mode: Mode) => void
  setColorScheme: (scheme: ColorScheme) => void
}

function getSystemDark(): boolean {
  return window.matchMedia('(prefers-color-scheme: dark)').matches
}

function applyTheme(mode: Mode, colorScheme: ColorScheme): void {
  const isDark = mode === 'dark' || (mode === 'system' && getSystemDark())
  document.documentElement.classList.toggle('dark', isDark)
  document.documentElement.classList.toggle('teal', colorScheme === 'teal')
}

export const useThemeStore = create<ThemeState>((set) => {
  const storedMode = (localStorage.getItem('adare-mode') as Mode | null) ?? 'system'
  const storedScheme = (localStorage.getItem('adare-color-scheme') as ColorScheme | null) ?? 'default'
  applyTheme(storedMode, storedScheme)

  const mq = window.matchMedia('(prefers-color-scheme: dark)')
  mq.addEventListener('change', () => {
    const { mode, colorScheme } = useThemeStore.getState()
    if (mode === 'system') applyTheme('system', colorScheme)
  })

  return {
    mode: storedMode,
    colorScheme: storedScheme,
    setMode: (mode: Mode) => {
      localStorage.setItem('adare-mode', mode)
      const { colorScheme } = useThemeStore.getState()
      applyTheme(mode, colorScheme)
      set({ mode })
    },
    setColorScheme: (colorScheme: ColorScheme) => {
      localStorage.setItem('adare-color-scheme', colorScheme)
      const { mode } = useThemeStore.getState()
      applyTheme(mode, colorScheme)
      set({ colorScheme })
    },
  }
})
```

- [ ] **Step 2: Create src/stores/sidebar-store.ts**

```typescript
import { create } from 'zustand'

interface SidebarState {
  collapsed: boolean
  toggle: () => void
}

export const useSidebarStore = create<SidebarState>((set) => {
  const stored = localStorage.getItem('adare-sidebar-collapsed')
  return {
    collapsed: stored === 'true',
    toggle: () =>
      set((state) => {
        const next = !state.collapsed
        localStorage.setItem('adare-sidebar-collapsed', String(next))
        return { collapsed: next }
      }),
  }
})
```

- [ ] **Step 3: Create src/stores/playbook-store.ts**

```typescript
import { create } from 'zustand'
import { stringify } from 'yaml'
import type { Action, ActionTypeMetadata } from '@/types/action'

interface PlaybookState {
  actions: Action[]
  selectedActionIndex: number | null
  variables: Record<string, unknown>
  playbookName: string
  isDirty: boolean
  actionTypes: ActionTypeMetadata[]

  setActionTypes: (types: ActionTypeMetadata[]) => void
  addAction: (action: Action, index?: number) => void
  removeAction: (index: number) => void
  updateAction: (index: number, action: Action) => void
  reorderActions: (newOrder: Action[]) => void
  selectAction: (index: number | null) => void
  setVariable: (name: string, value: unknown) => void
  removeVariable: (name: string) => void
  clearVariables: () => void
  exportToYAML: () => string
  clearPlaybook: () => void
  setPlaybookName: (name: string) => void
  markClean: () => void
}

export const usePlaybookStore = create<PlaybookState>((set, get) => ({
  actions: [],
  selectedActionIndex: null,
  variables: {},
  playbookName: 'untitled',
  isDirty: false,
  actionTypes: [],

  setActionTypes: (types) => set({ actionTypes: types }),

  addAction: (action, index) =>
    set((state) => {
      const actions = [...state.actions]
      if (index !== undefined) {
        actions.splice(index, 0, action)
      } else {
        actions.push(action)
      }
      return { actions, isDirty: true }
    }),

  removeAction: (index) =>
    set((state) => {
      const actions = state.actions.filter((_, i) => i !== index)
      const selectedActionIndex =
        state.selectedActionIndex === index ? null : state.selectedActionIndex
      return { actions, selectedActionIndex, isDirty: true }
    }),

  updateAction: (index, action) =>
    set((state) => {
      const actions = [...state.actions]
      actions[index] = action
      return { actions, isDirty: true }
    }),

  reorderActions: (newOrder) => set({ actions: newOrder, isDirty: true }),

  selectAction: (index) => set({ selectedActionIndex: index }),

  setVariable: (name, value) =>
    set((state) => ({
      variables: { ...state.variables, [name]: value },
    })),

  removeVariable: (name) =>
    set((state) => {
      const { [name]: _, ...rest } = state.variables
      return { variables: rest }
    }),

  clearVariables: () => set({ variables: {} }),

  exportToYAML: () => {
    const { actions, variables } = get()
    return stringify({ actions, variables })
  },

  clearPlaybook: () =>
    set({
      actions: [],
      selectedActionIndex: null,
      variables: {},
      playbookName: 'untitled',
      isDirty: false,
    }),

  setPlaybookName: (name) => set({ playbookName: name }),
  markClean: () => set({ isDirty: false }),
}))
```

- [ ] **Step 4: Create src/stores/execution-store.ts**

```typescript
import { create } from 'zustand'
import type { ExecutionLogEntry } from '@/types/api'
import type { ActionResult } from '@/types/action'

interface ExecutionState {
  log: ExecutionLogEntry[]
  addExecution: (actionType: string, description?: string) => string
  updateExecution: (id: string, status: 'success' | 'error', result?: ActionResult) => void
  clearLog: () => void
}

const MAX_LOG_SIZE = 1000

export const useExecutionStore = create<ExecutionState>((set) => ({
  log: [],

  addExecution: (actionType, description) => {
    const id = crypto.randomUUID()
    const entry: ExecutionLogEntry = {
      id,
      timestamp: new Date().toISOString(),
      action_type: actionType,
      description,
      status: 'running',
    }
    set((state) => ({
      log: [entry, ...state.log].slice(0, MAX_LOG_SIZE),
    }))
    return id
  },

  updateExecution: (id, status, result) =>
    set((state) => ({
      log: state.log.map((entry) =>
        entry.id === id
          ? {
              ...entry,
              status,
              result,
              duration_ms: result?.execution_time
                ? result.execution_time * 1000
                : Date.now() - new Date(entry.timestamp).getTime(),
            }
          : entry,
      ),
    })),

  clearLog: () => set({ log: [] }),
}))
```

- [ ] **Step 5: Commit**

```bash
git add src/stores/
git commit -m "feat(adare-web): add Zustand stores - theme, sidebar, playbook, execution"
```

---

## Task 5: API layer — client, endpoints, React Query hooks

**Files:**
- Create: `src/api/client.ts`, `src/api/endpoints.ts`, `src/api/hooks/use-sessions.ts`, `src/api/hooks/use-checkpoints.ts`, `src/api/hooks/use-actions.ts`, `src/api/hooks/use-playbook.ts`

- [ ] **Step 1: Create src/api/client.ts**

```typescript
import axios from 'axios'

export const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
})

api.interceptors.request.use((config) => {
  config.params = { ...config.params, _t: Date.now() }
  return config
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    const data = error.response?.data
    const message = data?.error ?? data?.message ?? data?.detail ?? error.message ?? 'Unknown error'
    return Promise.reject(new Error(message))
  },
)
```

- [ ] **Step 2: Create src/api/endpoints.ts**

```typescript
export const endpoints = {
  sessions: '/sessions',
  sessionState: (id: string) => `/sessions/${id}/state`,
  sessionStart: '/sessions/start',
  sessionStop: (id: string) => `/sessions/${id}/stop`,
  sessionReset: (id: string, type: string) => `/sessions/${id}/reset?type=${type}`,
  sessionCleanup: '/sessions/cleanup',
  checkpoints: (id: string) => `/sessions/${id}/checkpoints`,
  checkpointRestore: (id: string, name: string) => `/sessions/${id}/checkpoints/${name}/restore`,
  checkpointDelete: (id: string, name: string) => `/sessions/${id}/checkpoints/${name}`,
  actionExecute: (id: string) => `/sessions/${id}/actions/execute`,
  playbookExecute: (id: string) => `/sessions/${id}/playbooks/execute`,
  actionTypes: '/actions/types',
  playbookSave: '/playbooks/save',
  playbookLoad: (name: string) => `/playbooks/${name}`,
  health: '/health',
} as const
```

- [ ] **Step 3: Create src/api/hooks/use-sessions.ts**

```typescript
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/api/client'
import { endpoints } from '@/api/endpoints'
import type { ApiResponse } from '@/types/api'
import type { DevSessionListItem, DevSessionInfo, SessionState, StartSessionRequest } from '@/types/session'

export function useSessions() {
  return useQuery({
    queryKey: ['sessions'],
    queryFn: async () => {
      const { data } = await api.get<ApiResponse<DevSessionListItem[]>>(endpoints.sessions)
      return data.data ?? []
    },
    refetchInterval: 10_000,
  })
}

export function useSessionState(sessionId: string) {
  return useQuery({
    queryKey: ['session-state', sessionId],
    queryFn: async () => {
      const { data } = await api.get<ApiResponse<SessionState>>(endpoints.sessionState(sessionId))
      return data.data!
    },
    enabled: !!sessionId,
  })
}

export function useStartSession() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (request: StartSessionRequest) => {
      const { data } = await api.post<ApiResponse<DevSessionInfo>>(endpoints.sessionStart, request)
      return data.data!
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sessions'] }),
  })
}

export function useStopSession() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (sessionId: string) => {
      await api.post(endpoints.sessionStop(sessionId))
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sessions'] }),
  })
}

export function useResetSession() {
  return useMutation({
    mutationFn: async ({ sessionId, type }: { sessionId: string; type: 'soft' | 'hard' }) => {
      await api.post(endpoints.sessionReset(sessionId, type))
    },
  })
}

export function useCleanupSessions() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      const { data } = await api.post<ApiResponse<number>>(endpoints.sessionCleanup)
      return data.data ?? 0
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sessions'] }),
  })
}
```

- [ ] **Step 4: Create src/api/hooks/use-checkpoints.ts**

```typescript
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/api/client'
import { endpoints } from '@/api/endpoints'
import type { ApiResponse, CreateCheckpointRequest } from '@/types/api'
import type { CheckpointInfo } from '@/types/session'

export function useCheckpoints(sessionId: string) {
  return useQuery({
    queryKey: ['checkpoints', sessionId],
    queryFn: async () => {
      const { data } = await api.get<ApiResponse<CheckpointInfo[]>>(endpoints.checkpoints(sessionId))
      return data.data ?? []
    },
    enabled: !!sessionId,
  })
}

export function useCreateCheckpoint(sessionId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (request: CreateCheckpointRequest) => {
      const { data } = await api.post<ApiResponse<CheckpointInfo>>(endpoints.checkpoints(sessionId), request)
      return data.data!
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['checkpoints', sessionId] }),
  })
}

export function useRestoreCheckpoint(sessionId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (name: string) => {
      await api.post(endpoints.checkpointRestore(sessionId, name))
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['checkpoints', sessionId] }),
  })
}

export function useDeleteCheckpoint(sessionId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (name: string) => {
      await api.delete(endpoints.checkpointDelete(sessionId, name))
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['checkpoints', sessionId] }),
  })
}
```

- [ ] **Step 5: Create src/api/hooks/use-actions.ts**

```typescript
import { useQuery, useMutation } from '@tanstack/react-query'
import { api } from '@/api/client'
import { endpoints } from '@/api/endpoints'
import type { ApiResponse, ExecuteActionRequest } from '@/types/api'
import type { ActionResult, ActionTypeMetadata } from '@/types/action'

export function useActionTypes() {
  return useQuery({
    queryKey: ['action-types'],
    queryFn: async () => {
      const { data } = await api.get<ApiResponse<ActionTypeMetadata[]>>(endpoints.actionTypes)
      return data.data ?? []
    },
    staleTime: Infinity,
  })
}

export function useExecuteAction(sessionId: string) {
  return useMutation({
    mutationFn: async (request: ExecuteActionRequest) => {
      const { data } = await api.post<ApiResponse<ActionResult>>(endpoints.actionExecute(sessionId), request)
      return data.data!
    },
  })
}
```

- [ ] **Step 6: Create src/api/hooks/use-playbook.ts**

```typescript
import { useQuery, useMutation } from '@tanstack/react-query'
import { api } from '@/api/client'
import { endpoints } from '@/api/endpoints'
import type { ApiResponse, SavePlaybookRequest } from '@/types/api'

export function useLoadPlaybook(name: string) {
  return useQuery({
    queryKey: ['playbook', name],
    queryFn: async () => {
      const { data } = await api.get<ApiResponse<string>>(endpoints.playbookLoad(name))
      return data.data ?? ''
    },
    enabled: !!name,
  })
}

export function useSavePlaybook() {
  return useMutation({
    mutationFn: async (request: SavePlaybookRequest) => {
      const { data } = await api.post<ApiResponse<string>>(endpoints.playbookSave, request)
      return data.data
    },
  })
}
```

- [ ] **Step 7: Commit**

```bash
git add src/api/
git commit -m "feat(adare-web): add API layer - axios client and React Query hooks"
```

---

## Task 6: WebSocket service (port from Vue)

**Files:**
- Create: `src/services/websocket.ts`

- [ ] **Step 1: Create src/services/websocket.ts**

Port the `WebSocketClient` and `WebSocketManager` classes verbatim from the Vue version at `adare-web/src/services/websocket.ts`. These are pure TypeScript classes with no Vue dependencies — copy as-is. The import path changes from `@/types/api` which is the same in both projects.

- [ ] **Step 2: Commit**

```bash
git add src/services/
git commit -m "feat(adare-web): port WebSocket service from Vue frontend"
```

---

## Task 7: UI primitives — button, card, input, textarea, badge, dialog, separator, tooltip, scroll-area

**Files:**
- Create: all files in `src/components/ui/`

- [ ] **Step 1: Create src/components/ui/button.tsx**

Copy from adare-server reference: `/Users/miq/Documents/Projects/ADARE/adare-server/frontend_react/src/components/ui/button.tsx`. Same exact component.

- [ ] **Step 2: Create src/components/ui/card.tsx**

Copy from adare-server reference. Same exact component.

- [ ] **Step 3: Create src/components/ui/input.tsx**

Copy from adare-server reference. Same exact component.

- [ ] **Step 4: Create src/components/ui/badge.tsx**

Copy from adare-server reference. Same exact component.

- [ ] **Step 5: Create src/components/ui/textarea.tsx**

```tsx
import * as React from 'react'
import { cn } from '@/lib/utils'

const Textarea = React.forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(
  ({ className, ...props }, ref) => {
    return (
      <textarea
        className={cn(
          'flex min-h-[60px] w-full rounded-md border border-input bg-transparent px-3 py-2 text-base shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50 md:text-sm',
          className,
        )}
        ref={ref}
        {...props}
      />
    )
  },
)
Textarea.displayName = 'Textarea'

export { Textarea }
```

- [ ] **Step 6: Create src/components/ui/dialog.tsx**

```tsx
import * as React from 'react'
import * as DialogPrimitive from '@radix-ui/react-dialog'
import { X } from 'lucide-react'
import { cn } from '@/lib/utils'

const Dialog = DialogPrimitive.Root
const DialogTrigger = DialogPrimitive.Trigger
const DialogPortal = DialogPrimitive.Portal
const DialogClose = DialogPrimitive.Close

const DialogOverlay = React.forwardRef<
  React.ComponentRef<typeof DialogPrimitive.Overlay>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Overlay>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Overlay
    ref={ref}
    className={cn(
      'fixed inset-0 z-50 bg-black/80 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0',
      className,
    )}
    {...props}
  />
))
DialogOverlay.displayName = DialogPrimitive.Overlay.displayName

const DialogContent = React.forwardRef<
  React.ComponentRef<typeof DialogPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Content>
>(({ className, children, ...props }, ref) => (
  <DialogPortal>
    <DialogOverlay />
    <DialogPrimitive.Content
      ref={ref}
      className={cn(
        'fixed left-[50%] top-[50%] z-50 grid w-full max-w-lg translate-x-[-50%] translate-y-[-50%] gap-4 border bg-background p-6 shadow-lg duration-200 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95 data-[state=closed]:slide-out-to-left-1/2 data-[state=closed]:slide-out-to-top-[48%] data-[state=open]:slide-in-from-left-1/2 data-[state=open]:slide-in-from-top-[48%] sm:rounded-lg',
        className,
      )}
      {...props}
    >
      {children}
      <DialogPrimitive.Close className="absolute right-4 top-4 rounded-sm opacity-70 ring-offset-background transition-opacity hover:opacity-100 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 disabled:pointer-events-none data-[state=open]:bg-accent data-[state=open]:text-muted-foreground">
        <X className="h-4 w-4" />
        <span className="sr-only">Close</span>
      </DialogPrimitive.Close>
    </DialogPrimitive.Content>
  </DialogPortal>
))
DialogContent.displayName = DialogPrimitive.Content.displayName

const DialogHeader = ({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) => (
  <div className={cn('flex flex-col space-y-1.5 text-center sm:text-left', className)} {...props} />
)

const DialogFooter = ({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) => (
  <div className={cn('flex flex-col-reverse sm:flex-row sm:justify-end sm:space-x-2', className)} {...props} />
)

const DialogTitle = React.forwardRef<
  React.ComponentRef<typeof DialogPrimitive.Title>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Title>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Title ref={ref} className={cn('text-lg font-semibold leading-none tracking-tight', className)} {...props} />
))
DialogTitle.displayName = DialogPrimitive.Title.displayName

const DialogDescription = React.forwardRef<
  React.ComponentRef<typeof DialogPrimitive.Description>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Description>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Description ref={ref} className={cn('text-sm text-muted-foreground', className)} {...props} />
))
DialogDescription.displayName = DialogPrimitive.Description.displayName

export { Dialog, DialogPortal, DialogOverlay, DialogClose, DialogTrigger, DialogContent, DialogHeader, DialogFooter, DialogTitle, DialogDescription }
```

- [ ] **Step 7: Create src/components/ui/separator.tsx**

```tsx
import * as React from 'react'
import * as SeparatorPrimitive from '@radix-ui/react-separator'
import { cn } from '@/lib/utils'

const Separator = React.forwardRef<
  React.ComponentRef<typeof SeparatorPrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof SeparatorPrimitive.Root>
>(({ className, orientation = 'horizontal', decorative = true, ...props }, ref) => (
  <SeparatorPrimitive.Root
    ref={ref}
    decorative={decorative}
    orientation={orientation}
    className={cn(
      'shrink-0 bg-border',
      orientation === 'horizontal' ? 'h-[1px] w-full' : 'h-full w-[1px]',
      className,
    )}
    {...props}
  />
))
Separator.displayName = SeparatorPrimitive.Root.displayName

export { Separator }
```

- [ ] **Step 8: Create src/components/ui/tooltip.tsx**

```tsx
import * as React from 'react'
import * as TooltipPrimitive from '@radix-ui/react-tooltip'
import { cn } from '@/lib/utils'

const TooltipProvider = TooltipPrimitive.Provider
const Tooltip = TooltipPrimitive.Root
const TooltipTrigger = TooltipPrimitive.Trigger

const TooltipContent = React.forwardRef<
  React.ComponentRef<typeof TooltipPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof TooltipPrimitive.Content>
>(({ className, sideOffset = 4, ...props }, ref) => (
  <TooltipPrimitive.Content
    ref={ref}
    sideOffset={sideOffset}
    className={cn(
      'z-50 overflow-hidden rounded-md bg-primary px-3 py-1.5 text-xs text-primary-foreground animate-in fade-in-0 zoom-in-95 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95',
      className,
    )}
    {...props}
  />
))
TooltipContent.displayName = TooltipPrimitive.Content.displayName

export { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider }
```

- [ ] **Step 9: Create src/components/ui/scroll-area.tsx**

```tsx
import * as React from 'react'
import { cn } from '@/lib/utils'

interface ScrollAreaProps extends React.HTMLAttributes<HTMLDivElement> {
  orientation?: 'vertical' | 'horizontal'
}

const ScrollArea = React.forwardRef<HTMLDivElement, ScrollAreaProps>(
  ({ className, children, ...props }, ref) => (
    <div ref={ref} className={cn('relative overflow-auto', className)} {...props}>
      {children}
    </div>
  ),
)
ScrollArea.displayName = 'ScrollArea'

export { ScrollArea }
```

- [ ] **Step 10: Create src/components/ui/theme-toggle.tsx**

```tsx
import { Sun, Moon, Monitor, Palette, Droplets } from 'lucide-react'
import { useThemeStore } from '@/stores/theme-store'
import { cn } from '@/lib/utils'

type Mode = 'light' | 'dark' | 'system'
type ColorScheme = 'default' | 'teal'

const modeOptions: { value: Mode; icon: typeof Sun; label: string }[] = [
  { value: 'light', icon: Sun, label: 'Light' },
  { value: 'dark', icon: Moon, label: 'Dark' },
  { value: 'system', icon: Monitor, label: 'System' },
]

const schemeOptions: { value: ColorScheme; icon: typeof Palette; label: string }[] = [
  { value: 'default', icon: Palette, label: 'Default' },
  { value: 'teal', icon: Droplets, label: 'Teal' },
]

export function ThemeToggle({ collapsed = false }: { collapsed?: boolean }) {
  const { mode, colorScheme, setMode, setColorScheme } = useThemeStore()

  return (
    <div className={cn('flex flex-col gap-2', collapsed ? 'items-center' : 'px-3 py-2')}>
      {!collapsed && <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Theme</span>}
      <div className="flex gap-0.5 rounded-md bg-muted p-0.5">
        {modeOptions.map(({ value, icon: Icon, label }) => (
          <button
            key={value}
            onClick={() => setMode(value)}
            className={cn(
              'rounded p-1.5 transition-colors',
              mode === value
                ? 'bg-background text-foreground shadow-sm'
                : 'text-muted-foreground hover:text-foreground',
            )}
            title={label}
          >
            <Icon className="h-3.5 w-3.5" />
          </button>
        ))}
      </div>
      <div className="flex gap-0.5 rounded-md bg-muted p-0.5">
        {schemeOptions.map(({ value, icon: Icon, label }) => (
          <button
            key={value}
            onClick={() => setColorScheme(value)}
            className={cn(
              'rounded p-1.5 transition-colors',
              colorScheme === value
                ? 'bg-background text-foreground shadow-sm'
                : 'text-muted-foreground hover:text-foreground',
            )}
            title={label}
          >
            <Icon className="h-3.5 w-3.5" />
          </button>
        ))}
      </div>
    </div>
  )
}
```

- [ ] **Step 11: Commit**

```bash
git add src/components/ui/
git commit -m "feat(adare-web): add UI primitives - button, card, input, dialog, etc."
```

---

## Task 8: Layout — collapsible sidebar + main layout

**Files:**
- Create: `src/components/layout/main-layout.tsx`, `src/components/layout/sidebar.tsx`, `src/components/layout/sidebar-item.tsx`

- [ ] **Step 1: Create src/components/layout/sidebar-item.tsx**

```tsx
import { Link } from '@tanstack/react-router'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'

interface SidebarItemProps {
  to: string
  label: string
  icon: React.ReactNode
  collapsed: boolean
}

export function SidebarItem({ to, label, icon, collapsed }: SidebarItemProps) {
  const link = (
    <Link
      to={to}
      className={cn(
        'flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors',
        'text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground',
        collapsed && 'justify-center px-2',
      )}
      activeProps={{
        className: cn(
          'flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors',
          'bg-sidebar-primary text-sidebar-primary-foreground',
          collapsed && 'justify-center px-2',
        ),
      }}
    >
      {icon}
      {!collapsed && <span>{label}</span>}
    </Link>
  )

  if (collapsed) {
    return (
      <Tooltip>
        <TooltipTrigger asChild>{link}</TooltipTrigger>
        <TooltipContent side="right">{label}</TooltipContent>
      </Tooltip>
    )
  }

  return link
}
```

- [ ] **Step 2: Create src/components/layout/sidebar.tsx**

```tsx
import { Home, MonitorPlay, FileCode, ChevronLeft, ChevronRight } from 'lucide-react'
import { useSidebarStore } from '@/stores/sidebar-store'
import { ThemeToggle } from '@/components/ui/theme-toggle'
import { Separator } from '@/components/ui/separator'
import { SidebarItem } from './sidebar-item'
import { cn } from '@/lib/utils'

const navItems = [
  { to: '/', label: 'Home', icon: <Home className="h-5 w-5" /> },
  { to: '/sessions', label: 'Sessions', icon: <MonitorPlay className="h-5 w-5" /> },
  { to: '/playbook/editor', label: 'Playbook Editor', icon: <FileCode className="h-5 w-5" /> },
]

export function Sidebar() {
  const { collapsed, toggle } = useSidebarStore()

  return (
    <aside
      className={cn(
        'flex flex-col h-screen bg-sidebar border-r border-sidebar-border transition-all duration-200',
        collapsed ? 'w-16' : 'w-60',
      )}
    >
      {/* Logo */}
      <div className={cn('flex items-center h-14 px-4 border-b border-sidebar-border', collapsed && 'justify-center px-2')}>
        {collapsed ? (
          <span className="text-lg font-bold text-sidebar-primary">A</span>
        ) : (
          <span className="text-lg font-semibold text-sidebar-foreground">ADARE Web</span>
        )}
      </div>

      {/* Navigation */}
      <nav className="flex-1 flex flex-col gap-1 p-2">
        {navItems.map((item) => (
          <SidebarItem key={item.to} {...item} collapsed={collapsed} />
        ))}
      </nav>

      {/* Footer */}
      <div className="mt-auto">
        <Separator />
        <div className="p-2">
          <ThemeToggle collapsed={collapsed} />
        </div>
        <Separator />
        <button
          onClick={toggle}
          className={cn(
            'flex items-center gap-2 w-full px-4 py-3 text-sm text-muted-foreground hover:text-foreground transition-colors',
            collapsed && 'justify-center px-2',
          )}
          title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {collapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
          {!collapsed && <span>Collapse</span>}
        </button>
      </div>
    </aside>
  )
}
```

- [ ] **Step 3: Create src/components/layout/main-layout.tsx**

```tsx
import { Outlet } from '@tanstack/react-router'
import { TooltipProvider } from '@/components/ui/tooltip'
import { Sidebar } from './sidebar'
import { useThemeStore } from '@/stores/theme-store'

export function MainLayout() {
  useThemeStore()

  return (
    <TooltipProvider delayDuration={0}>
      <div className="flex h-screen bg-background">
        <Sidebar />
        <main className="flex-1 overflow-auto">
          <Outlet />
        </main>
      </div>
    </TooltipProvider>
  )
}
```

- [ ] **Step 4: Commit**

```bash
git add src/components/layout/
git commit -m "feat(adare-web): add collapsible sidebar layout"
```

---

## Task 9: Routing + shared components + empty state

**Files:**
- Create: `src/routes/route-tree.tsx`, `src/routes/index.ts`, `src/components/shared/empty-state.tsx`

- [ ] **Step 1: Create src/routes/route-tree.tsx**

```tsx
import { createRootRouteWithContext, createRoute } from '@tanstack/react-router'
import type { QueryClient } from '@tanstack/react-query'
import { MainLayout } from '@/components/layout/main-layout'
import HomePage from '@/pages/home'
import SessionListPage from '@/pages/session-list'
import SessionDetailPage from '@/pages/session-detail'
import PlaybookEditorPage from '@/pages/playbook-editor'

interface RouterContext {
  queryClient: QueryClient
}

const rootRoute = createRootRouteWithContext<RouterContext>()({
  component: MainLayout,
})

const homeRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/',
  component: HomePage,
})

const sessionListRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/sessions',
  component: SessionListPage,
})

const sessionDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/session/$id',
  component: SessionDetailPage,
})

const playbookEditorRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/playbook/editor',
  component: PlaybookEditorPage,
})

export const routeTree = rootRoute.addChildren([
  homeRoute,
  sessionListRoute,
  sessionDetailRoute,
  playbookEditorRoute,
])
```

- [ ] **Step 2: Create src/routes/index.ts**

```typescript
export { routeTree } from './route-tree'
```

- [ ] **Step 3: Create src/components/shared/empty-state.tsx**

```tsx
import { cn } from '@/lib/utils'

interface EmptyStateProps {
  icon?: React.ReactNode
  title: string
  message: string
  children?: React.ReactNode
  className?: string
}

export function EmptyState({ icon, title, message, children, className }: EmptyStateProps) {
  return (
    <div className={cn('flex flex-col items-center justify-center py-16 text-center', className)}>
      {icon && <div className="mb-4 text-muted-foreground">{icon}</div>}
      <h2 className="text-lg font-semibold text-foreground">{title}</h2>
      <p className="mt-1 text-sm text-muted-foreground max-w-sm">{message}</p>
      {children && <div className="mt-6">{children}</div>}
    </div>
  )
}
```

- [ ] **Step 4: Create placeholder pages so the app compiles**

Create minimal placeholder pages (will be fully implemented in Tasks 10-13):

`src/pages/home.tsx`:
```tsx
export default function HomePage() {
  return <div className="p-6"><h1 className="text-2xl font-bold">ADARE Web</h1></div>
}
```

`src/pages/session-list.tsx`:
```tsx
export default function SessionListPage() {
  return <div className="p-6"><h1 className="text-2xl font-bold">Sessions</h1></div>
}
```

`src/pages/session-detail.tsx`:
```tsx
import { useParams } from '@tanstack/react-router'

export default function SessionDetailPage() {
  const { id } = useParams({ strict: false }) as { id: string }
  return <div className="p-6"><h1 className="text-2xl font-bold">Session: {id}</h1></div>
}
```

`src/pages/playbook-editor.tsx`:
```tsx
export default function PlaybookEditorPage() {
  return <div className="p-6"><h1 className="text-2xl font-bold">Playbook Editor</h1></div>
}
```

- [ ] **Step 5: Verify app compiles and runs**

```bash
cd adare-web && npm run dev
```

Expected: Vite dev server starts, browser shows sidebar + "ADARE Web" home page. Sidebar collapses/expands. Theme toggles work.

- [ ] **Step 6: Commit**

```bash
git add src/routes/ src/components/shared/ src/pages/
git commit -m "feat(adare-web): add routing, shared components, placeholder pages"
```

---

## Task 10: Home page

**Files:**
- Modify: `src/pages/home.tsx`

- [ ] **Step 1: Implement the full home page**

```tsx
import { Link } from '@tanstack/react-router'
import { GripVertical, Zap, Save, FileCode } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'

const features = [
  { icon: GripVertical, title: 'Drag & Drop', description: 'Visual playbook builder with 18+ action types' },
  { icon: Zap, title: 'Real-time Testing', description: 'Execute actions instantly and see results' },
  { icon: Save, title: 'Checkpoints', description: 'Save and restore VM state at any point' },
  { icon: FileCode, title: 'YAML Export', description: 'Export playbooks to YAML format' },
]

export default function HomePage() {
  return (
    <div className="min-h-full">
      {/* Hero */}
      <div className="bg-gradient-to-br from-indigo-500 to-purple-600 text-white px-8 py-16 text-center">
        <h1 className="text-4xl font-bold mb-4">ADARE Web Interface</h1>
        <p className="text-xl opacity-90">Build and test playbooks visually with drag-and-drop action builder</p>
      </div>

      <div className="max-w-5xl mx-auto px-6 py-8 space-y-12">
        {/* Quick Nav Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 -mt-12">
          <Card>
            <CardHeader>
              <CardTitle>Dev Sessions</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <p className="text-sm text-muted-foreground">Start interactive development sessions to build playbooks step-by-step.</p>
              <Button asChild>
                <Link to="/sessions">View Sessions</Link>
              </Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Playbook Editor</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <p className="text-sm text-muted-foreground">Create and edit playbooks with a visual action sequence builder.</p>
              <Button asChild>
                <Link to="/playbook/editor">Open Editor</Link>
              </Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Quick Start</CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="text-sm text-muted-foreground space-y-1.5 list-disc list-inside">
                <li>Start a new dev session</li>
                <li>Drag actions to build your playbook</li>
                <li>Test actions with the Test button</li>
                <li>Create checkpoints to save VM state</li>
                <li>Export your playbook to YAML</li>
              </ul>
            </CardContent>
          </Card>
        </div>

        {/* Features */}
        <div>
          <h2 className="text-2xl font-semibold text-center mb-8">Features</h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
            {features.map(({ icon: Icon, title, description }) => (
              <div key={title} className="text-center space-y-2">
                <Icon className="h-10 w-10 mx-auto text-primary" />
                <h3 className="font-semibold">{title}</h3>
                <p className="text-sm text-muted-foreground">{description}</p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Verify page renders**

```bash
cd adare-web && npm run dev
```

Open browser to `/` — hero, cards, and features grid should render with proper theming.

- [ ] **Step 3: Commit**

```bash
git add src/pages/home.tsx
git commit -m "feat(adare-web): implement home page"
```

---

## Task 11: Session list page + session components

**Files:**
- Modify: `src/pages/session-list.tsx`
- Create: `src/components/session/session-card.tsx`, `src/components/session/start-session-dialog.tsx`, `src/components/session/connection-status.tsx`

- [ ] **Step 1: Create src/components/session/connection-status.tsx**

```tsx
import { Wifi, WifiOff } from 'lucide-react'
import { cn } from '@/lib/utils'

export function ConnectionStatus({ connected }: { connected: boolean }) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-md px-2.5 py-0.5 text-xs font-medium',
        connected
          ? 'bg-success/10 text-success'
          : 'bg-destructive/10 text-destructive',
      )}
    >
      {connected ? <Wifi className="h-3 w-3" /> : <WifiOff className="h-3 w-3" />}
      {connected ? 'Connected' : 'Disconnected'}
    </span>
  )
}
```

- [ ] **Step 2: Create src/components/session/session-card.tsx**

```tsx
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ExternalLink, Square } from 'lucide-react'
import type { DevSessionListItem } from '@/types/session'

function formatUptime(seconds: number): string {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = seconds % 60
  return `${h}h ${m}m ${s}s`
}

interface SessionCardProps {
  session: DevSessionListItem
  onOpen: (id: string) => void
  onStop: (id: string) => void
}

export function SessionCard({ session, onOpen, onStop }: SessionCardProps) {
  const statusVariant = session.status === 'running' ? 'success' : session.status === 'error' ? 'destructive' : 'secondary'

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-base">
          {session.project} / {session.experiment}
        </CardTitle>
        <Badge variant={statusVariant}>{session.status}</Badge>
      </CardHeader>
      <CardContent className="space-y-1 text-sm text-muted-foreground">
        <p>{session.environment}</p>
        <p>ID: {session.session_id.substring(0, 8)}...</p>
        <p>Actions: {session.action_count}</p>
        <p>Uptime: {formatUptime(session.uptime_seconds)}</p>
        <p>Created: {new Date(session.created_at).toLocaleString()}</p>
      </CardContent>
      <CardFooter className="gap-2 justify-end">
        <Button size="sm" onClick={() => onOpen(session.session_id)}>
          <ExternalLink className="h-4 w-4" /> Open
        </Button>
        <Button size="sm" variant="destructive" onClick={() => onStop(session.session_id)}>
          <Square className="h-4 w-4" /> Stop
        </Button>
      </CardFooter>
    </Card>
  )
}
```

- [ ] **Step 3: Create src/components/session/start-session-dialog.tsx**

```tsx
import { useState } from 'react'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'

interface StartSessionDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSubmit: (data: { project_path: string; experiment_name: string; environment_name: string }) => void
  loading: boolean
}

export function StartSessionDialog({ open, onOpenChange, onSubmit, loading }: StartSessionDialogProps) {
  const [form, setForm] = useState({ project_path: '', experiment_name: '', environment_name: '' })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (form.project_path && form.experiment_name && form.environment_name) {
      onSubmit(form)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Start New Dev Session</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <label className="text-sm font-medium">Project Path</label>
            <Input placeholder="/path/to/project" value={form.project_path} onChange={(e) => setForm({ ...form, project_path: e.target.value })} />
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium">Experiment Name</label>
            <Input placeholder="my-experiment" value={form.experiment_name} onChange={(e) => setForm({ ...form, experiment_name: e.target.value })} />
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium">Environment Name</label>
            <Input placeholder="win10-env" value={form.environment_name} onChange={(e) => setForm({ ...form, environment_name: e.target.value })} />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button type="submit" disabled={loading}>{loading ? 'Starting...' : 'Start Session'}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
```

- [ ] **Step 4: Implement src/pages/session-list.tsx**

```tsx
import { useState } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { Plus, Trash2, RefreshCw, Inbox, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { EmptyState } from '@/components/shared/empty-state'
import { SessionCard } from '@/components/session/session-card'
import { StartSessionDialog } from '@/components/session/start-session-dialog'
import { useSessions, useStartSession, useStopSession, useCleanupSessions } from '@/api/hooks/use-sessions'

export default function SessionListPage() {
  const navigate = useNavigate()
  const [dialogOpen, setDialogOpen] = useState(false)

  const { data: sessions, isLoading, error, refetch } = useSessions()
  const startSession = useStartSession()
  const stopSession = useStopSession()
  const cleanupSessions = useCleanupSessions()

  const handleStart = (data: { project_path: string; experiment_name: string; environment_name: string }) => {
    startSession.mutate(data, {
      onSuccess: (session) => {
        setDialogOpen(false)
        navigate({ to: '/session/$id', params: { id: session.session_id } })
      },
    })
  }

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Dev Sessions</h1>
        <div className="flex gap-2">
          <Button onClick={() => setDialogOpen(true)}><Plus className="h-4 w-4" /> Start New Session</Button>
          <Button variant="outline" onClick={() => cleanupSessions.mutate()}><Trash2 className="h-4 w-4" /> Cleanup Stale</Button>
          <Button variant="outline" onClick={() => refetch()}><RefreshCw className="h-4 w-4" /> Refresh</Button>
        </div>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-16">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      ) : error ? (
        <div className="text-center py-16 text-destructive">Error: {error.message}</div>
      ) : !sessions?.length ? (
        <EmptyState
          icon={<Inbox className="h-12 w-12" />}
          title="No active sessions"
          message="Start a new dev session to begin building playbooks"
        >
          <Button onClick={() => setDialogOpen(true)}><Plus className="h-4 w-4" /> Start Session</Button>
        </EmptyState>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {sessions.map((session) => (
            <SessionCard
              key={session.session_id}
              session={session}
              onOpen={(id) => navigate({ to: '/session/$id', params: { id } })}
              onStop={(id) => stopSession.mutate(id)}
            />
          ))}
        </div>
      )}

      <StartSessionDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        onSubmit={handleStart}
        loading={startSession.isPending}
      />
    </div>
  )
}
```

- [ ] **Step 5: Commit**

```bash
git add src/pages/session-list.tsx src/components/session/
git commit -m "feat(adare-web): implement session list page with card grid and start dialog"
```

---

## Task 12: Session detail page + checkpoint panel + execution log

**Files:**
- Modify: `src/pages/session-detail.tsx`
- Create: `src/components/checkpoint/checkpoint-panel.tsx`, `src/components/execution/execution-log.tsx`

- [ ] **Step 1: Create src/components/checkpoint/checkpoint-panel.tsx**

```tsx
import { useState } from 'react'
import { Plus, RotateCcw, Trash2, Loader2, Database } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { EmptyState } from '@/components/shared/empty-state'
import { useCheckpoints, useCreateCheckpoint, useRestoreCheckpoint, useDeleteCheckpoint } from '@/api/hooks/use-checkpoints'

export function CheckpointPanel({ sessionId }: { sessionId: string }) {
  const { data: checkpoints, isLoading } = useCheckpoints(sessionId)
  const createCheckpoint = useCreateCheckpoint(sessionId)
  const restoreCheckpoint = useRestoreCheckpoint(sessionId)
  const deleteCheckpoint = useDeleteCheckpoint(sessionId)

  const [createOpen, setCreateOpen] = useState(false)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')

  const handleCreate = () => {
    if (!name.trim()) return
    createCheckpoint.mutate({ name, description: description || undefined }, {
      onSuccess: () => { setCreateOpen(false); setName(''); setDescription('') },
    })
  }

  if (isLoading) return <div className="flex justify-center py-4"><Loader2 className="h-5 w-5 animate-spin" /></div>

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold">Checkpoints</h3>
        <Button size="sm" variant="outline" onClick={() => setCreateOpen(true)}><Plus className="h-3 w-3" /></Button>
      </div>

      {!checkpoints?.length ? (
        <p className="text-xs text-muted-foreground">No checkpoints yet</p>
      ) : (
        <div className="space-y-2">
          {checkpoints.map((cp) => (
            <Card key={cp.name} className="p-3">
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-sm font-medium">{cp.name}</p>
                  {cp.description && <p className="text-xs text-muted-foreground">{cp.description}</p>}
                  <p className="text-xs text-muted-foreground mt-1">
                    {cp.disk_size_mb}MB disk / {cp.memory_size_mb}MB mem
                  </p>
                </div>
                <div className="flex gap-1">
                  <Button size="sm" variant="ghost" onClick={() => restoreCheckpoint.mutate(cp.name)} title="Restore">
                    <RotateCcw className="h-3 w-3" />
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => deleteCheckpoint.mutate(cp.name)} title="Delete">
                    <Trash2 className="h-3 w-3" />
                  </Button>
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent>
          <DialogHeader><DialogTitle>Create Checkpoint</DialogTitle></DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <label className="text-sm font-medium">Name</label>
              <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="checkpoint-1" />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium">Description (optional)</label>
              <Textarea value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Before installing updates..." />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateOpen(false)}>Cancel</Button>
            <Button onClick={handleCreate} disabled={createCheckpoint.isPending}>
              {createCheckpoint.isPending ? 'Creating...' : 'Create'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
```

- [ ] **Step 2: Create src/components/execution/execution-log.tsx**

```tsx
import { useRef, useEffect } from 'react'
import { CheckCircle, XCircle, Loader2, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { useExecutionStore } from '@/stores/execution-store'
import { cn } from '@/lib/utils'

export function ExecutionLog() {
  const { log, clearLog } = useExecutionStore()
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [log.length])

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold">Execution Log ({log.length})</h3>
        {log.length > 0 && (
          <Button size="sm" variant="ghost" onClick={clearLog}><Trash2 className="h-3 w-3" /></Button>
        )}
      </div>

      <ScrollArea className="max-h-64">
        {log.length === 0 ? (
          <p className="text-xs text-muted-foreground">No executions yet</p>
        ) : (
          <div className="space-y-1">
            {log.map((entry) => (
              <div key={entry.id} className="flex items-start gap-2 rounded-md border p-2 text-xs">
                {entry.status === 'running' && <Loader2 className="h-3.5 w-3.5 animate-spin text-primary mt-0.5" />}
                {entry.status === 'success' && <CheckCircle className="h-3.5 w-3.5 text-success mt-0.5" />}
                {entry.status === 'error' && <XCircle className="h-3.5 w-3.5 text-destructive mt-0.5" />}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between">
                    <span className="font-medium">{entry.action_type}</span>
                    {entry.duration_ms != null && (
                      <span className="text-muted-foreground">{(entry.duration_ms / 1000).toFixed(2)}s</span>
                    )}
                  </div>
                  {entry.description && <p className="text-muted-foreground truncate">{entry.description}</p>}
                  {entry.result?.error_message && (
                    <p className={cn('mt-1 text-destructive')}>{entry.result.error_message}</p>
                  )}
                </div>
              </div>
            ))}
            <div ref={bottomRef} />
          </div>
        )}
      </ScrollArea>
    </div>
  )
}
```

- [ ] **Step 3: Implement src/pages/session-detail.tsx**

```tsx
import { useState, useEffect } from 'react'
import { useParams, useNavigate } from '@tanstack/react-router'
import { RefreshCw, RotateCcw, Square, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { ConnectionStatus } from '@/components/session/connection-status'
import { CheckpointPanel } from '@/components/checkpoint/checkpoint-panel'
import { ExecutionLog } from '@/components/execution/execution-log'
import { useSessionState, useStopSession, useResetSession } from '@/api/hooks/use-sessions'
import { useExecuteAction } from '@/api/hooks/use-actions'
import { useExecutionStore } from '@/stores/execution-store'
import { wsManager } from '@/services/websocket'
import { useQueryClient } from '@tanstack/react-query'

export default function SessionDetailPage() {
  const { id } = useParams({ strict: false }) as { id: string }
  const navigate = useNavigate()
  const qc = useQueryClient()

  const { data: sessionState, isLoading } = useSessionState(id)
  const stopSession = useStopSession()
  const resetSession = useResetSession()
  const executeAction = useExecuteAction(id)
  const { addExecution, updateExecution } = useExecutionStore()

  const [yamlInput, setYamlInput] = useState('')
  const [connected, setConnected] = useState(false)

  useEffect(() => {
    const client = wsManager.getClient(id)
    client.connect()

    const onConnected = () => setConnected(true)
    const onDisconnected = () => setConnected(false)
    const onCheckpoint = () => qc.invalidateQueries({ queryKey: ['checkpoints', id] })
    const onSessionState = () => qc.invalidateQueries({ queryKey: ['session-state', id] })

    client.on('connected', onConnected)
    client.on('disconnected', onDisconnected)
    client.on('checkpoint_created', onCheckpoint)
    client.on('checkpoint_deleted', onCheckpoint)
    client.on('checkpoint_restored', onCheckpoint)
    client.on('session_state', onSessionState)

    return () => {
      client.off('connected', onConnected)
      client.off('disconnected', onDisconnected)
      client.off('checkpoint_created', onCheckpoint)
      client.off('checkpoint_deleted', onCheckpoint)
      client.off('checkpoint_restored', onCheckpoint)
      client.off('session_state', onSessionState)
      wsManager.removeClient(id)
    }
  }, [id, qc])

  const handleExecute = () => {
    if (!yamlInput.trim()) return
    const execId = addExecution('YAML', 'Quick execute')

    executeAction.mutate({ action_yaml: yamlInput }, {
      onSuccess: (result) => {
        updateExecution(execId, result.success ? 'success' : 'error', result)
        if (result.success) setYamlInput('')
      },
      onError: (err) => {
        updateExecution(execId, 'error', { success: false, message: err.message, execution_time: 0 })
      },
    })
  }

  if (isLoading) {
    return <div className="flex items-center justify-center h-full"><Loader2 className="h-8 w-8 animate-spin" /></div>
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-3 border-b bg-card">
        <div className="flex items-center gap-3">
          <h1 className="text-lg font-semibold">Session: {id.substring(0, 8)}...</h1>
          <ConnectionStatus connected={connected} />
        </div>
        <div className="flex gap-2">
          <Button variant="ghost" size="sm" onClick={() => resetSession.mutate({ sessionId: id, type: 'soft' })}>
            <RefreshCw className="h-4 w-4" /> Soft Reset
          </Button>
          <Button variant="ghost" size="sm" onClick={() => resetSession.mutate({ sessionId: id, type: 'hard' })}>
            <RotateCcw className="h-4 w-4" /> Hard Reset
          </Button>
          <Button variant="destructive" size="sm" onClick={() => stopSession.mutate(id, { onSuccess: () => navigate({ to: '/sessions' }) })}>
            <Square className="h-4 w-4" /> Stop
          </Button>
        </div>
      </div>

      {/* 3-panel layout */}
      <div className="flex-1 grid grid-cols-[250px_1fr_350px] gap-4 p-4 overflow-hidden">
        {/* Left: Action list placeholder */}
        <div className="bg-card rounded-lg border p-4 overflow-y-auto">
          <h2 className="text-sm font-semibold border-b pb-2 mb-3">Action Palette</h2>
          <p className="text-xs text-muted-foreground italic">Available in Playbook Editor</p>
        </div>

        {/* Center: Quick Execute */}
        <div className="bg-card rounded-lg border p-4 overflow-y-auto space-y-4">
          <div>
            <h2 className="text-sm font-semibold border-b pb-2 mb-3">Quick Execute</h2>
            <p className="text-xs text-muted-foreground mb-3">Enter YAML action and execute it directly</p>
            <Textarea
              value={yamlInput}
              onChange={(e) => setYamlInput(e.target.value)}
              rows={8}
              placeholder={'Click:\n  target:\n    text: Start Menu\n  strategy: best_confidence'}
              className="font-mono text-xs"
            />
            <Button className="w-full mt-3" onClick={handleExecute} disabled={!yamlInput.trim() || executeAction.isPending}>
              {executeAction.isPending ? 'Executing...' : 'Execute Action'}
            </Button>
          </div>

          {/* Variables */}
          {sessionState?.variables && Object.keys(sessionState.variables).length > 0 && (
            <div>
              <h3 className="text-sm font-semibold border-b pb-2 mb-3">Variables</h3>
              <div className="space-y-1">
                {Object.entries(sessionState.variables).map(([key, value]) => (
                  <div key={key} className="flex justify-between text-xs py-1 border-b border-border/50">
                    <span className="font-medium">{key}</span>
                    <span className="text-muted-foreground truncate max-w-[200px]">{JSON.stringify(value)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Right: Checkpoints + Execution Log */}
        <div className="bg-card rounded-lg border p-4 overflow-y-auto space-y-6">
          <CheckpointPanel sessionId={id} />
          <ExecutionLog />
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Commit**

```bash
git add src/pages/session-detail.tsx src/components/checkpoint/ src/components/execution/
git commit -m "feat(adare-web): implement session detail page with checkpoints and execution log"
```

---

## Task 13: Playbook editor page + all playbook/action components

This is the largest task. It implements the full playbook editor with drag-and-drop, action palette, config panel, and all 6 action forms.

**Files:**
- Modify: `src/pages/playbook-editor.tsx`
- Create: `src/components/shared/target-input.tsx`, `src/components/shared/strategy-selector.tsx`
- Create: `src/components/playbook/action-palette.tsx`, `src/components/playbook/action-palette-item.tsx`, `src/components/playbook/playbook-canvas.tsx`, `src/components/playbook/playbook-action-item.tsx`, `src/components/playbook/action-config-panel.tsx`, `src/components/playbook/action-config-form.tsx`
- Create: `src/components/actions/click-action-form.tsx`, `src/components/actions/keyboard-action-form.tsx`, `src/components/actions/wait-action-form.tsx`, `src/components/actions/screenshot-action-form.tsx`, `src/components/actions/command-action-form.tsx`, `src/components/actions/generic-action-form.tsx`

- [ ] **Step 1: Create src/components/shared/target-input.tsx**

```tsx
import { Input } from '@/components/ui/input'
import type { Target, TargetType } from '@/types/action'

interface TargetInputProps {
  value: Target
  onChange: (target: Target) => void
}

export function TargetInput({ value, onChange }: TargetInputProps) {
  return (
    <div className="space-y-2">
      <label className="text-sm font-medium">Target</label>
      <div className="flex gap-2">
        <select
          className="flex h-9 rounded-md border border-input bg-transparent px-3 py-1 text-sm"
          value={value.type}
          onChange={(e) => onChange({ ...value, type: e.target.value as TargetType })}
        >
          <option value="text">Text</option>
          <option value="image">Image</option>
        </select>
        <Input
          className="flex-1"
          placeholder={value.type === 'text' ? 'Search text...' : 'Image path...'}
          value={value.type === 'text' ? (value.text ?? '') : (value.image ?? '')}
          onChange={(e) =>
            onChange(
              value.type === 'text'
                ? { ...value, text: e.target.value }
                : { ...value, image: e.target.value },
            )
          }
        />
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Create src/components/shared/strategy-selector.tsx**

```tsx
import type { StrategyType } from '@/types/action'

const strategies: { value: StrategyType; label: string }[] = [
  { value: 'best_confidence', label: 'Best Confidence' },
  { value: 'sweep', label: 'Sweep' },
  { value: 'closest_to', label: 'Closest To' },
  { value: 'leftmost', label: 'Leftmost' },
  { value: 'rightmost', label: 'Rightmost' },
  { value: 'topmost', label: 'Topmost' },
  { value: 'bottommost', label: 'Bottommost' },
]

interface StrategySelectorProps {
  value: StrategyType
  onChange: (strategy: StrategyType) => void
}

export function StrategySelector({ value, onChange }: StrategySelectorProps) {
  return (
    <div className="space-y-2">
      <label className="text-sm font-medium">Strategy</label>
      <select
        className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm"
        value={value}
        onChange={(e) => onChange(e.target.value as StrategyType)}
      >
        {strategies.map((s) => (
          <option key={s.value} value={s.value}>{s.label}</option>
        ))}
      </select>
    </div>
  )
}
```

- [ ] **Step 3: Create all 6 action form components**

Create `src/components/actions/click-action-form.tsx`:
```tsx
import { Input } from '@/components/ui/input'
import { TargetInput } from '@/components/shared/target-input'
import { StrategySelector } from '@/components/shared/strategy-selector'
import type { ClickAction, MouseButton } from '@/types/action'

interface ClickActionFormProps {
  action: ClickAction
  onChange: (action: ClickAction) => void
}

export function ClickActionForm({ action, onChange }: ClickActionFormProps) {
  return (
    <div className="space-y-4">
      <TargetInput value={action.target} onChange={(target) => onChange({ ...action, target })} />
      <StrategySelector value={action.strategy} onChange={(strategy) => onChange({ ...action, strategy })} />
      <div className="space-y-2">
        <label className="text-sm font-medium">Mouse Button</label>
        <select
          className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm"
          value={action.button ?? 'left'}
          onChange={(e) => onChange({ ...action, button: e.target.value as MouseButton })}
        >
          <option value="left">Left</option>
          <option value="right">Right</option>
          <option value="middle">Middle</option>
        </select>
      </div>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={action.double_click ?? false} onChange={(e) => onChange({ ...action, double_click: e.target.checked })} className="rounded" />
        Double Click
      </label>
      <div className="grid grid-cols-2 gap-2">
        <div className="space-y-1">
          <label className="text-xs font-medium">Offset X</label>
          <Input type="number" value={action.offset_x ?? 0} onChange={(e) => onChange({ ...action, offset_x: Number(e.target.value) })} />
        </div>
        <div className="space-y-1">
          <label className="text-xs font-medium">Offset Y</label>
          <Input type="number" value={action.offset_y ?? 0} onChange={(e) => onChange({ ...action, offset_y: Number(e.target.value) })} />
        </div>
      </div>
    </div>
  )
}
```

Create `src/components/actions/keyboard-action-form.tsx`:
```tsx
import { useState } from 'react'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import type { KeyboardAction } from '@/types/action'

interface KeyboardActionFormProps {
  action: KeyboardAction
  onChange: (action: KeyboardAction) => void
}

export function KeyboardActionForm({ action, onChange }: KeyboardActionFormProps) {
  const [mode, setMode] = useState<'text' | 'keys'>(action.keys?.length ? 'keys' : 'text')

  return (
    <div className="space-y-4">
      <div className="flex gap-2">
        <button className={`px-3 py-1 text-sm rounded ${mode === 'text' ? 'bg-primary text-primary-foreground' : 'bg-muted'}`} onClick={() => setMode('text')}>Type Text</button>
        <button className={`px-3 py-1 text-sm rounded ${mode === 'keys' ? 'bg-primary text-primary-foreground' : 'bg-muted'}`} onClick={() => setMode('keys')}>Press Keys</button>
      </div>
      {mode === 'text' ? (
        <div className="space-y-2">
          <label className="text-sm font-medium">Text to Type</label>
          <Input value={action.text ?? ''} onChange={(e) => onChange({ ...action, text: e.target.value, keys: undefined })} />
        </div>
      ) : (
        <div className="space-y-2">
          <label className="text-sm font-medium">Key Combinations (one per line)</label>
          <Textarea rows={4} value={(action.keys ?? []).join('\n')} onChange={(e) => onChange({ ...action, keys: e.target.value.split('\n').filter(Boolean), text: undefined })} />
        </div>
      )}
      <div className="space-y-2">
        <label className="text-sm font-medium">Wait (seconds)</label>
        <Input type="number" step="0.1" value={action.wait ?? 0} onChange={(e) => onChange({ ...action, wait: Number(e.target.value) })} />
      </div>
    </div>
  )
}
```

Create `src/components/actions/wait-action-form.tsx`:
```tsx
import { Input } from '@/components/ui/input'
import type { WaitAction } from '@/types/action'

export function WaitActionForm({ action, onChange }: { action: WaitAction; onChange: (a: WaitAction) => void }) {
  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <label className="text-sm font-medium">Duration (seconds)</label>
        <Input type="number" min={0.5} max={3600} step={0.5} value={action.seconds ?? 1} onChange={(e) => onChange({ ...action, seconds: Number(e.target.value) })} />
      </div>
      <p className="text-xs text-muted-foreground bg-muted p-3 rounded-md">Pauses execution for the specified number of seconds.</p>
    </div>
  )
}
```

Create `src/components/actions/screenshot-action-form.tsx`:
```tsx
import { useState } from 'react'
import { Input } from '@/components/ui/input'
import type { ScreenshotAction } from '@/types/action'

export function ScreenshotActionForm({ action, onChange }: { action: ScreenshotAction; onChange: (a: ScreenshotAction) => void }) {
  const [useRegion, setUseRegion] = useState(!!action.region)

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <label className="text-sm font-medium">Filename</label>
        <Input value={action.filename} onChange={(e) => onChange({ ...action, filename: e.target.value })} placeholder="screenshot.png" />
      </div>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={useRegion} onChange={(e) => { setUseRegion(e.target.checked); if (!e.target.checked) onChange({ ...action, region: undefined }) }} className="rounded" />
        Capture Region
      </label>
      {useRegion && (
        <div className="grid grid-cols-2 gap-2">
          {(['x', 'y', 'width', 'height'] as const).map((field) => (
            <div key={field} className="space-y-1">
              <label className="text-xs font-medium capitalize">{field}</label>
              <Input type="number" value={action.region?.[field] ?? 0} onChange={(e) => onChange({ ...action, region: { x: 0, y: 0, width: 0, height: 0, ...action.region, [field]: Number(e.target.value) } })} />
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
```

Create `src/components/actions/command-action-form.tsx`:
```tsx
import { Textarea } from '@/components/ui/textarea'
import { Input } from '@/components/ui/input'
import type { CommandAction } from '@/types/action'

export function CommandActionForm({ action, onChange }: { action: CommandAction; onChange: (a: CommandAction) => void }) {
  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <label className="text-sm font-medium">Command</label>
        <Textarea rows={4} value={action.command} onChange={(e) => onChange({ ...action, command: e.target.value })} placeholder="echo hello" className="font-mono text-xs" />
      </div>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={action.wait_for_completion ?? true} onChange={(e) => onChange({ ...action, wait_for_completion: e.target.checked })} className="rounded" />
        Wait for completion
      </label>
      <div className="space-y-2">
        <label className="text-sm font-medium">Timeout (seconds)</label>
        <Input type="number" value={action.timeout_seconds ?? 30} onChange={(e) => onChange({ ...action, timeout_seconds: Number(e.target.value) })} />
      </div>
      <p className="text-xs text-destructive bg-destructive/10 p-3 rounded-md">Commands execute on the guest VM.</p>
    </div>
  )
}
```

Create `src/components/actions/generic-action-form.tsx`:
```tsx
import { useState } from 'react'
import { Textarea } from '@/components/ui/textarea'
import type { Action } from '@/types/action'

export function GenericActionForm({ action, onChange }: { action: Action; onChange: (a: Action) => void }) {
  const { type, description, screenshot_before, screenshot_after, ...params } = action
  const [json, setJson] = useState(JSON.stringify(params, null, 2))

  const handleBlur = () => {
    try {
      const parsed = JSON.parse(json)
      onChange({ ...action, ...parsed })
    } catch { /* invalid JSON, ignore */ }
  }

  return (
    <div className="space-y-4">
      <p className="text-xs text-muted-foreground bg-muted p-3 rounded-md">
        No dedicated form for <strong>{type}</strong>. Edit raw parameters below.
      </p>
      <Textarea rows={10} value={json} onChange={(e) => setJson(e.target.value)} onBlur={handleBlur} className="font-mono text-xs" />
    </div>
  )
}
```

- [ ] **Step 4: Create playbook components**

Create `src/components/playbook/action-palette-item.tsx`:
```tsx
import { Plus } from 'lucide-react'
import type { ActionTypeMetadata } from '@/types/action'

interface ActionPaletteItemProps {
  actionType: ActionTypeMetadata
  onAdd: (actionType: ActionTypeMetadata) => void
}

export function ActionPaletteItem({ actionType, onAdd }: ActionPaletteItemProps) {
  return (
    <button
      className="flex items-center gap-2 w-full px-2 py-1.5 text-left text-sm rounded-md hover:bg-accent transition-colors group"
      onClick={() => onAdd(actionType)}
      draggable
      onDragStart={(e) => e.dataTransfer.setData('application/json', JSON.stringify(actionType))}
    >
      <span className="text-base">{actionType.icon}</span>
      <div className="flex-1 min-w-0">
        <p className="font-medium text-xs">{actionType.display_name}</p>
        <p className="text-xs text-muted-foreground truncate">{actionType.description}</p>
      </div>
      <Plus className="h-3 w-3 opacity-0 group-hover:opacity-100 transition-opacity" />
    </button>
  )
}
```

Create `src/components/playbook/action-palette.tsx`:
```tsx
import { useState, useEffect } from 'react'
import { Search } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { ActionPaletteItem } from './action-palette-item'
import { useActionTypes } from '@/api/hooks/use-actions'
import { usePlaybookStore } from '@/stores/playbook-store'
import type { ActionTypeMetadata, Action } from '@/types/action'

const categoryNames: Record<string, string> = {
  gui: 'GUI Actions',
  control: 'Control Flow',
  data: 'Data Actions',
  system: 'System Actions',
}

export function ActionPalette() {
  const { data: actionTypes } = useActionTypes()
  const { setActionTypes, addAction } = usePlaybookStore()
  const [search, setSearch] = useState('')

  useEffect(() => {
    if (actionTypes) setActionTypes(actionTypes)
  }, [actionTypes, setActionTypes])

  const filtered = (actionTypes ?? []).filter(
    (a) => !search || a.display_name.toLowerCase().includes(search.toLowerCase()) || a.type.toLowerCase().includes(search.toLowerCase()),
  )

  const grouped = filtered.reduce<Record<string, ActionTypeMetadata[]>>((acc, a) => {
    const cat = a.category || 'system'
    ;(acc[cat] ??= []).push(a)
    return acc
  }, {})

  const handleAdd = (meta: ActionTypeMetadata) => {
    addAction({ type: meta.type, ...meta.default_params } as Action)
  }

  return (
    <div className="flex flex-col h-full">
      <h2 className="text-sm font-semibold border-b pb-2 mb-3">Actions</h2>
      <div className="relative mb-3">
        <Search className="absolute left-2 top-2.5 h-3.5 w-3.5 text-muted-foreground" />
        <Input className="pl-8 h-8 text-xs" placeholder="Search actions..." value={search} onChange={(e) => setSearch(e.target.value)} />
      </div>
      <div className="flex-1 overflow-y-auto space-y-4">
        {Object.entries(grouped).map(([cat, items]) => (
          <div key={cat}>
            <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-1">{categoryNames[cat] ?? cat}</h3>
            <div className="space-y-0.5">
              {items.map((item) => <ActionPaletteItem key={item.type} actionType={item} onAdd={handleAdd} />)}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
```

Create `src/components/playbook/playbook-action-item.tsx`:
```tsx
import { GripVertical, Trash2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { Action } from '@/types/action'

const iconMap: Record<string, string> = {
  Click: '🖱️', Keyboard: '⌨️', Scroll: '🔄', Drag: '↔️', Wait: '⏱️', Loop: '🔁',
  Block: '📦', Conditional: '❓', SetVar: '📝', FileRead: '📖', FileWrite: '💾',
  Screenshot: '📸', Command: '💻', Test: '🧪', Checkpoint: '💾', RestoreCheckpoint: '↩️', Reset: '🔃',
}

interface PlaybookActionItemProps {
  action: Action
  index: number
  isSelected: boolean
  onSelect: () => void
  onDelete: () => void
  dragHandleProps?: Record<string, unknown>
}

export function PlaybookActionItem({ action, index, isSelected, onSelect, onDelete, dragHandleProps }: PlaybookActionItemProps) {
  return (
    <div
      className={cn(
        'flex items-center gap-2 rounded-md border p-2 text-sm transition-colors cursor-pointer',
        isSelected ? 'border-primary bg-accent' : 'hover:bg-muted',
      )}
      onClick={onSelect}
    >
      <span {...dragHandleProps} className="cursor-grab text-muted-foreground"><GripVertical className="h-4 w-4" /></span>
      <span className="flex items-center justify-center w-6 h-6 rounded-full bg-muted text-xs font-medium">{index + 1}</span>
      <span>{iconMap[action.type] ?? '❔'}</span>
      <span className="flex-1 font-medium">{action.type}</span>
      {action.description && <span className="text-xs text-muted-foreground truncate max-w-32">{action.description}</span>}
      <button onClick={(e) => { e.stopPropagation(); onDelete() }} className="text-muted-foreground hover:text-destructive">
        <Trash2 className="h-3.5 w-3.5" />
      </button>
    </div>
  )
}
```

Create `src/components/playbook/playbook-canvas.tsx`:
```tsx
import { DndContext, closestCenter, KeyboardSensor, PointerSensor, useSensor, useSensors, type DragEndEvent } from '@dnd-kit/core'
import { SortableContext, sortableKeyboardCoordinates, verticalListSortingStrategy, useSortable, arrayMove } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { FileCode } from 'lucide-react'
import { EmptyState } from '@/components/shared/empty-state'
import { PlaybookActionItem } from './playbook-action-item'
import { usePlaybookStore } from '@/stores/playbook-store'
import type { Action, ActionTypeMetadata } from '@/types/action'

function SortableAction({ action, index, id }: { action: Action; index: number; id: string }) {
  const { attributes, listeners, setNodeRef, transform, transition } = useSortable({ id })
  const { selectedActionIndex, selectAction, removeAction } = usePlaybookStore()

  const style = { transform: CSS.Transform.toString(transform), transition }

  return (
    <div ref={setNodeRef} style={style} {...attributes}>
      <PlaybookActionItem
        action={action}
        index={index}
        isSelected={selectedActionIndex === index}
        onSelect={() => selectAction(index)}
        onDelete={() => removeAction(index)}
        dragHandleProps={listeners}
      />
    </div>
  )
}

export function PlaybookCanvas() {
  const { actions, reorderActions, addAction } = usePlaybookStore()
  const sensors = useSensors(useSensor(PointerSensor), useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }))

  const ids = actions.map((_, i) => `action-${i}`)

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event
    if (over && active.id !== over.id) {
      const oldIndex = ids.indexOf(active.id as string)
      const newIndex = ids.indexOf(over.id as string)
      reorderActions(arrayMove(actions, oldIndex, newIndex))
    }
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    try {
      const meta: ActionTypeMetadata = JSON.parse(e.dataTransfer.getData('application/json'))
      addAction({ type: meta.type, ...meta.default_params } as Action)
    } catch { /* ignore invalid drops */ }
  }

  if (actions.length === 0) {
    return (
      <div onDragOver={(e) => e.preventDefault()} onDrop={handleDrop} className="h-full">
        <EmptyState icon={<FileCode className="h-12 w-12" />} title="No actions yet" message="Drag actions from the palette or click + to add" />
      </div>
    )
  }

  return (
    <div onDragOver={(e) => e.preventDefault()} onDrop={handleDrop} className="space-y-1">
      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
        <SortableContext items={ids} strategy={verticalListSortingStrategy}>
          {actions.map((action, index) => (
            <SortableAction key={ids[index]} id={ids[index]} action={action} index={index} />
          ))}
        </SortableContext>
      </DndContext>
    </div>
  )
}
```

Create `src/components/playbook/action-config-form.tsx`:
```tsx
import type { Action } from '@/types/action'
import { ClickActionForm } from '@/components/actions/click-action-form'
import { KeyboardActionForm } from '@/components/actions/keyboard-action-form'
import { WaitActionForm } from '@/components/actions/wait-action-form'
import { ScreenshotActionForm } from '@/components/actions/screenshot-action-form'
import { CommandActionForm } from '@/components/actions/command-action-form'
import { GenericActionForm } from '@/components/actions/generic-action-form'
import type { ClickAction, KeyboardAction, WaitAction, ScreenshotAction, CommandAction } from '@/types/action'

interface ActionConfigFormProps {
  action: Action
  onChange: (action: Action) => void
}

export function ActionConfigForm({ action, onChange }: ActionConfigFormProps) {
  switch (action.type) {
    case 'Click':
      return <ClickActionForm action={action as ClickAction} onChange={onChange} />
    case 'Keyboard':
      return <KeyboardActionForm action={action as KeyboardAction} onChange={onChange} />
    case 'Wait':
      return <WaitActionForm action={action as WaitAction} onChange={onChange} />
    case 'Screenshot':
      return <ScreenshotActionForm action={action as ScreenshotAction} onChange={onChange} />
    case 'Command':
      return <CommandActionForm action={action as CommandAction} onChange={onChange} />
    default:
      return <GenericActionForm action={action} onChange={onChange} />
  }
}
```

Create `src/components/playbook/action-config-panel.tsx`:
```tsx
import { useState } from 'react'
import { ActionConfigForm } from './action-config-form'
import { Input } from '@/components/ui/input'
import { usePlaybookStore } from '@/stores/playbook-store'
import { cn } from '@/lib/utils'

const tabs = ['Config', 'Settings', 'Variables'] as const

export function ActionConfigPanel() {
  const { actions, selectedActionIndex, updateAction, variables } = usePlaybookStore()
  const [activeTab, setActiveTab] = useState<typeof tabs[number]>('Config')

  const selectedAction = selectedActionIndex !== null ? actions[selectedActionIndex] : null

  if (!selectedAction) {
    return (
      <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
        Select an action to configure
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex border-b mb-3">
        {tabs.map((tab) => (
          <button
            key={tab}
            className={cn(
              'px-3 py-2 text-xs font-medium border-b-2 transition-colors',
              activeTab === tab ? 'border-primary text-primary' : 'border-transparent text-muted-foreground hover:text-foreground',
            )}
            onClick={() => setActiveTab(tab)}
          >
            {tab}
          </button>
        ))}
      </div>

      <div className="flex-1 overflow-y-auto">
        {activeTab === 'Config' && (
          <ActionConfigForm
            action={selectedAction}
            onChange={(updated) => updateAction(selectedActionIndex!, updated)}
          />
        )}
        {activeTab === 'Settings' && (
          <div className="space-y-4">
            <div className="space-y-2">
              <label className="text-sm font-medium">Description</label>
              <Input
                value={selectedAction.description ?? ''}
                onChange={(e) => updateAction(selectedActionIndex!, { ...selectedAction, description: e.target.value })}
                placeholder="Optional description..."
              />
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={selectedAction.screenshot_before ?? false} onChange={(e) => updateAction(selectedActionIndex!, { ...selectedAction, screenshot_before: e.target.checked })} className="rounded" />
              Screenshot Before
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={selectedAction.screenshot_after ?? false} onChange={(e) => updateAction(selectedActionIndex!, { ...selectedAction, screenshot_after: e.target.checked })} className="rounded" />
              Screenshot After
            </label>
          </div>
        )}
        {activeTab === 'Variables' && (
          <div className="space-y-1">
            {Object.keys(variables).length === 0 ? (
              <p className="text-xs text-muted-foreground">No variables defined</p>
            ) : (
              Object.entries(variables).map(([key, val]) => (
                <div key={key} className="flex justify-between text-xs py-1 border-b border-border/50">
                  <span className="font-medium">{key}</span>
                  <span className="text-muted-foreground">{JSON.stringify(val)}</span>
                </div>
              ))
            )}
          </div>
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 5: Implement src/pages/playbook-editor.tsx**

```tsx
import { useEffect, useCallback } from 'react'
import { FilePlus, FolderOpen, Save, FileDown } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { ActionPalette } from '@/components/playbook/action-palette'
import { PlaybookCanvas } from '@/components/playbook/playbook-canvas'
import { ActionConfigPanel } from '@/components/playbook/action-config-panel'
import { usePlaybookStore } from '@/stores/playbook-store'
import { useSavePlaybook } from '@/api/hooks/use-playbook'

export default function PlaybookEditorPage() {
  const { playbookName, setPlaybookName, isDirty, actions, clearPlaybook, exportToYAML, markClean, selectedActionIndex, removeAction } = usePlaybookStore()
  const savePlaybook = useSavePlaybook()

  const handleSave = useCallback(() => {
    const content = exportToYAML()
    savePlaybook.mutate({ name: playbookName, content }, { onSuccess: () => markClean() })
  }, [playbookName, exportToYAML, savePlaybook, markClean])

  const handleExport = () => {
    const yaml = exportToYAML()
    const blob = new Blob([yaml], { type: 'text/yaml' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${playbookName}.yaml`
    a.click()
    URL.revokeObjectURL(url)
  }

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 's') {
        e.preventDefault()
        handleSave()
      }
      if (e.key === 'Delete' && selectedActionIndex !== null) {
        removeAction(selectedActionIndex)
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [handleSave, selectedActionIndex, removeAction])

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2 border-b bg-card">
        <div className="flex items-center gap-3">
          <Input className="w-48 h-8 text-sm" value={playbookName} onChange={(e) => setPlaybookName(e.target.value)} />
          {isDirty && <span className="text-xs text-warning">Unsaved changes</span>}
        </div>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" onClick={clearPlaybook}><FilePlus className="h-4 w-4" /> New</Button>
          <Button size="sm" variant="outline" disabled><FolderOpen className="h-4 w-4" /> Load</Button>
          <Button size="sm" onClick={handleSave} disabled={savePlaybook.isPending}><Save className="h-4 w-4" /> Save</Button>
          <Button size="sm" variant="outline" onClick={handleExport} disabled={actions.length === 0}><FileDown className="h-4 w-4" /> Export</Button>
        </div>
      </div>

      {/* 3-column layout */}
      <div className="flex-1 grid grid-cols-[240px_1fr_300px] gap-4 p-4 overflow-hidden">
        <div className="bg-card rounded-lg border p-3 overflow-y-auto">
          <ActionPalette />
        </div>
        <div className="bg-card rounded-lg border p-3 overflow-y-auto">
          <h2 className="text-sm font-semibold border-b pb-2 mb-3">Playbook ({actions.length} actions)</h2>
          <PlaybookCanvas />
        </div>
        <div className="bg-card rounded-lg border p-3 overflow-y-auto">
          <h2 className="text-sm font-semibold border-b pb-2 mb-3">Configuration</h2>
          <ActionConfigPanel />
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 6: Verify the full app compiles and runs**

```bash
cd adare-web && npm run dev
```

Visit all 4 routes: `/`, `/sessions`, `/session/test-id`, `/playbook/editor`. Verify sidebar, theming, and layouts render correctly.

- [ ] **Step 7: Run type check**

```bash
cd adare-web && npx tsc --noEmit
```

Expected: No TypeScript errors.

- [ ] **Step 8: Commit**

```bash
git add src/pages/playbook-editor.tsx src/components/playbook/ src/components/actions/ src/components/shared/target-input.tsx src/components/shared/strategy-selector.tsx
git commit -m "feat(adare-web): implement playbook editor with drag-drop, action forms, and config panel"
```

---

## Task 14: Final build verification

- [ ] **Step 1: Run production build**

```bash
cd adare-web && npm run build
```

Expected: Build completes with no errors. Output in `dist/`.

- [ ] **Step 2: Preview production build**

```bash
cd adare-web && npm run preview
```

Visit all pages, test sidebar collapse, all 4 theme variants.

- [ ] **Step 3: Commit if any fixes were needed**

If fixes were made:
```bash
git add -A
git commit -m "fix(adare-web): fix build issues from final verification"
```

---

## Verification Checklist

After all tasks:

1. `npm run dev` starts without errors
2. All 4 pages render: Home (`/`), Sessions (`/sessions`), Session Detail (`/session/$id`), Playbook Editor (`/playbook/editor`)
3. Sidebar collapses to 64px / expands to 240px with smooth transition
4. Sidebar state persists on refresh (localStorage)
5. All 4 theme variants work: Light Default, Dark Default (slate-teal), Light Teal, Dark Teal
6. Theme mode + color scheme persist on refresh
7. System theme preference detection works (mode=system)
8. Session list fetches from API, shows loading/empty/error states
9. Start Session dialog validates and submits
10. Session detail connects WebSocket, shows connection status
11. Checkpoint panel CRUD works against API
12. Execution log shows entries with status icons
13. Playbook editor: drag from palette to canvas works
14. Playbook editor: reorder actions on canvas works
15. Playbook editor: select action → config panel shows form
16. Playbook editor: Ctrl+S saves, Delete removes selected action
17. YAML export downloads .yaml file
18. `npm run build` succeeds with no TS errors
