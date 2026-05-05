export const endpoints = {
  // Sessions
  sessions: '/sessions',
  sessionState: (id: string) => `/sessions/${id}/state`,
  sessionStart: '/sessions/start',
  sessionStop: (id: string) => `/sessions/${id}/stop`,
  sessionReset: (id: string, type: string) => `/sessions/${id}/reset?type=${type}`,
  sessionCleanup: '/sessions/cleanup',

  // Checkpoints
  checkpoints: (id: string) => `/sessions/${id}/checkpoints`,
  checkpointRestore: (id: string, name: string) => `/sessions/${id}/checkpoints/${name}/restore`,
  checkpointDelete: (id: string, name: string) => `/sessions/${id}/checkpoints/${name}`,

  // Actions
  actionExecute: (id: string) => `/sessions/${id}/actions/execute`,
  actionTypes: '/actions/types',

  // Playbooks
  playbookExecute: (id: string) => `/sessions/${id}/playbooks/execute`,
  playbookSave: '/playbooks/save',
  playbookLoad: (name: string) => `/playbooks/${name}`,

  // VirtualSpice REST/WebSocket proxy
  // NOTE: `vmProxy` returns a path starting with `/api/vm/...` because the
  // VirtualSpice proxy router is mounted at the app root (not under the `/api`
  // axios baseURL). Consumers should pass the full path to `fetch` or build an
  // absolute URL. WebSocket paths are likewise absolute.
  vmProxy: (path: string) => `/api/vm/${path}`,
  vmWebSocket: (path: string) => `/ws/vm/${path}`,
  vmEventsWebSocket: '/ws/vm-events',

  // Local VMs (database-tracked)
  localVms: '/local-vms',
  localVm: (id: string) => `/local-vms/${id}`,

  // Projects
  projects: '/projects',
  project: (path: string) => `/projects/${path}`,
  projectDelete: (name: string, path?: string) =>
    path ? `/projects/${name}?path=${encodeURIComponent(path)}` : `/projects/${name}`,

  // Experiments
  experiments: '/experiments',
  experimentsByTags: (tags: string) => `/experiments?tags=${encodeURIComponent(tags)}`,
  experiment: (name: string) => `/experiments/${name}`,
  experimentClone: (name: string) => `/experiments/${name}/clone`,
  experimentValidate: (name: string) => `/experiments/${name}/validate`,
  experimentEnvironments: (name: string) => `/experiments/${name}/environments`,

  // Environments
  environments: '/environments',
  environment: (name: string) => `/environments/${name}`,
  environmentDelete: (name: string, force = false) =>
    `/environments/${name}?force=${force}`,

  // Runs
  runs: '/runs',
  run: (ulid: string) => `/runs/${ulid}`,

  // Test functions
  testfunctions: '/testfunctions',
  testfunctionsByFile: (fileName: string) =>
    `/testfunctions?file_name=${encodeURIComponent(fileName)}`,
  testfunction: (dotnotation: string) => `/testfunctions/${dotnotation}`,

  // Web sync / auth
  webLogin: '/web/login',
  webLogout: '/web/logout',
  webStatus: '/web/status',
  webSync: '/web/sync',

  // System management
  manageDbStatus: '/manage/db-status',

  // Health
  health: '/health',
} as const
