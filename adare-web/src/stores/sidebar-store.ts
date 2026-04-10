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
