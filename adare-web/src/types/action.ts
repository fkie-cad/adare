/**
 * TypeScript types for ADARE playbook actions
 * Mirrors backend action models
 */

// Base types
export type TargetType = 'image' | 'text'
export type StrategyType = 'sweep' | 'best_confidence' | 'closest_to' | 'leftmost' | 'rightmost' | 'topmost' | 'bottommost'
export type MouseButton = 'left' | 'right' | 'middle'
export type ScrollDirection = 'up' | 'down' | 'left' | 'right'

export interface Target {
  type: TargetType
  image?: string  // Path to image file
  text?: string   // Text to search for
}

export interface Strategy {
  type: StrategyType
  reference_image?: string  // For closest_to strategy
}

export interface WaitCondition {
  type: 'image_appears' | 'image_disappears' | 'text_appears' | 'text_disappears' | 'timeout'
  target?: Target
  timeout_seconds?: number
}

// Action base interface
export interface BaseAction {
  type: string
  description?: string
  screenshot_before?: boolean
  screenshot_after?: boolean
}

// GUI Actions
export interface ClickAction extends BaseAction {
  type: 'Click'
  target: Target
  strategy: StrategyType
  button?: MouseButton
  double_click?: boolean
  offset_x?: number
  offset_y?: number
}

export interface KeyboardAction extends BaseAction {
  type: 'Keyboard'
  text?: string
  keys?: string[]
  wait?: number
}

export interface ScrollAction extends BaseAction {
  type: 'Scroll'
  direction: ScrollDirection
  amount?: number
  target?: Target
}

export interface DragAction extends BaseAction {
  type: 'Drag'
  source: Target
  destination: Target
  strategy?: StrategyType
}

// Control Flow Actions
export interface WaitAction extends BaseAction {
  type: 'Wait'
  seconds?: number
  condition?: WaitCondition
}

export interface LoopAction extends BaseAction {
  type: 'Loop'
  iterations?: number
  condition?: WaitCondition
  actions: Action[]
}

export interface BlockAction extends BaseAction {
  type: 'Block'
  actions: Action[]
  description?: string
}

export interface ConditionalAction extends BaseAction {
  type: 'Conditional'
  condition: WaitCondition
  if_true: Action[]
  if_false?: Action[]
}

// Data Actions
export interface SetVarAction extends BaseAction {
  type: 'SetVar'
  name: string
  value: any
}

export interface FileReadAction extends BaseAction {
  type: 'FileRead'
  filename: string
  var_name: string
}

export interface FileWriteAction extends BaseAction {
  type: 'FileWrite'
  filename: string
  content: string
}

export interface ScreenshotAction extends BaseAction {
  type: 'Screenshot'
  filename: string
  region?: { x: number; y: number; width: number; height: number }
}

// System Actions
export interface CommandAction extends BaseAction {
  type: 'Command'
  command: string
  wait_for_completion?: boolean
  timeout_seconds?: number
}

export interface TestAction extends BaseAction {
  type: 'Test'
  test_name: string
  expected_result?: any
}

export interface CheckpointAction extends BaseAction {
  type: 'Checkpoint'
  name: string
  description?: string
}

export interface RestoreCheckpointAction extends BaseAction {
  type: 'RestoreCheckpoint'
  name: string
}

export interface ResetAction extends BaseAction {
  type: 'Reset'
  reset_type: 'soft' | 'hard'
}

// Union type for all actions
export type Action =
  | ClickAction
  | KeyboardAction
  | ScrollAction
  | DragAction
  | WaitAction
  | LoopAction
  | BlockAction
  | ConditionalAction
  | SetVarAction
  | FileReadAction
  | FileWriteAction
  | ScreenshotAction
  | CommandAction
  | TestAction
  | CheckpointAction
  | RestoreCheckpointAction
  | ResetAction

// Action execution result
export interface ActionResult {
  success: boolean
  message: string
  execution_time: number
  screenshot_path?: string
  error_message?: string
  coordinates?: [number, number]
  data?: any
}

// Action type metadata (for palette)
export interface ActionTypeMetadata {
  type: string
  category: 'gui' | 'control' | 'data' | 'system'
  display_name: string
  description: string
  icon: string
  default_params: Partial<Action>
}
