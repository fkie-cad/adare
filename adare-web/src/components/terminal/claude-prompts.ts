/**
 * Opening prompts for Claude sessions started from a page. They point Claude at
 * the ADARE skills and CLI rather than restating them, and leave decisions that
 * boot VMs to the user.
 */

export function newExperimentPrompt(): string {
  return (
    'I want to build a new ADARE experiment in this project. Ask me which forensic question it should answer ' +
    'and on which environments, then create the experiment, write and validate its playbook and tests. ' +
    'Use the adare-overview skill to pick the steps, and check `adare system capacity` before starting runs.'
  )
}

export function experimentPrompt(name: string, environments: string[]): string {
  const envs = environments.length ? ` (environments: ${environments.join(', ')})` : ''
  return (
    `Let's work on the ADARE experiment "${name}" in this project${envs}. Read its playbook and tests, ` +
    'validate it with the adare CLI, and summarize what it does and anything that looks wrong; then ask me ' +
    'what to change. Use the adare-playbook and adare-experiment skills.'
  )
}

export function debugRunPrompt(run: {
  ulid: string
  experiment_name?: string
  environment_name?: string
  status?: string
  result_status?: string
}): string {
  const what = [
    run.experiment_name && `experiment "${run.experiment_name}"`,
    run.environment_name && `environment "${run.environment_name}"`,
    run.status && `status ${run.status}`,
    run.result_status && `result ${run.result_status}`,
  ]
    .filter(Boolean)
    .join(', ')
  return (
    `Debug ADARE run ${run.ulid}${what ? ` (${what})` : ''}. Inspect it with \`adare runs info ${run.ulid}\`, ` +
    'its logs and screenshots, find the first failing action or test and why, and propose a concrete fix to ' +
    "the playbook. Use the adare-experiment and adare-playbook skills, and don't start new runs without asking."
  )
}
