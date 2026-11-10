import { CircleHelp } from 'lucide-react'
import { Badge, statusToVariant, type BadgeVariant } from '@/components/ui/badge'
import { INCONCLUSIVE_HINT, isInconclusive, verdictLabel } from '@/lib/verdict'

/** Badge for a run / test-result verdict; INCONCLUSIVE gets an amber question style. */
export function VerdictBadge({ status, variant }: { status: string | null | undefined; variant?: BadgeVariant }) {
  if (isInconclusive(status)) {
    return (
      <Badge variant="inconclusive" title={INCONCLUSIVE_HINT} className="gap-1">
        <CircleHelp className="h-3 w-3" aria-hidden />
        {verdictLabel(status)}
      </Badge>
    )
  }
  if (!status) return <>—</>
  return <Badge variant={variant ?? statusToVariant(status)}>{verdictLabel(status)}</Badge>
}
