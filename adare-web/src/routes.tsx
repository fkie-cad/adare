import {
  createRootRoute,
  createRoute,
} from '@tanstack/react-router'
import { RootLayout } from '@/components/layout/root-layout'

const rootRoute = createRootRoute({
  component: RootLayout,
})

const homeRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/',
  component: () => (
    <div className="p-6">
      <h2 className="text-xl font-semibold text-foreground">Home</h2>
      <p className="mt-2 text-muted-foreground">Welcome to ADARE Web.</p>
    </div>
  ),
})

const sessionsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/sessions',
  component: () => (
    <div className="p-6">
      <h2 className="text-xl font-semibold text-foreground">Sessions</h2>
      <p className="mt-2 text-muted-foreground">Session management coming soon.</p>
    </div>
  ),
})

const sessionDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/session/$id',
  component: () => (
    <div className="p-6">
      <h2 className="text-xl font-semibold text-foreground">Session</h2>
      <p className="mt-2 text-muted-foreground">Session detail view coming soon.</p>
    </div>
  ),
})

const playbookEditorRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/playbook/editor',
  component: () => (
    <div className="p-6">
      <h2 className="text-xl font-semibold text-foreground">Playbook Editor</h2>
      <p className="mt-2 text-muted-foreground">Playbook editor coming soon.</p>
    </div>
  ),
})

export const routeTree = rootRoute.addChildren([
  homeRoute,
  sessionsRoute,
  sessionDetailRoute,
  playbookEditorRoute,
])
