/**
 * Run / test-result verdicts (StatusEnum names) that need special display.
 *
 * INCONCLUSIVE (StatusEnum 15): a negative test (asserting an artifact is
 * absent) passed, but ADARE could not prove the GUI actions before it took
 * effect (an action was skipped by `when:`, showed no screen change, or failed
 * a `verify:`). It is neither a pass nor a fail. Run verdict precedence:
 * FAILED > INCONCLUSIVE > TEST_MISSING > WARNING > SUCCESS.
 */
export const INCONCLUSIVE = 'INCONCLUSIVE'

export const INCONCLUSIVE_HINT =
  'The test passed, but ADARE could not prove the GUI actions before it took effect ' +
  '(skipped by a when:, no screen change, or a failed verify:).'

export function isInconclusive(status: string | null | undefined): boolean {
  return (status ?? '').toUpperCase() === INCONCLUSIVE
}

/** Human label for a verdict; unknown verdicts are shown as sent. */
export function verdictLabel(status: string | null | undefined): string {
  if (!status) return '—'
  if (isInconclusive(status)) return 'Inconclusive'
  return status
}
