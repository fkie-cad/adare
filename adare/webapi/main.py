"""
ADARE Web API - FastAPI application for web frontend.

Provides REST and WebSocket endpoints for dev mode session control.
"""

import logging
from pathlib import Path
from typing import Optional, Literal

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from adare.api import AdareAPI
from adare.core.dto.devmode import (
    DevSessionStartRequest,
    DevSessionStopRequest,
    DevActionExecuteRequest,
    DevPlaybookExecuteRequest,
    DevResetRequest,
    DevCheckpointCreateRequest,
    DevCheckpointDeleteRequest,
    DevCheckpointRestoreRequest,
    DevCheckpointListRequest,
    DevSessionListRequest,
    DevSessionStateRequest,
    DevSessionCleanupRequest,
)
from adare.webapi.adapters import result_to_response
from adare.webapi.websocket_manager import ws_manager

logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="ADARE Web API",
    description="Web API for ADARE dev mode session control",
    version="1.0.0",
)

# CORS middleware for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:3002",
    ],  # Vite dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize ADARE API facade
api = AdareAPI()


# =============================================================================
# Pydantic Models for Request/Response
# =============================================================================


class SessionStartRequest(BaseModel):
    """Request to start a new session."""

    project_path: str
    experiment_name: str
    environment_name: str
    gui_mode: Optional[str] = None
    vm_memory: Optional[int] = None
    vm_cpus: Optional[int] = None
    debug_screenshots: bool = False


class SessionStopRequest(BaseModel):
    """Request to stop a session."""

    remove_resources: bool = False


class ActionExecuteRequest(BaseModel):
    """Request to execute a single action."""

    action_yaml: str = Field(..., description="YAML string of the action")


class PlaybookExecuteRequest(BaseModel):
    """Request to execute a playbook."""

    actions: list[dict] = Field(..., description="List of action dictionaries")
    settings: dict = Field(default_factory=dict, description="Playbook settings")


class CheckpointCreateRequest(BaseModel):
    """Request to create a checkpoint."""

    name: str
    description: str = ""


class CheckpointRestoreRequest(BaseModel):
    """Request to restore a checkpoint."""

    name: str


class PlaybookSaveRequest(BaseModel):
    """Request to save a playbook."""

    filename: str
    actions: list[dict]
    settings: dict = Field(default_factory=dict)


# =============================================================================
# Session Management Endpoints
# =============================================================================


@app.post("/api/sessions/start")
async def start_session(request: SessionStartRequest):
    """
    Start a new dev mode session.

    Returns:
        Session info on success, error on failure
    """
    logger.info(f"Starting session for {request.experiment_name}")

    dto = DevSessionStartRequest(
        project_path=Path(request.project_path),
        experiment_name=request.experiment_name,
        environment_name=request.environment_name,
        gui_mode=request.gui_mode,
        vm_memory=request.vm_memory,
        vm_cpus=request.vm_cpus,
        debug_screenshots=request.debug_screenshots,
    )

    result = api.devmode.start_session(dto)

    if result.is_success():
        # Send WebSocket notification
        session_id = result.value.session_id
        await ws_manager.send_session_state(
            session_id,
            {
                "status": "started",
                "vm_running": result.value.vm_running,
            },
        )

    return result_to_response(result)


@app.post("/api/sessions/{session_id}/stop")
async def stop_session(session_id: str, request: SessionStopRequest = SessionStopRequest()):
    """
    Stop a dev mode session.

    Args:
        session_id: Session ID
        request: Stop options

    Returns:
        Success indicator
    """
    logger.info(f"Stopping session {session_id}")

    dto = DevSessionStopRequest(
        session_id=session_id, remove_resources=request.remove_resources
    )

    result = api.devmode.stop_session(dto)

    if result.is_success():
        await ws_manager.send_session_state(
            session_id, {"status": "stopped"}
        )

    return result_to_response(result)


@app.get("/api/sessions")
async def list_sessions(project_path: Optional[str] = None):
    """
    List all active dev mode sessions.

    Args:
        project_path: Optional project filter

    Returns:
        List of session items
    """
    dto = DevSessionListRequest(
        project_path=Path(project_path) if project_path else None
    )

    result = api.devmode.list_sessions(dto)
    return result_to_response(result)


@app.get("/api/sessions/{session_id}/state")
async def get_session_state(session_id: str):
    """
    Get current session state.

    Args:
        session_id: Session ID

    Returns:
        Session state information
    """
    dto = DevSessionStateRequest(session_id=session_id)
    result = api.devmode.get_state(dto)
    return result_to_response(result)


