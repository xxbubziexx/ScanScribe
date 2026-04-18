"""Custom logging handlers for ScanScribe."""
import logging
import logging.handlers
import asyncio
from typing import Optional

from .services.websocket import websocket_manager


class WebSocketHandler(logging.Handler):
    """Logging handler that broadcasts log messages to WebSocket clients."""
    
    _main_loop: Optional[asyncio.AbstractEventLoop] = None
    
    def __init__(self, level=logging.NOTSET):
        super().__init__(level)
        self.loop: Optional[asyncio.AbstractEventLoop] = None
    
    @classmethod
    def set_main_loop(cls, loop: asyncio.AbstractEventLoop):
        """Store reference to main event loop for thread-safe logging."""
        cls._main_loop = loop
        
    def emit(self, record: logging.LogRecord):
        """Send log record to WebSocket clients."""
        try:
            # Format the message
            msg = self.format(record)
            
            # Map logging levels to our level names
            level_map = {
                logging.DEBUG: "info",
                logging.INFO: "info",
                logging.WARNING: "warning",
                logging.ERROR: "error",
                logging.CRITICAL: "error"
            }
            level = level_map.get(record.levelno, "info")
            
            # Try to get the running loop
            try:
                loop = asyncio.get_running_loop()
                # If we're in the event loop, schedule the task
                asyncio.create_task(
                    websocket_manager.send_log(msg, level=level)
                )
            except RuntimeError:
                # No running loop (called from thread), use main loop with threadsafe call
                if self._main_loop and not self._main_loop.is_closed():
                    asyncio.run_coroutine_threadsafe(
                        websocket_manager.send_log(msg, level=level),
                        self._main_loop
                    )
            
        except Exception:
            self.handleError(record)


class ColoredConsoleHandler(logging.StreamHandler):
    """Console handler with emoji preservation for Docker logs."""
    
    # ANSI color codes
    COLORS = {
        'DEBUG': '\033[36m',    # Cyan
        'INFO': '\033[32m',     # Green
        'WARNING': '\033[33m',  # Yellow
        'ERROR': '\033[31m',    # Red
        'CRITICAL': '\033[35m', # Magenta
        'RESET': '\033[0m'
    }
    
    def emit(self, record):
        """Emit colored log message to console."""
        try:
            msg = self.format(record)
            stream = self.stream
            
            # Add color based on level
            color = self.COLORS.get(record.levelname, self.COLORS['RESET'])
            stream.write(f"{color}{msg}{self.COLORS['RESET']}\n")
            self.flush()
            
        except Exception:
            self.handleError(record)


def setup_logging(app_name: str = "scanscribe", level: str = "INFO"):
    """
    Configure application logging with multiple handlers.
    
    Args:
        app_name: Name of the application logger
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))
    
    # Clear existing handlers
    root_logger.handlers.clear()
    
    # Create formatters
    detailed_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    simple_formatter = logging.Formatter(
        '%(levelname)s: %(message)s'
    )
    
    # Console handler (colored, for Docker logs)
    console_handler = ColoredConsoleHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(simple_formatter)
    root_logger.addHandler(console_handler)
    
    # WebSocket handler (for dashboard)
    ws_handler = WebSocketHandler()
    ws_handler.setLevel(logging.INFO)
    ws_handler.setFormatter(simple_formatter)
    root_logger.addHandler(ws_handler)
    
    # File handler (detailed logs)
    try:
        from pathlib import Path
        from .config import get_settings
        
        settings = get_settings()
        log_file = settings.log_dir / "scanscribe.log"
        
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(detailed_formatter)
        root_logger.addHandler(file_handler)
        
    except Exception as e:
        root_logger.warning(f"Could not setup file logging: {e}")
    
    # Set specific logger levels
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)
    logging.getLogger("fastapi").setLevel(logging.INFO)
    
    root_logger.info(f"✅ Logging configured: level={level}")
