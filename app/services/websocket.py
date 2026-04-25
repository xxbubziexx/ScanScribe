"""WebSocket manager for real-time updates."""
import logging
from typing import Dict, Set
from fastapi import WebSocket
import json
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class WebSocketManager:
    """Manages WebSocket connections and broadcasts."""
    
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self._log_buffer: list = []  # Buffer recent logs for new connections
        self._max_buffer = 100
        
    async def connect(self, websocket: WebSocket):
        """Accept and register a new WebSocket connection."""
        await websocket.accept()
        self.active_connections.add(websocket)
        
        # Send buffered logs to new connection
        for log in self._log_buffer:
            try:
                await websocket.send_json(log)
            except Exception:
                pass
                
        logger.info(f"WebSocket connected. Total connections: {len(self.active_connections)}")
        
    def disconnect(self, websocket: WebSocket):
        """Remove a WebSocket connection."""
        self.active_connections.discard(websocket)
        logger.info(f"WebSocket disconnected. Total connections: {len(self.active_connections)}")
        
    async def broadcast(self, message: Dict):
        """Broadcast message to all connected clients."""
        # Add to buffer
        self._log_buffer.append(message)
        if len(self._log_buffer) > self._max_buffer:
            self._log_buffer.pop(0)
            
        # Send to all connections
        dead_connections = set()
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Error sending to WebSocket: {e}")
                dead_connections.add(connection)
                
        # Clean up dead connections
        for connection in dead_connections:
            self.disconnect(connection)
            
    async def send_log(
        self,
        message: str,
        level: str = "info",
        tag: str = None,
        timestamp: str = None,
    ):
        """Send a log message to all clients."""
        if timestamp is None:
            timestamp = datetime.now(timezone.utc).isoformat()
        await self.broadcast({
            "type": "log",
            "level": level,
            "message": message,
            "tag": tag,
            "timestamp": timestamp,
        })
        
    async def send_status(self, status: str, data: Dict = None):
        """Send a status update to all clients."""
        await self.broadcast({
            "type": "status",
            "status": status,
            "data": data or {},
            "timestamp": datetime.now().isoformat()
        })
        
    async def send_transcription(self, transcription_data: Dict):
        """Send a completed transcription to all clients."""
        await self.broadcast({
            "type": "transcription",
            "data": transcription_data,
            "timestamp": datetime.now().isoformat()
        })


# Global instance
websocket_manager = WebSocketManager()
