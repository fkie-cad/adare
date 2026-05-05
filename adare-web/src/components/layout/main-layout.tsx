import { useEffect } from 'react'
import { Outlet } from '@tanstack/react-router'
import { useThemeStore } from '@/stores/theme-store'
import { useSidebarStore } from '@/stores/sidebar-store'
import { ToastViewport } from '@/components/ui/toast'
import { Sidebar } from './sidebar'

export function MainLayout() {
  const { mode, colorScheme } = useThemeStore()
  // Subscribe to sidebar store to activate it
  useSidebarStore()

  useEffect(() => {
    const root = document.documentElement

    function applyMode() {
      const isDark =
        mode === 'dark' ||
        (mode === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches)
      root.classList.toggle('dark', isDark)
    }

    root.classList.toggle('teal', colorScheme === 'teal')
    applyMode()

    if (mode === 'system') {
      const mq = window.matchMedia('(prefers-color-scheme: dark)')
      mq.addEventListener('change', applyMode)
      return () => mq.removeEventListener('change', applyMode)
    }

    return undefined
  }, [mode, colorScheme])

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
