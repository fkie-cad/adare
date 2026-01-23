# ADARE Web - Quick Start Guide

## Prerequisites

- Node.js 18+ and npm
- Running ADARE backend on port 8000

## Installation

```bash
cd adare-web
npm install
```

## Development

### 1. Start the Backend

In a separate terminal:

```bash
cd ../adare
poetry install
adare webserver start --dev --port 8000
```

You should see:
```
INFO:     Uvicorn running on http://127.0.0.1:8000
INFO:     Application startup complete
```

### 2. Start the Frontend

```bash
npm run dev
```

You should see:
```
VITE v5.x.x ready in xxx ms

➜  Local:   http://localhost:3000/
➜  Network: use --host to expose
```

### 3. Open in Browser

Navigate to: http://localhost:3000

You should see the ADARE Web homepage.

## Available Scripts

```bash
npm run dev         # Start development server (port 3000)
npm run build       # Build for production
npm run preview     # Preview production build
npm run type-check  # Run TypeScript type checking
```

## Project Structure

```
src/
├── components/      # Vue components (Phase 3+)
├── views/          # Page components
│   ├── HomePage.vue
│   ├── SessionsPage.vue
│   ├── DevSessionPage.vue
│   └── PlaybookEditorPage.vue
├── stores/         # Pinia state management
│   ├── sessionStore.ts
│   ├── playbookStore.ts
│   ├── executionStore.ts
│   └── checkpointStore.ts
├── services/       # API clients
│   ├── api.ts
│   ├── sessionService.ts
│   ├── actionService.ts
│   ├── checkpointService.ts
│   ├── playbookService.ts
│   └── websocket.ts
├── types/          # TypeScript types
│   ├── session.ts
│   ├── action.ts
│   └── api.ts
├── router/         # Vue Router
│   └── index.ts
├── assets/         # Global CSS
│   └── main.css
└── main.ts         # Entry point
```

## Testing the Integration

### 1. Test Backend Connection

Open DevTools Console and check for:
```
CLAUDE: ADARE Web frontend initialized
```

### 2. Test Session List

1. Navigate to "Sessions" page
2. You should see either:
   - Empty state: "No active sessions"
   - List of running sessions (if any exist)

### 3. Test Session Creation

1. Click "Start New Session"
2. Fill in:
   - Project: `test-project`
   - Experiment: `test-experiment`
   - Environment: `win10-env`
3. Click "Start Session"
4. You should be redirected to the dev session page

### 4. Test WebSocket Connection

Check the connection status indicator in the header:
- 🟢 Green "Connected" = WebSocket connected
- 🔴 Red "Disconnected" = WebSocket not connected

## API Endpoints (Backend)

The frontend connects to these endpoints:

- `GET /api/health` - Health check
- `GET /api/sessions` - List sessions
- `POST /api/sessions/start` - Start session
- `POST /api/sessions/{id}/stop` - Stop session
- `GET /api/sessions/{id}/state` - Get session state
- `POST /api/sessions/{id}/reset?type=soft|hard` - Reset session
- `POST /api/sessions/{id}/actions/execute` - Execute action
- `GET /api/sessions/{id}/checkpoints` - List checkpoints
- `POST /api/sessions/{id}/checkpoints` - Create checkpoint
- `POST /api/sessions/{id}/checkpoints/{name}/restore` - Restore checkpoint
- `DELETE /api/sessions/{id}/checkpoints/{name}` - Delete checkpoint
- `WS /ws/{session_id}` - WebSocket for real-time updates

## WebSocket Events

Real-time updates are received via WebSocket:

- `action_start` - Action execution started
- `action_complete` - Action completed successfully
- `action_error` - Action failed
- `session_state` - Session state updated
- `vm_status` - VM status changed
- `checkpoint_created` - Checkpoint created
- `checkpoint_restored` - Checkpoint restored
- `checkpoint_deleted` - Checkpoint deleted

## Troubleshooting

### Frontend won't start

```bash
# Clear node_modules and reinstall
rm -rf node_modules package-lock.json
npm install
```

### Backend not responding

Check that the backend is running:
```bash
curl http://localhost:8000/api/health
```

Expected response:
```json
{
  "success": true,
  "data": {
    "status": "healthy",
    "timestamp": "2026-01-22T..."
  }
}
```

### WebSocket not connecting

1. Check backend logs for WebSocket errors
2. Check browser console for connection errors
3. Verify firewall allows WebSocket connections
4. Try disabling browser extensions

### TypeScript errors

```bash
npm run type-check
```

If errors persist, check:
- `tsconfig.json` is properly configured
- `src/vite-env.d.ts` exists
- All imports use correct paths

## Development Tips

### Hot Module Replacement (HMR)

Vite supports HMR - changes to `.vue`, `.ts`, `.css` files will update instantly without full page reload.

### Vue DevTools

Install Vue DevTools browser extension for:
- Component inspector
- Vuex/Pinia state inspector
- Performance profiling

### API Testing

Use the backend's interactive docs:
http://localhost:8000/docs

## Next Steps

See `PHASE2_COMPLETE.md` for implementation status and roadmap.

Phase 3 will implement:
- Action palette with drag-and-drop
- Monaco YAML editor
- Full playbook builder
- Checkpoint management UI
- Execution log with real-time updates
