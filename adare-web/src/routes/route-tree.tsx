import { createRootRouteWithContext, createRoute } from '@tanstack/react-router'
import type { QueryClient } from '@tanstack/react-query'
import { MainLayout } from '@/components/layout/main-layout'
import HomePage from '@/pages/home'
import RunsListPage from '@/pages/runs-list'
import RunDetailPage from '@/pages/run-detail'
import ExperimentsListPage from '@/pages/experiments-list'
import ExperimentDetailPage from '@/pages/experiment-detail'
import ProjectsListPage from '@/pages/projects-list'
import EnvironmentsListPage from '@/pages/environments-list'
import EnvironmentDetailPage from '@/pages/environment-detail'
import VmsListPage from '@/pages/vms-list'
import VmDetailPage from '@/pages/vm-detail'
import WorkbenchPage from '@/pages/workbench'
import VmWatchPage from '@/pages/vm-watch'

interface RouterContext {
  queryClient: QueryClient
}

const rootRoute = createRootRouteWithContext<RouterContext>()({
  component: MainLayout,
})

const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/',
  component: HomePage,
})

const runsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/runs',
  component: RunsListPage,
  validateSearch: (search: Record<string, unknown>): { focus?: string } => {
    const focus = search.focus
    return typeof focus === 'string' && focus.length > 0 ? { focus } : {}
  },
})

const runDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/runs/$ulid',
  component: RunDetailPage,
})

const experimentsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/experiments',
  component: ExperimentsListPage,
})

const experimentDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/experiments/$name',
  component: ExperimentDetailPage,
})

const projectsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/projects',
  component: ProjectsListPage,
})

const environmentsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/environments',
  component: EnvironmentsListPage,
})

const environmentDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/environments/$name',
  component: EnvironmentDetailPage,
})

const vmsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/vms',
  component: VmsListPage,
})

const vmDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/vms/$instanceId',
  component: VmDetailPage,
})

const developRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/develop',
  component: WorkbenchPage,
  validateSearch: (search: Record<string, unknown>): { experiment?: string; environment?: string } => {
    const experiment = search.experiment
    const environment = search.environment
    return {
      ...(typeof experiment === 'string' && experiment.length > 0 ? { experiment } : {}),
      ...(typeof environment === 'string' && environment.length > 0 ? { environment } : {}),
    }
  },
})

const vmWatchRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/vm/watch',
  component: VmWatchPage,
  validateSearch: (
    search: Record<string, unknown>,
  ): { name?: string; viewOnly?: boolean } => {
    const rawName = search.name
    const name = typeof rawName === 'string' && rawName.length > 0 ? rawName : undefined
    // Accept either `view_only` (from CLI/pop-out URLs) or `viewOnly`.
    const rawViewOnly = search.view_only ?? search.viewOnly
    const viewOnly =
      rawViewOnly === true || rawViewOnly === 'true' || rawViewOnly === '1'
    return name ? { name, viewOnly } : { viewOnly }
  },
})

export const routeTree = rootRoute.addChildren([
  indexRoute,
  runsRoute,
  runDetailRoute,
  experimentsRoute,
  experimentDetailRoute,
  projectsRoute,
  environmentsRoute,
  environmentDetailRoute,
  vmsRoute,
  vmDetailRoute,
  developRoute,
  vmWatchRoute,
])
