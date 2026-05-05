import { Moon, Sun, Monitor } from 'lucide-react'
import { useThemeStore } from '@/stores/theme-store'
import { cn } from '@/lib/utils'

const modes = ['light', 'dark', 'system'] as const

const icons = {
  light: Sun,
  dark: Moon,
  system: Monitor,
} as const

const labels = {
  light: 'Light mode',
  dark: 'Dark mode',
  system: 'System theme',
} as const

export function ThemeToggle({ className }: { className?: string }) {
  const mode = useThemeStore((s) => s.mode)
  const setMode = useThemeStore((s) => s.setMode)

  function cycle() {
    const i = modes.indexOf(mode)
    setMode(modes[(i + 1) % modes.length])
  }

  const Icon = icons[mode]

  return (
    <button
      onClick={cycle}
      className={cn(
        'inline-flex items-center justify-center rounded-md p-2 text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring',
        className,
      )}
      aria-label={labels[mode]}
      title={labels[mode]}
    >
      <Icon className="size-4" />
    </button>
  )
}
