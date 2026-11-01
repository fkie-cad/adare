import { Badge } from '@/components/ui/badge'

// The backend reports an environment's publication state as two booleans
// (`published`, `in_request`) -- see EnvironmentListItem / EnvironmentDetail.
// Published: the server has it. In request: queued for / part of a pending
// publish request. Neither: it only exists on this machine.
export function EnvironmentSyncBadge({
  published,
  inRequest,
}: {
  published: unknown
  inRequest: unknown
}) {
  if (published === true) return <Badge variant="success">Published</Badge>
  if (inRequest === true) return <Badge variant="warning">Pending request</Badge>
  return <Badge variant="outline">Local</Badge>
}
