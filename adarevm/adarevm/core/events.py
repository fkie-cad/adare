from typing import Callable, Awaitable, Optional
import contextlib
import asyncio
import time

from adarelib.event.event import Event
from adarelib.event.ws import EVENT

import logging
log = logging.getLogger(__name__)

class EventCtxManager(contextlib.AbstractContextManager):
    """
    Context manager for handling events with WebSocket streaming support.
    
    This manager can work with both the legacy EVENT/WS format and
    the new WebSocket event streaming format.
    """
    event: Event
    log_func: Callable[[str], Awaitable[None]]
    websocket_broadcaster: Optional[Callable] = None

    def __init__(self, event: Event, log_func: Callable[[str], Awaitable[None]], websocket_broadcaster: Optional[Callable] = None):
        self.log_func = log_func
        self.event = event
        self.websocket_broadcaster = websocket_broadcaster

    def _log(self):
        """Log the event using the legacy format."""
        event_ws_msg = EVENT(self.event)
        
        # Create coroutine but don't await it - let the caller handle it
        if asyncio.iscoroutinefunction(self.log_func):
            # Schedule the coroutine to run in the event loop
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(self.log_func(event_ws_msg.encode()))
                else:
                    loop.run_until_complete(self.log_func(event_ws_msg.encode()))
            except RuntimeError:
                # No event loop running, just log to file
                log.info(f"Event: {event_ws_msg.encode()}")
        else:
            # Synchronous function
            self.log_func(event_ws_msg.encode())

    async def _broadcast_websocket_event(self):
        """Broadcast event over WebSocket if broadcaster is available."""
        if self.websocket_broadcaster:
            try:
                # Convert event to WebSocket format
                event_type = self._get_websocket_event_type()
                event_data = self._convert_to_websocket_data()
                
                await self.websocket_broadcaster(event_type, event_data)
            except Exception as e:
                log.error(f"Failed to broadcast WebSocket event: {e}")

    def _get_websocket_event_type(self) -> str:
        """Convert Event type to WebSocket event type."""
        event_class = self.event.__class__.__name__
        
        # Map event types to WebSocket event types
        mapping = {
            'TestEvent': 'test_progress',
            'ErrorEvent': 'error',
        }
        
        return mapping.get(event_class, 'log')

    def _convert_to_websocket_data(self) -> dict:
        """Convert Event to WebSocket data format."""
        data = {
            "timestamp": time.time(),
            "status": getattr(self.event, 'status', None),
        }
        
        # Add event-specific data
        if hasattr(self.event, 'test_name'):
            data['test_name'] = self.event.test_name
        if hasattr(self.event, 'error_name'):
            data['error_name'] = self.event.error_name
        if hasattr(self.event, 'error_msg'):
            data['error_message'] = self.event.error_msg
        if hasattr(self.event, 'result'):
            data['result'] = {
                'status': self.event.result.status,
                'details': getattr(self.event.result, 'details', [])
            }
        
        return data

    def __enter__(self):
        self._log()
        
        # Also broadcast over WebSocket if available
        if self.websocket_broadcaster:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(self._broadcast_websocket_event())
            except RuntimeError:
                pass  # No event loop running
        
        return self

    def update(self, event: Event):
        self.event = event
        self._log()
        
        # Also broadcast over WebSocket if available  
        if self.websocket_broadcaster:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(self._broadcast_websocket_event())
            except RuntimeError:
                pass  # No event loop running

    def __exit__(self, exc_type, exc_value, traceback):
        pass


# Global WebSocket broadcaster reference
_websocket_broadcaster: Optional[Callable] = None

def set_websocket_broadcaster(broadcaster: Callable):
    """Set the global WebSocket event broadcaster."""
    global _websocket_broadcaster
    _websocket_broadcaster = broadcaster

def get_websocket_broadcaster() -> Optional[Callable]:
    """Get the global WebSocket event broadcaster."""
    return _websocket_broadcaster