@app.post("/api/sessions/cleanup")
async def cleanup_sessions(project_path: Optional[str] = None):
    """
    Cleanup stale sessions.

    Args:
        project_path: Optional project filter

    Returns:
        Cleanup statistics
    """
    dto = DevSessionCleanupRequest(
        project_path=Path(project_path) if project_path else None
    )

    result = api.devmode.cleanup_stale_sessions(dto)
    return result_to_response(result)


# =============================================================================
# Action Execution Endpoints
# =============================================================================


@app.post("/api/sessions/{session_id}/actions/execute")
async def execute_action(session_id: str, request: ActionExecuteRequest):
    """
    Execute a single action.

    Args:
        session_id: Session ID
        request: Action YAML

    Returns:
        Action execution result
    """
    logger.info(f"Executing action for session {session_id}")

    # Send action start event
    await ws_manager.send_action_start(
        session_id, action_type="action", description="Executing action"
    )

    dto = DevActionExecuteRequest(
        session_id=session_id,
        action_source="yaml",
        action_content=request.action_yaml,
    )

    result = api.devmode.execute_action(dto)

    # Send action complete or error event
    if result.is_success():
        await ws_manager.send_action_complete(
            session_id,
            action_type="action",
            success=result.value.success,
            result={
                "message": result.value.message,
                "execution_time": result.value.execution_time,
                "coordinates": result.value.coordinates,
            },
        )
    else:
        # Send error event on failure
        error_msg = result.error if hasattr(result, 'error') else "Action execution failed"
        await ws_manager.send_action_error(session_id, "action", str(error_msg))

    return result_to_response(result)


@app.post("/api/sessions/{session_id}/playbooks/execute")
async def execute_playbook(session_id: str, request: PlaybookExecuteRequest):
    """
    Execute a full playbook.

    Args:
        session_id: Session ID
        request: Playbook data (actions + settings)

    Returns:
        Playbook execution result
    """
    logger.info(f"Executing playbook for session {session_id} ({len(request.actions)} actions)")

    # Convert actions and settings to YAML
    import yaml

    playbook_dict = {"settings": request.settings, "actions": request.actions}
    yaml_content = yaml.dump(playbook_dict, default_flow_style=False, sort_keys=False)

    # Write to temp file for parsing
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
        f.write(yaml_content)
        temp_path = f.name

    try:
        dto = DevPlaybookExecuteRequest(
            session_id=session_id, playbook_source="file", playbook_content=temp_path
        )

        result = api.devmode.execute_playbook(dto)
        return result_to_response(result)
    finally:
        # Clean up temp file
        Path(temp_path).unlink(missing_ok=True)


# =============================================================================
# Reset Endpoints
# =============================================================================


@app.post("/api/sessions/{session_id}/reset")
async def reset_session(
    session_id: str, reset_type: Literal["soft", "hard"] = Query("soft")
):
    """
    Reset session state.

    Args:
        session_id: Session ID
        reset_type: 'soft' (variables only) or 'hard' (full VM restore)

    Returns:
        Reset result
    """
    logger.info(f"Resetting session {session_id} (type={reset_type})")

    dto = DevResetRequest(session_id=session_id, reset_type=reset_type)

    if reset_type == "soft":
        result = api.devmode.reset_soft(dto)
    else:
        result = api.devmode.reset_hard(dto)

    return result_to_response(result)


# =============================================================================
# Checkpoint Endpoints
# =============================================================================


@app.post("/api/sessions/{session_id}/checkpoints")
async def create_checkpoint(session_id: str, request: CheckpointCreateRequest):
    """
    Create a named checkpoint.

    Args:
        session_id: Session ID
        request: Checkpoint name and description

    Returns:
        Success indicator
    """
    logger.info(f"Creating checkpoint '{request.name}' for session {session_id}")

    dto = DevCheckpointCreateRequest(
        session_id=session_id, name=request.name, description=request.description
    )

    result = api.devmode.create_checkpoint(dto)

    if result.is_success():
        await ws_manager.send_checkpoint_created(session_id, request.name)

    return result_to_response(result)


@app.get("/api/sessions/{session_id}/checkpoints")
async def list_checkpoints(session_id: str):
    """
    List available checkpoints.

    Args:
        session_id: Session ID

    Returns:
        List of checkpoints
    """
    dto = DevCheckpointListRequest(session_id=session_id)
    result = api.devmode.list_checkpoints(dto)
    return result_to_response(result)


@app.post("/api/sessions/{session_id}/checkpoints/{checkpoint_name}/restore")
async def restore_checkpoint(session_id: str, checkpoint_name: str):
    """
    Restore to a checkpoint.

    Args:
        session_id: Session ID
        checkpoint_name: Checkpoint name

    Returns:
        Success indicator
    """
    logger.info(f"Restoring checkpoint '{checkpoint_name}' for session {session_id}")

    dto = DevCheckpointRestoreRequest(session_id=session_id, name=checkpoint_name)
    result = api.devmode.restore_checkpoint(dto)

    # Broadcast checkpoint restored event
    if result.is_success():
        await ws_manager.send_checkpoint_restored(session_id, checkpoint_name)

    return result_to_response(result)


