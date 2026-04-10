import { Link } from '@tanstack/react-router'
import {
  LayoutDashboard,
  Play,
  FlaskConical,
  FolderKanban,
  Server,
  Sun,
  Moon,
  Monitor,
  Palette,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { useThemeStore } from '@/stores/theme-store'
import { useSidebarStore } from '@/stores/sidebar-store'

const navItems = [
  { to: '/', label: 'Home', icon: LayoutDashboard },
  { to: '/runs', label: 'Runs', icon: Play },
  { to: '/experiments', label: 'Experiments', icon: FlaskConical },
  { to: '/projects', label: 'Projects', icon: FolderKanban },
  { to: '/environments', label: 'Environments', icon: Server },
] as const

export function Sidebar() {
  const { mode, colorScheme, setMode, setColorScheme } = useThemeStore()
  const { collapsed } = useSidebarStore()

  return (
    <aside
      className={cn(
        'flex flex-col h-screen border-r border-border bg-card sticky top-0 shrink-0 transition-all duration-200',
        collapsed ? 'w-16' : 'w-60',
      )}
    >
      {/* Header */}
      <div className="flex items-center p-4 border-b border-border">
        {!collapsed && (
          <h2 className="font-semibold text-lg tracking-tight">ADARE</h2>
        )}
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto p-4">
        <ul className="space-y-1">
          {navItems.map(({ to, label, icon: Icon }) => (
            <li key={to}>
              <Link
                to={to}
                activeProps={{ className: 'bg-accent text-accent-foreground' }}
                activeOptions={to === '/' ? { exact: true } : undefined}
                className={cn(
                  'flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium',
                  'hover:bg-accent hover:text-accent-foreground transition-colors',
                  collapsed && 'justify-center',
                )}
              >
                <Icon className="h-4 w-4 shrink-0" />
                {!collapsed && <span>{label}</span>}
              </Link>
            </li>
          ))}
        </ul>
      </nav>

      {/* Theme controls */}
      <div className="p-4 border-t border-border space-y-2">
        {/* Mode toggle */}
        <div className={cn('flex gap-1', collapsed && 'flex-col items-center')}>
          <Button
            variant="ghost"
            size="icon"
            aria-label="Light mode"
            aria-pressed={mode === 'light'}
            className={cn(mode === 'light' && 'bg-accent text-accent-foreground')}
            onClick={() => setMode('light')}
          >
            <Sun className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            aria-label="System mode"
            aria-pressed={mode === 'system'}
            className={cn(mode === 'system' && 'bg-accent text-accent-foreground')}
            onClick={() => setMode('system')}
          >
            <Monitor className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            aria-label="Dark mode"
            aria-pressed={mode === 'dark'}
            className={cn(mode === 'dark' && 'bg-accent text-accent-foreground')}
            onClick={() => setMode('dark')}
          >
            <Moon className="h-4 w-4" />
          </Button>
        </div>

        {/* Color scheme toggle */}
        <div className="flex gap-1">
          <Button
            variant="ghost"
            size="icon"
            aria-label={`Color scheme: ${colorScheme === 'teal' ? 'switch to default' : 'switch to teal'}`}
            className={cn(colorScheme === 'teal' && 'bg-accent text-accent-foreground')}
            onClick={() => setColorScheme(colorScheme === 'teal' ? 'default' : 'teal')}
          >
            <Palette className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </aside>
  )
}
