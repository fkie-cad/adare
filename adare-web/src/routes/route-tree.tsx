import { createRootRouteWithContext, createRoute } from '@tanstack/react-router'
import type { QueryClient } from '@tanstack/react-query'
import { MainLayout } from '@/components/layout/main-layout'
import HomePage from '@/pages/home'
import RunsListPage from '@/pages/runs-list'
import ExperimentsListPage from '@/pages/experiments-list'
import ProjectsListPage from '@/pages/projects-list'
import EnvironmentsListPage from '@/pages/environments-list'

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

export const routeTree = rootRoute.addChildren([
  indexRoute,
  runsRoute,
  experimentsRoute,
  projectsRoute,
  environmentsRoute,
])
