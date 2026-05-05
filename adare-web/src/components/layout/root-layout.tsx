import { Link, Outlet, useMatchRoute } from '@tanstack/react-router'
import { ThemeToggle } from './theme-toggle'
import { cn } from '@/lib/utils'

const navItems = [
  { to: '/', label: 'Home' },
  { to: '/sessions', label: 'Sessions' },
  { to: '/playbook/editor', label: 'Playbook Editor' },
] as const

function NavLink({ to, label }: { to: string; label: string }) {
  const matchRoute = useMatchRoute()
  const isActive = matchRoute({ to, fuzzy: to !== '/' })
  const isExactHome = to === '/' && matchRoute({ to: '/' }) && !matchRoute({ to: '/sessions', fuzzy: true }) && !matchRoute({ to: '/playbook', fuzzy: true })
  const active = to === '/' ? isExactHome : isActive

  return (
    <Link
      to={to}
      className={cn(
        'rounded-md px-3 py-1.5 text-sm font-medium transition-colors',
        active
          ? 'bg-primary text-primary-foreground'
          : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground',
      )}
    >
      {label}
    </Link>
  )
}

export function RootLayout() {
  return (
    <div className="flex h-screen w-screen flex-col overflow-hidden">
      <header className="flex items-center justify-between border-b border-border bg-card px-6 py-3">
        <div className="flex items-baseline gap-3">
          <h1 className="text-lg font-bold text-foreground">ADARE Web</h1>
          <span className="text-xs text-muted-foreground">
            Automated Desktop Analysis
          </span>
        </div>

        <nav className="flex items-center gap-1">
          {navItems.map((item) => (
            <NavLink key={item.to} to={item.to} label={item.label} />
          ))}
        </nav>

        <div className="flex items-center gap-2">
          <ThemeToggle />
        </div>
      </header>

      <main className="flex-1 overflow-auto bg-background">
        <Outlet />
      </main>
    </div>
  )
}
