// Check if user is authenticated
const token = localStorage.getItem('access_token');
const username = localStorage.getItem('username');

if (!token) {
    window.location.href = '/login';
}

// Display current user
document.getElementById('currentUser').textContent = username || 'User';

// WebSocket connection
let ws = null;
let wsReconnectTimer = null;
let wsReconnectAttempts = 0;
const wsMaxReconnectDelay = 30000; // 30 seconds

function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/api/watcher/ws`;
    
    try {
        ws = new WebSocket(wsUrl);
        
        ws.onopen = () => {
            console.log('WebSocket connected');
            wsReconnectAttempts = 0;
            addConsoleMessage('Connected to server', 'success');
        };
        
        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                handleWebSocketMessage(data);
            } catch (error) {
                console.error('Error parsing WebSocket message:', error);
            }
        };
        
        ws.onerror = (error) => {
            console.error('WebSocket error:', error);
        };
        
        ws.onclose = () => {
            console.log('WebSocket disconnected');
            addConsoleMessage('Disconnected from server - reconnecting...', 'warning');
            scheduleReconnect();
        };
    } catch (error) {
        console.error('WebSocket connection failed:', error);
        scheduleReconnect();
    }
}

function scheduleReconnect() {
    if (wsReconnectTimer) {
        return; // Already scheduled
    }
    
    wsReconnectAttempts++;
    const delay = Math.min(1000 * Math.pow(2, wsReconnectAttempts - 1), wsMaxReconnectDelay);
    
    console.log(`Reconnecting in ${delay/1000}s (attempt ${wsReconnectAttempts})...`);
    
    wsReconnectTimer = setTimeout(() => {
        wsReconnectTimer = null;
        connectWebSocket();
    }, delay);
}

function handleWebSocketMessage(data) {
    const { type, level, message, tag, status, data: msgData, timestamp } = data;
    
    console.log('WebSocket message received:', type, data); // Debug
    
    if (type === 'log') {
        addConsoleMessage(`[${tag || 'system'}] ${message}`, level || 'info', timestamp);
    } else if (type === 'status') {
        handleStatusUpdate(status, msgData);
    } else if (type === 'transcription') {
        console.log('Transcription message detected, triggering handlers'); // Debug
        handleTranscription(msgData);
        // Trigger handlers for Alpine.js components
        window.wsManager.triggerHandlers('transcription', data);
    }
}

function handleStatusUpdate(status, data) {
    console.log('Status update:', status, data);
    
    const startBtn = document.getElementById('startBtn');
    const stopBtn = document.getElementById('stopBtn');
    
    const statusEl = document.getElementById('status');
    
    // Update dashboard status
    if (status === 'watcher_started') {
        if (statusEl) {
            statusEl.textContent = 'Status: Running';
            statusEl.style.color = '#4ade80';
            statusEl.style.fontWeight = 'bold';
        }
        document.querySelector('.status-dot').classList.remove('status-warning');
        document.querySelector('.status-dot').classList.add('status-active');
        // Grey out start button, enable stop button
        if (startBtn) startBtn.disabled = true;
        if (stopBtn) stopBtn.disabled = false;
    } else if (status === 'watcher_stopped') {
        if (statusEl) {
            statusEl.textContent = 'Status: Stopped';
            statusEl.style.color = '#f87171';
            statusEl.style.fontWeight = 'normal';
        }
        document.querySelector('.status-dot').classList.remove('status-active');
        document.querySelector('.status-dot').classList.add('status-warning');
        // Grey out stop button, enable start button
        if (startBtn) startBtn.disabled = false;
        if (stopBtn) stopBtn.disabled = true;
    } else if (status === 'watcher_paused') {
        if (statusEl) {
            statusEl.textContent = 'Status: Paused';
            statusEl.style.color = '#facc15';
            statusEl.style.fontWeight = 'normal';
        }
    } else if (status === 'watcher_resumed') {
        if (statusEl) {
            statusEl.textContent = 'Status: Running';
            statusEl.style.color = '#4ade80';
            statusEl.style.fontWeight = 'bold';
        }
    } else if (status === 'stats_update') {
        // Update live file counts
        updateStats(data);
    }
    
    // Update stats if available
    if (data) {
        updateStats(data);
    }
}

function updateStats(data) {
    if (data.ingest_count !== undefined) {
        document.getElementById('statIngest').textContent = data.ingest_count;
    }
    if (data.queue_count !== undefined) {
        document.getElementById('statQueue').textContent = data.queue_count;
    }
    if (data.files_processed !== undefined) {
        document.getElementById('statProcessed').textContent = data.files_processed;
    }
    if (data.files_rejected !== undefined) {
        document.getElementById('statRejected').textContent = data.files_rejected;
    }
    
    // Update main status and status dot based on watcher state
    if (data.is_running !== undefined) {
        const statusEl = document.getElementById('status');
        const statusDot = document.querySelector('.status-dot');
        
        if (data.is_running) {
            statusEl.textContent = 'Status: Running';
            statusDot.classList.remove('status-warning', 'status-inactive');
            statusDot.classList.add('status-active');
        } else {
            statusEl.textContent = 'Status: Stopped';
            statusDot.classList.remove('status-active');
            statusDot.classList.add('status-warning');
        }
    }
    
    // Update engine device type (CPU/GPU)
    if (data.engine_device) {
        const statEngine = document.getElementById('statEngine');
        if (statEngine) {
            statEngine.textContent = data.engine_device;
        }
    }
    
    // Update engine status
    const engineStatusEl = document.getElementById('engineStatus');
    if (data.processor_running !== undefined && engineStatusEl) {
        if (data.processor_running) {
            engineStatusEl.textContent = 'Transcription Engine: Running';
        } else {
            engineStatusEl.textContent = 'Transcription Engine: Not running';
        }
    }
    
    // Update memory bar
    if (data.memory_used_gb !== undefined && data.memory_total_gb !== undefined) {
        const memoryText = document.getElementById('memoryText');
        const memoryBar = document.getElementById('memoryBar');
        
        if (memoryText) {
            memoryText.textContent = `${data.memory_used_gb} / ${data.memory_total_gb} GB`;
        }
        
        if (memoryBar) {
            memoryBar.style.width = `${data.memory_percent}%`;
            memoryBar.classList.remove('warning', 'critical');
            if (data.memory_percent >= 90) {
                memoryBar.classList.add('critical');
            } else if (data.memory_percent >= 70) {
                memoryBar.classList.add('warning');
            }
        }
    }
    
    // Update CPU bar
    if (data.cpu_percent !== undefined) {
        const cpuText = document.getElementById('cpuText');
        const cpuBar = document.getElementById('cpuBar');
        
        if (cpuText) {
            cpuText.textContent = `${data.cpu_percent}%`;
        }
        
        if (cpuBar) {
            cpuBar.style.width = `${data.cpu_percent}%`;
            cpuBar.classList.remove('warning', 'critical');
            if (data.cpu_percent >= 90) {
                cpuBar.classList.add('critical');
            } else if (data.cpu_percent >= 70) {
                cpuBar.classList.add('warning');
            }
        }
    }
}

function handleTranscription(data) {
    console.log('Transcription received:', data);
    // Alpine.js handles this via WebSocket handler in component
}

// Logout handler
document.getElementById('logoutBtn').addEventListener('click', () => {
    // Close WebSocket
    if (ws) {
        ws.close();
    }
    if (wsReconnectTimer) {
        clearTimeout(wsReconnectTimer);
    }
    
    localStorage.removeItem('access_token');
    localStorage.removeItem('username');
    window.location.href = '/login';
});

// Clear console
document.getElementById('clearLog').addEventListener('click', () => {
    const console = document.getElementById('console');
    console.innerHTML = '<div class="console-message info">Console cleared.</div>';
});

// Clear transcriptions - Now handled by Alpine.js

// Fetch authenticated data with token
async function fetchWithAuth(url, options = {}) {
    const headers = {
        ...options.headers,
        'Authorization': `Bearer ${token}`
    };
    
    const response = await fetch(url, { ...options, headers });
    
    if (response.status === 401) {
        // Token expired or invalid
        localStorage.removeItem('access_token');
        localStorage.removeItem('username');
        window.location.href = '/login';
    }
    
    return response;
}

// Width resizer functionality (Vertical divider)
const widthResizer = document.getElementById('width-resizer');
const container = document.getElementById('resizable-container');
const leftPane = document.querySelector('.resizable-pane-left');

let isResizingWidth = false;

widthResizer.addEventListener('mousedown', (e) => {
    isResizingWidth = true;
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
});

// Height resizer functionality (Horizontal divider)
const heightResizer = document.getElementById('height-resizer');

let isResizingHeight = false;

heightResizer.addEventListener('mousedown', (e) => {
    isResizingHeight = true;
    document.body.style.cursor = 'row-resize';
    document.body.style.userSelect = 'none';
});

document.addEventListener('mousemove', (e) => {
    // Handle width resizing
    if (isResizingWidth) {
        const containerRect = container.getBoundingClientRect();
        const newWidth = e.clientX - containerRect.left;
        const containerWidth = containerRect.width;
        
        // Calculate percentage (min 20%, max 80%)
        const percentage = (newWidth / containerWidth) * 100;
        
        if (percentage > 20 && percentage < 80) {
            leftPane.style.flex = `0 0 ${percentage}%`;
        }
    }
    
    // Handle height resizing
    if (isResizingHeight) {
        const containerRect = container.parentElement.getBoundingClientRect();
        const newHeight = e.clientY - containerRect.top;
        
        if (newHeight > 300 && newHeight < window.innerHeight) {
            container.style.height = `${newHeight}px`;
        }
    }
});

document.addEventListener('mouseup', () => {
    if (isResizingWidth) {
        isResizingWidth = false;
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
    }
    if (isResizingHeight) {
        isResizingHeight = false;
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
    }
});

const consoleDiv = document.getElementById('console');

function formatConsoleTimeLabel(isoString) {
    if (!isoString) {
        return new Date().toLocaleTimeString();
    }
    const d = new Date(isoString);
    return Number.isNaN(d.getTime()) ? new Date().toLocaleTimeString() : d.toLocaleTimeString();
}

function addConsoleMessage(message, type = 'info', timeSource = null) {
    const msg = document.createElement('div');
    msg.className = `console-message ${type}`;
    msg.textContent = `[${formatConsoleTimeLabel(timeSource)}] ${message}`;
    
    consoleDiv.appendChild(msg);
    const autoScrollEl = document.getElementById('consoleAutoScroll');
    if (autoScrollEl && autoScrollEl.checked) {
        consoleDiv.scrollTop = consoleDiv.scrollHeight;
    }
}

// Control buttons
document.getElementById('startBtn').addEventListener('click', async () => {
    try {
        const response = await fetchWithAuth('/api/watcher/start', { method: 'POST' });
        const data = await response.json();
        addConsoleMessage(data.message, data.success ? 'success' : 'error');
    } catch (error) {
        addConsoleMessage('Failed to start watcher', 'error');
    }
});

document.getElementById('stopBtn').addEventListener('click', async () => {
    try {
        const response = await fetchWithAuth('/api/watcher/stop', { method: 'POST' });
        const data = await response.json();
        addConsoleMessage(data.message, data.success ? 'warning' : 'error');
    } catch (error) {
        addConsoleMessage('Failed to stop watcher', 'error');
    }
});

document.getElementById('pauseBtn').addEventListener('click', async () => {
    try {
        // Toggle pause/resume
        const statusResponse = await fetchWithAuth('/api/watcher/status');
        const statusData = await statusResponse.json();
        
        const endpoint = statusData.paused ? '/api/watcher/resume' : '/api/watcher/pause';
        const response = await fetchWithAuth(endpoint, { method: 'POST' });
        const data = await response.json();
        
        // Update button text
        document.getElementById('pauseBtn').textContent = statusData.paused ? 'Pause' : 'Resume';
        
        addConsoleMessage(data.message, data.success ? 'info' : 'error');
    } catch (error) {
        addConsoleMessage('Failed to toggle pause', 'error');
    }
});

// Initial status check
async function checkHealth() {
    try {
        const response = await fetch('/health');
        const data = await response.json();
        
        if (data.status === 'healthy') {
            const healthEl = document.getElementById('health');
            if (healthEl) {
                healthEl.textContent = 'Healthy';
                healthEl.className = 'text-green-300';
            }
            
            const warningEl = document.querySelector('.status-warning');
            if (warningEl) {
                warningEl.classList.remove('status-warning');
            }
            
            const statusDot = document.querySelector('.status-dot');
            if (statusDot) {
                statusDot.classList.add('status-active');
            }
            
            // Update model info
            if (data.model) {
                const modelEl = document.getElementById('statModel');
                if (modelEl) {
                    modelEl.textContent = data.model.split('/').pop();
                }
            }
            
            addConsoleMessage('System health check: OK', 'success');
        }
    } catch (error) {
        console.error('Health check failed:', error);
        addConsoleMessage('Health check failed', 'error');
    }
}

// Initialize watcher status
async function loadWatcherStatus() {
    try {
        const response = await fetchWithAuth('/api/watcher/status');
        const data = await response.json();
        
        handleStatusUpdate(data.running ? 'watcher_started' : 'watcher_stopped', data);
        
        // Update pause button
        if (data.paused) {
            document.getElementById('pauseBtn').textContent = 'Resume';
        }
        
        // Update stats
        updateStats(data);
    } catch (error) {
        console.error('Failed to load watcher status:', error);
    }
}

// Poll stats periodically
setInterval(async () => {
    try {
        const response = await fetchWithAuth('/api/watcher/status');
        const data = await response.json();
        console.log('Status poll:', data); // Debug log
        updateStats(data);
    } catch (error) {
        console.error('Status poll error:', error);
    }
}, 5000); // Update every 5 seconds

// Fullscreen toggle
let isFullscreen = false;
const fullscreenBtn = document.getElementById('fullscreenBtn');

if (fullscreenBtn) {
    fullscreenBtn.addEventListener('click', () => {
        isFullscreen = !isFullscreen;
        
        const mainHeader = document.getElementById('mainHeader');
        const statsGrid = document.getElementById('statsGrid');
        const controlPanel = document.getElementById('controlPanel');
        const transcriptionsPane = document.getElementById('transcriptionsPane');
        const consolePane = document.getElementById('consolePane');
        
        if (isFullscreen) {
            // Enter browser fullscreen
            if (document.documentElement.requestFullscreen) {
                document.documentElement.requestFullscreen();
            } else if (document.documentElement.webkitRequestFullscreen) {
                document.documentElement.webkitRequestFullscreen();
            } else if (document.documentElement.mozRequestFullScreen) {
                document.documentElement.mozRequestFullScreen();
            } else if (document.documentElement.msRequestFullscreen) {
                document.documentElement.msRequestFullscreen();
            }
            
            // Hide header, stats, and control panel
            mainHeader.style.display = 'none';
            statsGrid.style.display = 'none';
            controlPanel.style.display = 'none';
            
            // Add glass background to panes
            transcriptionsPane.style.background = 'rgba(255, 255, 255, 0.03)';
            transcriptionsPane.style.backdropFilter = 'blur(10px)';
            consolePane.style.background = 'rgba(255, 255, 255, 0.03)';
            consolePane.style.backdropFilter = 'blur(10px)';
            
            // Update button text
            fullscreenBtn.textContent = '✕ Exit Fullscreen';
            
            // Expand container
            document.querySelector('.container').style.padding = '0';
            document.querySelector('.resizable-container-wrapper').style.height = '100vh';
            document.querySelector('.resizable-container').style.height = '100vh';
        } else {
            // Exit browser fullscreen
            if (document.exitFullscreen) {
                document.exitFullscreen();
            } else if (document.webkitExitFullscreen) {
                document.webkitExitFullscreen();
            } else if (document.mozCancelFullScreen) {
                document.mozCancelFullScreen();
            } else if (document.msExitFullscreen) {
                document.msExitFullscreen();
            }
            
            // Show header, stats, and control panel
            mainHeader.style.display = 'flex';
            statsGrid.style.display = 'grid';
            controlPanel.style.display = 'block';
            
            // Remove glass background from panes
            transcriptionsPane.style.background = '';
            transcriptionsPane.style.backdropFilter = '';
            consolePane.style.background = '';
            consolePane.style.backdropFilter = '';
            
            // Update button text
            fullscreenBtn.textContent = '⛶ Fullscreen';
            
            // Restore container
            document.querySelector('.container').style.padding = '1rem';
            document.querySelector('.resizable-container-wrapper').style.height = '';
            document.querySelector('.resizable-container').style.height = '500px';
        }
    });
} else {
    console.error('Fullscreen button not found!');
}

// Handle ESC key or browser fullscreen exit
document.addEventListener('fullscreenchange', () => {
    if (!document.fullscreenElement && isFullscreen) {
        // User pressed ESC or exited fullscreen, manually restore UI
        isFullscreen = false;
        
        const mainHeader = document.getElementById('mainHeader');
        const statsGrid = document.getElementById('statsGrid');
        const controlPanel = document.getElementById('controlPanel');
        const transcriptionsPane = document.getElementById('transcriptionsPane');
        const consolePane = document.getElementById('consolePane');
        
        // Show header, stats, and control panel
        mainHeader.style.display = 'flex';
        statsGrid.style.display = 'grid';
        controlPanel.style.display = 'block';
        
        // Remove glass background from panes
        transcriptionsPane.style.background = '';
        transcriptionsPane.style.backdropFilter = '';
        consolePane.style.background = '';
        consolePane.style.backdropFilter = '';
        
        // Update button text
        fullscreenBtn.textContent = '⛶ Fullscreen';
        
        // Restore container
        document.querySelector('.container').style.padding = '1rem';
        document.querySelector('.resizable-container-wrapper').style.height = '';
        document.querySelector('.resizable-container').style.height = '500px';
    }
});

document.addEventListener('webkitfullscreenchange', () => {
    if (!document.webkitFullscreenElement && isFullscreen) {
        isFullscreen = false;
        
        const mainHeader = document.getElementById('mainHeader');
        const statsGrid = document.getElementById('statsGrid');
        const controlPanel = document.getElementById('controlPanel');
        const transcriptionsPane = document.getElementById('transcriptionsPane');
        const consolePane = document.getElementById('consolePane');
        
        mainHeader.style.display = 'flex';
        statsGrid.style.display = 'grid';
        controlPanel.style.display = 'block';
        transcriptionsPane.style.background = '';
        transcriptionsPane.style.backdropFilter = '';
        consolePane.style.background = '';
        consolePane.style.backdropFilter = '';
        fullscreenBtn.textContent = '⛶ Fullscreen';
        document.querySelector('.container').style.padding = '1rem';
        document.querySelector('.resizable-container-wrapper').style.height = '';
        document.querySelector('.resizable-container').style.height = '500px';
    }
});

document.addEventListener('mozfullscreenchange', () => {
    if (!document.mozFullScreenElement && isFullscreen) {
        isFullscreen = false;
        
        const mainHeader = document.getElementById('mainHeader');
        const statsGrid = document.getElementById('statsGrid');
        const controlPanel = document.getElementById('controlPanel');
        const transcriptionsPane = document.getElementById('transcriptionsPane');
        const consolePane = document.getElementById('consolePane');
        
        mainHeader.style.display = 'flex';
        statsGrid.style.display = 'grid';
        controlPanel.style.display = 'block';
        transcriptionsPane.style.background = '';
        transcriptionsPane.style.backdropFilter = '';
        consolePane.style.background = '';
        consolePane.style.backdropFilter = '';
        fullscreenBtn.textContent = '⛶ Fullscreen';
        document.querySelector('.container').style.padding = '1rem';
        document.querySelector('.resizable-container-wrapper').style.height = '';
        document.querySelector('.resizable-container').style.height = '500px';
    }
});

document.addEventListener('msfullscreenchange', () => {
    if (!document.msFullscreenElement && isFullscreen) {
        isFullscreen = false;
        
        const mainHeader = document.getElementById('mainHeader');
        const statsGrid = document.getElementById('statsGrid');
        const controlPanel = document.getElementById('controlPanel');
        const transcriptionsPane = document.getElementById('transcriptionsPane');
        const consolePane = document.getElementById('consolePane');
        
        mainHeader.style.display = 'flex';
        statsGrid.style.display = 'grid';
        controlPanel.style.display = 'block';
        transcriptionsPane.style.background = '';
        transcriptionsPane.style.backdropFilter = '';
        consolePane.style.background = '';
        consolePane.style.backdropFilter = '';
        fullscreenBtn.textContent = '⛶ Fullscreen';
        document.querySelector('.container').style.padding = '1rem';
        document.querySelector('.resizable-container-wrapper').style.height = '';
        document.querySelector('.resizable-container').style.height = '500px';
    }
});

// Initialize
checkHealth();
loadWatcherStatus();
connectWebSocket();
addConsoleMessage('Dashboard initialized', 'info');