@app.delete("/api/sessions/{session_id}/checkpoints/{checkpoint_name}")
async def delete_checkpoint(session_id: str, checkpoint_name: str):
    """
    Delete a checkpoint.

    Args:
        session_id: Session ID
        checkpoint_name: Checkpoint name

    Returns:
        Success indicator
    """
    logger.info(f"Deleting checkpoint '{checkpoint_name}' for session {session_id}")

    dto = DevCheckpointDeleteRequest(session_id=session_id, name=checkpoint_name)
    result = api.devmode.delete_checkpoint(dto)

    # Broadcast checkpoint deleted event
    if result.is_success():
        await ws_manager.send_checkpoint_deleted(session_id, checkpoint_name)

    return result_to_response(result)


# =============================================================================
# Playbook Endpoints
# =============================================================================


@app.post("/api/playbooks/save")
async def save_playbook(request: PlaybookSaveRequest):
    """
    Save a playbook to YAML file.

    Args:
        request: Playbook data

    Returns:
        File path on success
    """
    import yaml

    playbook_dict = {"settings": request.settings, "actions": request.actions}

    # Save to playbooks directory (create if doesn't exist)
    playbooks_dir = Path("playbooks")
    playbooks_dir.mkdir(exist_ok=True)

    file_path = playbooks_dir / request.filename
    if not file_path.suffix:
        file_path = file_path.with_suffix(".yml")

    with open(file_path, "w") as f:
        yaml.dump(playbook_dict, f, default_flow_style=False, sort_keys=False)

    logger.info(f"Saved playbook to {file_path}")

    return {"success": True, "data": {"file_path": str(file_path)}}


@app.get("/api/playbooks/{filename}")
async def load_playbook(filename: str):
    """
    Load a playbook from YAML file.

    Args:
        filename: Playbook filename

    Returns:
        Playbook data (actions + settings)
    """
    import yaml

    playbooks_dir = Path("playbooks")
    file_path = playbooks_dir / filename

    if not file_path.suffix:
        file_path = file_path.with_suffix(".yml")

    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Playbook '{filename}' not found")

    with open(file_path, "r") as f:
        playbook_dict = yaml.safe_load(f)

    return {
        "success": True,
        "data": {
            "actions": playbook_dict.get("actions", []),
            "settings": playbook_dict.get("settings", {}),
        },
    }


@app.get("/api/actions/types")
async def get_action_types():
    """
    Get metadata for all available action types.

    Returns:
        Action type definitions with display metadata
    """
    # Define action type metadata with frontend-friendly format
    action_types = [
        {
            "type": "Click",
            "category": "gui",
            "display_name": "Click",
            "description": "Click on a target (image or text)",
            "icon": "pi-mouse-pointer",
            "default_params": {
                "target": {"type": "text", "text": ""},
                "strategy": "sweep",
                "button": "left",
            },
        },
        {
            "type": "Keyboard",
            "category": "gui",
            "display_name": "Keyboard",
            "description": "Type text or press keys",
            "icon": "pi-keyboard",
            "default_params": {"text": ""},
        },
        {
            "type": "Scroll",
            "category": "gui",
            "display_name": "Scroll",
            "description": "Scroll in a direction",
            "icon": "pi-arrows-v",
            "default_params": {"direction": "down", "amount": 3},
        },
        {
            "type": "Drag",
            "category": "gui",
            "display_name": "Drag",
            "description": "Drag from source to destination",
            "icon": "pi-arrows-alt",
            "default_params": {
                "source": {"type": "text", "text": ""},
                "destination": {"type": "text", "text": ""},
            },
        },
        {
            "type": "Wait",
            "category": "control",
            "display_name": "Wait",
            "description": "Wait for a fixed duration",
            "icon": "pi-clock",
            "default_params": {"seconds": 5},
        },
        {
            "type": "Loop",
            "category": "control",
            "display_name": "Loop",
            "description": "Repeat actions multiple times",
            "icon": "pi-refresh",
            "default_params": {"iterations": 3, "actions": []},
        },
        {
            "type": "Block",
            "category": "control",
            "display_name": "Block",
            "description": "Group actions together",
            "icon": "pi-box",
            "default_params": {"actions": [], "description": ""},
        },
        {
            "type": "Conditional",
            "category": "control",
            "display_name": "Conditional",
            "description": "Execute actions based on condition",
            "icon": "pi-question-circle",
            "default_params": {
                "condition": {"type": "timeout", "timeout_seconds": 10},
                "if_true": [],
            },
        },
        {
            "type": "Screenshot",
            "category": "data",
            "display_name": "Screenshot",
            "description": "Capture a screenshot",
            "icon": "pi-camera",
            "default_params": {"filename": "screenshot.png"},
        },
        {
            "type": "SetVar",
            "category": "data",
            "display_name": "Set Variable",
            "description": "Set a variable value",
            "icon": "pi-pencil",
            "default_params": {"name": "my_var", "value": ""},
        },
        {
            "type": "FileRead",
            "category": "data",
            "display_name": "File Read",
            "description": "Read file contents into variable",
            "icon": "pi-file",
            "default_params": {"filename": "", "var_name": "file_content"},
        },
        {
            "type": "FileWrite",
            "category": "data",
            "display_name": "File Write",
            "description": "Write content to a file",
            "icon": "pi-file-edit",
            "default_params": {"filename": "", "content": ""},
        },
        {
            "type": "Command",
            "category": "system",
            "display_name": "Command",
            "description": "Execute a shell command",
            "icon": "pi-terminal",
            "default_params": {"command": "", "wait_for_completion": True, "timeout_seconds": 30},
        },
        {
            "type": "Test",
            "category": "system",
            "display_name": "Test",
            "description": "Run a test function",
            "icon": "pi-check-circle",
            "default_params": {"test_name": ""},
        },
        {
            "type": "Checkpoint",
            "category": "system",
            "display_name": "Checkpoint",
            "description": "Create a VM checkpoint",
            "icon": "pi-bookmark",
            "default_params": {"name": "", "description": ""},
        },
        {
            "type": "RestoreCheckpoint",
            "category": "system",
            "display_name": "Restore Checkpoint",
            "description": "Restore a VM checkpoint",
            "icon": "pi-replay",
            "default_params": {"name": ""},
        },
        {
            "type": "Reset",
            "category": "system",
            "display_name": "Reset",
            "description": "Reset the VM state",
            "icon": "pi-undo",
            "default_params": {"reset_type": "soft"},
        },
    ]

    return {"success": True, "data": action_types}


