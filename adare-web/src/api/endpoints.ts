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

  // GUI agent (live view)
  agentRun: (id: string) => `/sessions/${id}/agent/run`,
  // NOTE: `agentStepImage` returns an absolute `/api/...` path because it is
  // consumed by an `<img src>`, which bypasses the axios baseURL.
  agentStepImage: (id: string, index: number) =>
    `/api/sessions/${id}/agent/steps/${index}.png`,

  // Playbooks
  playbookExecute: (id: string) => `/sessions/${id}/playbooks/execute`,
  playbookSave: '/playbooks/save',
  playbookLoad: (name: string) => `/playbooks/${name}`,

  // Resolve an ADARE VM name to the live-display connection info (uuid + the
  // same-origin `ws_path` the ADARE-owned viewer connects to). Mounted at the
  // app root (not under the `/api` axios baseURL), so consumers `fetch` this
  // absolute path directly. The viewer WS is same-origin — never `:8081`.
  vmWatchUrl: (name: string, viewOnly = true) =>
    `/api/vm-watch-url?name=${encodeURIComponent(name)}&view_only=${viewOnly}`,

  // Local VMs (database-tracked)
  localVms: '/local-vms',
  localVm: (id: string) => `/local-vms/${id}`,

  // VM instances (running VMs) and their snapshots
  vmInstances: '/vm-instances',
  vmInstanceUsage: '/vm-instances/usage',
  vmInstance: (id: string) => `/vm-instances/${id}`,
  vmInstanceSnapshots: (id: string) => `/vm-instances/${id}/snapshots`,
  vmInstanceSnapshotDelete: (id: string, name: string) =>
    `/vm-instances/${id}/snapshots/${encodeURIComponent(name)}`,

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
  runExperiment: (name: string) => `/experiments/${name}/run`,

  // Environments
  environments: '/environments',
  environment: (name: string) => `/environments/${name}`,
  environmentDelete: (name: string, force = false) =>
    `/environments/${name}?force=${force}`,
  verifyEnvironment: (name: string) => `/environments/${name}/verify`,
  osProfiles: '/environments/os-profiles',
  environmentCheckUrl: '/environments/check-url',

  // Runs
  runs: '/runs',
  run: (ulid: string) => `/runs/${ulid}`,
  runArtifacts: (ulid: string) => `/runs/${ulid}/artifacts`,
  runArtifact: (ulid: string, path: string) =>
    `/api/runs/${ulid}/artifacts/${path.split('/').map(encodeURIComponent).join('/')}`,

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
