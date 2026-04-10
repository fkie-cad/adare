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
