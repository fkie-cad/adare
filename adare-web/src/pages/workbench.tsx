import { useState } from 'react'
import { useSearch } from '@tanstack/react-router'
import { Hammer } from 'lucide-react'
import { PageHeader } from '@/components/layout/page-header'
import { Card, CardContent } from '@/components/ui/card'
import { EmptyState } from '@/components/ui/empty-state'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { useSessions } from '@/api/hooks/use-sessions'
import { SessionControls } from '@/components/workbench/session-controls'
import { RunAgentPanel } from '@/components/workbench/run-agent-panel'
import { ManualActionsPanel } from '@/components/workbench/manual-actions-panel'
import { CheckpointsPanel } from '@/components/workbench/checkpoints-panel'
import { PlaybookPanel } from '@/components/workbench/playbook-panel'

export default function WorkbenchPage() {
  const search = useSearch({ from: '/develop' })
  const { data: sessions } = useSessions()
  const [sessionId, setSessionId] = useState('')

  const selectedSession = sessions?.find((s) => s.session_id === sessionId)
  const autoOpenNew = !sessionId && !!search.experiment && !!search.environment

  return (
    <div className="p-6 space-y-6">
      <PageHeader
        title="Workbench"
        description="Develop ADARE experiments interactively against a live VM"
      />

      <Card>
        <CardContent className="pt-6">
          <SessionControls
            sessionId={sessionId}
            onSelectSession={setSessionId}
            initialExperiment={search.experiment}
            initialEnvironment={search.environment}
            autoOpenNew={autoOpenNew}
          />
        </CardContent>
      </Card>

      {!sessionId ? (
        <EmptyState
          icon={Hammer}
          title="No session selected"
          description="Pick an existing session or start a new one to begin developing."
        />
      ) : (
        <div className="grid gap-6 xl:grid-cols-3">
          <div className="xl:col-span-2">
            <Tabs defaultValue="agent">
              <TabsList>
                <TabsTrigger value="agent">Run agent</TabsTrigger>
                <TabsTrigger value="manual">Manual actions</TabsTrigger>
              </TabsList>
              <TabsContent value="agent">
                <RunAgentPanel
                  sessionId={sessionId}
                  vmName={selectedSession?.vm_name}
                  vmRunning={selectedSession?.vm_running}
                />
              </TabsContent>
              <TabsContent value="manual">
                <ManualActionsPanel sessionId={sessionId} />
              </TabsContent>
            </Tabs>
          </div>

          <div className="space-y-6">
            <CheckpointsPanel sessionId={sessionId} />
            <PlaybookPanel />
          </div>
        </div>
      )}
    </div>
  )
}
