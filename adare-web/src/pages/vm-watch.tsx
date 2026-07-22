import { useSearch } from '@tanstack/react-router'
import { VmLiveView } from '@/components/vm/vm-live-view'

/**
 * Full-window host page for the ADARE-owned VM live view (the "pop out to tab"
 * target). Reads `name` / `viewOnly` from the URL search params and renders the
 * viewer filling the whole window.
 */
export default function VmWatchPage() {
  const { name, viewOnly } = useSearch({ from: '/vm/watch' }) as {
    name?: string
    viewOnly?: boolean
  }

  if (!name) {
    return (
      <div className="flex h-screen w-full items-center justify-center bg-black text-sm text-muted-foreground">
        No VM name provided (expected ?name=&lt;vm&gt;).
      </div>
    )
  }

  // Fills the layout's `<main>` area (the app shell/sidebar remains in place).
  return (
    <VmLiveView
      vmName={name}
      viewOnly={viewOnly ?? false}
      className="h-screen w-full"
    />
  )
}
