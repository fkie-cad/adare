import { useCreateTerminal, type CreateTerminalRequest } from '@/api/hooks/use-terminals'
import { useTerminalStore } from '@/stores/terminal-store'
import { toast } from '@/components/ui/toast'

export const CWD_KEY = 'adare-terminal-cwd'

/** The project last chosen in the terminal panel, else the first project. */
export function defaultProjectPath(projects: { path: string }[]): string | undefined {
  let remembered = ''
  try {
    remembered = localStorage.getItem(CWD_KEY) ?? ''
  } catch {
    // storage unavailable
  }
  return remembered || projects[0]?.path || undefined
}

/** Start a terminal (Claude Code by default) and show it in the docked panel. */
export function useLaunchTerminal() {
  const create = useCreateTerminal()
  const { setOpen, setActive } = useTerminalStore()

  const launch = (request: CreateTerminalRequest) => {
    setOpen(true)
    create.mutate(request, {
      onSuccess: (session) => setActive(session.id),
      onError: (err) => toast.error('Could not start terminal', (err as Error).message),
    })
  }

  return { launch, isPending: create.isPending }
}
