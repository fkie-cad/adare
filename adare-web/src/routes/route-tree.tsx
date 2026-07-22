import { createRootRouteWithContext, createRoute } from '@tanstack/react-router'
import type { QueryClient } from '@tanstack/react-query'
import { MainLayout } from '@/components/layout/main-layout'
import HomePage from '@/pages/home'
import RunsListPage from '@/pages/runs-list'
import ExperimentsListPage from '@/pages/experiments-list'
import ProjectsListPage from '@/pages/projects-list'
import EnvironmentsListPage from '@/pages/environments-list'
import AgentLivePage from '@/pages/agent-live'
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

const experimentsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/experiments',
  component: ExperimentsListPage,
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

const agentRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/agent',
  component: AgentLivePage,
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
  experimentsRoute,
  projectsRoute,
  environmentsRoute,
  agentRoute,
  vmWatchRoute,
])
