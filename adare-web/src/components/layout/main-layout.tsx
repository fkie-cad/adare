import { Outlet, useLocation } from '@tanstack/react-router'
import { useSidebarStore } from '@/stores/sidebar-store'
import { ToastViewport } from '@/components/ui/toast'
import { Sidebar } from './sidebar'
import { TerminalPanel } from '@/components/terminal/terminal-panel'

export function MainLayout() {
  // Subscribe to sidebar store to activate it
  useSidebarStore()

  // The VM watch page is a chrome-less, full-window host (pop-out target): no
  // sidebar, the viewer fills the viewport.
  const { pathname } = useLocation()
  if (pathname === '/vm/watch') {
    return (
      <div className="min-h-screen bg-background text-foreground">
        <Outlet />
        <ToastViewport />
      </div>
    )
  }

  return (
    <div className="flex min-h-screen bg-background text-foreground">
      <Sidebar />
      <div className="flex h-screen min-w-0 flex-1 flex-col">
        <main className="min-h-0 flex-1 overflow-auto">
          <Outlet />
        </main>
        <TerminalPanel />
      </div>
      <ToastViewport />
    </div>
  )
}

export default MainLayout
