import { create } from 'zustand'

/**
 * The docked terminal panel: open/closed, its height and the active tab. The
 * sessions themselves live on the server (they outlive page reloads); this only
 * remembers how the panel looks.
 */
interface TerminalPanelState {
  open: boolean
  height: number
  activeId: string | null
  setOpen: (open: boolean) => void
  toggle: () => void
  setHeight: (height: number) => void
  setActive: (id: string | null) => void
}

const HEIGHT_KEY = 'adare-terminal-height'
const OPEN_KEY = 'adare-terminal-open'

function readNumber(key: string, fallback: number): number {
  try {
    const value = Number(localStorage.getItem(key))
    return Number.isFinite(value) && value > 0 ? value : fallback
  } catch {
    return fallback
  }
}

function persist(key: string, value: string) {
  try {
    localStorage.setItem(key, value)
  } catch {
    // storage unavailable (private window): the panel just forgets its layout
  }
}

export const useTerminalStore = create<TerminalPanelState>((set) => ({
  open: (() => {
    try {
      return localStorage.getItem(OPEN_KEY) === 'true'
    } catch {
      return false
    }
  })(),
  height: readNumber(HEIGHT_KEY, 360),
  activeId: null,
  setOpen: (open) => {
    persist(OPEN_KEY, String(open))
    set({ open })
  },
  toggle: () =>
    set((state) => {
      persist(OPEN_KEY, String(!state.open))
      return { open: !state.open }
    }),
  setHeight: (height) => {
    persist(HEIGHT_KEY, String(height))
    set({ height })
  },
  setActive: (activeId) => set({ activeId }),
}))
