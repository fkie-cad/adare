# ADARE Web Frontend

Web interface for ADARE dev mode sessions with visual playbook builder.

## Features

- Start and manage dev sessions
- Visual drag-and-drop playbook builder
- Real-time action execution and testing
- Checkpoint management (create/restore/delete)
- YAML playbook export
- WebSocket real-time updates

## Tech Stack

- **Vue 3** - Progressive JavaScript framework
- **TypeScript** - Type safety
- **Vite** - Fast build tool
- **Pinia** - State management
- **PrimeVue** - UI component library
- **Vue Router** - Client-side routing
- **Axios** - HTTP client
- **Monaco Editor** - YAML editing

## Project Structure

```
adare-web/
├── src/
│   ├── components/        # Vue components
│   │   ├── actions/       # Action builder components
│   │   ├── checkpoint/    # Checkpoint management
│   │   ├── execution/     # Execution log components
│   │   ├── playbook/      # Playbook builder components
│   │   ├── session/       # Session management
│   │   └── common/        # Shared components
│   ├── views/             # Page components
│   ├── stores/            # Pinia stores
│   ├── services/          # API services
│   ├── types/             # TypeScript types
│   ├── utils/             # Utility functions
│   ├── router/            # Vue Router config
│   ├── assets/            # Static assets
│   └── main.ts            # Entry point
├── package.json           # Dependencies
├── vite.config.ts         # Vite configuration
├── tsconfig.json          # TypeScript config
└── index.html             # HTML template
```

## Development Setup

### Prerequisites

- Node.js 18+ and npm
- Running ADARE backend (see backend README)

### Install Dependencies

```bash
cd adare-web
npm install
```

### Start Development Server

```bash
# Start Vite dev server (runs on port 3000)
npm run dev
```

The dev server will proxy API requests to the backend at `http://localhost:8000`.

### Backend Setup

Before running the frontend, start the ADARE backend:

```bash
cd ../adare
poetry install
adare webserver start --dev --port 8000
```

The backend must be running for the frontend to function.

## Build for Production

```bash
npm run build
```

This creates an optimized build in the `dist/` directory that can be served by the FastAPI backend.

## Type Checking

```bash
npm run type-check
```

## Project Status

**Phase 2 (Frontend Setup): COMPLETE ✅**

Completed:
- ✅ Vue 3 project structure
- ✅ TypeScript type definitions
- ✅ API service layer (REST + WebSocket)
- ✅ Pinia stores (session, playbook, execution, checkpoint)
- ✅ Vue Router setup
- ✅ Basic view components (Home, Sessions, DevSession, PlaybookEditor)
- ✅ App layout with navigation

Next steps (Phase 3+):
- Action palette with drag-and-drop
- Monaco YAML editor integration
- Full playbook builder components
- Checkpoint management UI
- Execution log with real-time updates
- Complete DevSessionPage implementation

## API Endpoints

The frontend connects to these backend endpoints:

- `GET /api/health` - Health check
- `GET /api/sessions` - List sessions
- `POST /api/sessions/start` - Start session
- `POST /api/sessions/{id}/stop` - Stop session
- `GET /api/sessions/{id}/state` - Get session state
- `POST /api/sessions/{id}/reset` - Reset session
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

## Contributing

See main ADARE repository guidelines. Keep files under 1000 lines and follow Vue 3 Composition API patterns.
