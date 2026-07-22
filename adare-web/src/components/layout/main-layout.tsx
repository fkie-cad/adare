import { Outlet } from '@tanstack/react-router'
import { useSidebarStore } from '@/stores/sidebar-store'
import { ToastViewport } from '@/components/ui/toast'
import { Sidebar } from './sidebar'

export function MainLayout() {
  // Subscribe to sidebar store to activate it
  useSidebarStore()

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