# =============================================================================
# WebSocket Endpoint
# =============================================================================


@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """
    WebSocket endpoint for real-time session updates.

    Args:
        websocket: WebSocket connection
        session_id: Session ID to subscribe to
    """
    await ws_manager.connect(websocket, session_id)

    try:
        # Send initial connection confirmation
        await websocket.send_json(
            {"type": "connected", "session_id": session_id, "message": "WebSocket connected"}
        )

        # Keep connection alive and handle incoming messages
        while True:
            try:
                # Receive messages (ping/pong, etc.)
                data = await websocket.receive_json()

                # Handle ping
                if data.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})

            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error(f"WebSocket error for session {session_id}: {e}")
                break

    finally:
        await ws_manager.disconnect(websocket, session_id)


# =============================================================================
# Health Check
# =============================================================================


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "adare-web-api"}


# =============================================================================
# Static File Serving (for production)
# =============================================================================

# Mount static files (built frontend) - will be added after frontend is built
# app.mount("/", StaticFiles(directory="adare-web/dist", html=True), name="static")


# =============================================================================
# REST API Routes (Phase 3 - unified web frontend)
# =============================================================================

from adare.webapi.routes.projects import router as projects_router
from adare.webapi.routes.experiments import router as experiments_router
from adare.webapi.routes.environments import router as environments_router
from adare.webapi.routes.runs import router as runs_router
from adare.webapi.routes.testfunctions import router as testfunctions_router
from adare.webapi.routes.local_vms import router as local_vms_router
from adare.webapi.routes.web_sync import router as web_sync_router
from adare.webapi.routes.manage import router as manage_router
from adare.webapi.vm_proxy import router as vm_proxy_router

app.include_router(projects_router)
app.include_router(experiments_router)
app.include_router(environments_router)
app.include_router(runs_router)
app.include_router(testfunctions_router)
app.include_router(local_vms_router)
app.include_router(web_sync_router)
app.include_router(manage_router)
app.include_router(vm_proxy_router)


# =============================================================================
# SPA Fallback (serve built frontend static files)
# =============================================================================

from pathlib import Path

_frontend_dist = Path(__file__).resolve().parent.parent.parent.parent.parent / "adare-web" / "dist"


@app.get("/{path:path}")
async def spa_fallback(path: str):
    """Serve static files from the built frontend, with SPA index.html fallback."""
    if not _frontend_dist.is_dir():
        raise HTTPException(status_code=404, detail="Frontend not built. Run: pnpm build")
    file_path = (_frontend_dist / path).resolve()
    # Prevent path traversal
    if not str(file_path).startswith(str(_frontend_dist)):
        raise HTTPException(status_code=404)
    if file_path.is_file():
        return FileResponse(file_path)
    return FileResponse(_frontend_dist / "index.html")
