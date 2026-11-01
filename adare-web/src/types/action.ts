/**
 * TypeScript types for ADARE playbook actions.
 *
 * Single source of truth is the backend: `GET /api/actions/types` is generated from the
 * playbook parser's action registry (adare/types/action_catalogue.py), so action names and
 * fields come from there. The UI keeps actions in exactly the shape the parser accepts
 * (`{<action_key>: {params}}`, e.g. `{click: {target: {text: 'OK'}}}`), so the same object can
 * be stringified for execute-action (`action_yaml`) and sent as-is for playbook save/execute.
 */

// Parser-shaped action: a single-key mapping from the action key to its parameters.
export type ActionParams = Record<string, unknown>
export type Action = Record<string, ActionParams>

export type ActionCategory = 'gui' | 'control' | 'data' | 'system'

export interface Target {
  image?: string // Path to image file
  text?: string // Text to search for
}

// Target strategies as the parser spells them: `strategy: {<ClassName>: {params}}`.
export const TARGET_STRATEGIES = [
  'SweepStrategy',
  'BestConfidenceStrategy',
  'TopLeftStrategy',
  'TopRightStrategy',
  'BottomLeftStrategy',
  'BottomRightStrategy',
  'LargestStrategy',
  'SmallestStrategy',
] as const
export type TargetStrategyName = (typeof TARGET_STRATEGIES)[number]

export type ClickType = 'left' | 'right' | 'double'
export type ScrollDirection = 'up' | 'down' | 'left' | 'right'

// Action execution result
export interface ActionResult {
  success: boolean
  message: string
  execution_time: number
  screenshot_path?: string
  error_message?: string
  coordinates?: [number, number]
  data?: unknown
}

// Action type metadata (for palette), as served by /api/actions/types
export interface ActionTypeMetadata {
  /** The parser's action key (`click`, `idle`, `wait_until`, ...). */
  type: string
  category: ActionCategory
  display_name: string
  description: string
  /** lucide icon name */
  icon: string
  /** Seed parameters; `{[type]: default_params}` always parses. */
  default_params: ActionParams
  required_fields: string[]
  optional_fields: string[]
}

/** Build a parser-shaped action from its key and parameters. */
export function makeAction(key: string, params: ActionParams = {}): Action {
  return { [key]: params }
}

/** The parser key of an action (its single top-level key). */
export function actionKey(action: Action): string {
  return Object.keys(action)[0] ?? ''
}

export function actionParams(action: Action): ActionParams {
  const params = action[actionKey(action)]
  return params && typeof params === 'object' ? params : {}
}

/** Drop undefined/empty-string params so cleared inputs don't reach the parser. */
export function pruneParams(params: ActionParams): ActionParams {
  return Object.fromEntries(
    Object.entries(params).filter(([, v]) => v !== undefined && v !== ''),
  )
}
