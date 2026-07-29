import { Outlet, useLocation } from '@tanstack/react-router'
import { useSidebarStore } from '@/stores/sidebar-store'
import { ToastViewport } from '@/components/ui/toast'
import { Sidebar } from './sidebar'

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
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>
      <ToastViewport />
    </div>
  )
}

export default MainLayout
