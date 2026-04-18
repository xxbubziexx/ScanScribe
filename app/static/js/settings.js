// Check if user is authenticated
const token = localStorage.getItem('access_token');
const username = localStorage.getItem('username');

if (!token) {
    window.location.href = '/login';
}

// Display current user
document.getElementById('currentUser').textContent = username || 'User';

// Logout handler
document.getElementById('logoutBtn').addEventListener('click', () => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('username');
    window.location.href = '/login';
});

// Fetch with auth
async function fetchWithAuth(url, options = {}) {
    const headers = {
        ...options.headers,
        'Authorization': `Bearer ${token}`
    };
    
    const response = await fetch(url, { ...options, headers });
    
    if (response.status === 401) {
        localStorage.removeItem('access_token');
        localStorage.removeItem('username');
        window.location.href = '/login';
    }
    
    return response;
}

// Show status message
function showStatus(message, type = 'success') {
    const statusEl = document.getElementById('statusMessage');
    statusEl.textContent = message;
    statusEl.style.display = 'block';
    
    if (type === 'success') {
        statusEl.style.background = 'rgba(16, 185, 129, 0.1)';
        statusEl.style.border = '1px solid rgba(16, 185, 129, 0.3)';
        statusEl.style.color = 'rgb(16, 185, 129)';
    } else if (type === 'error') {
        statusEl.style.background = 'rgba(239, 68, 68, 0.1)';
        statusEl.style.border = '1px solid rgba(239, 68, 68, 0.3)';
        statusEl.style.color = 'rgb(239, 68, 68)';
    } else if (type === 'warning') {
        statusEl.style.background = 'rgba(245, 158, 11, 0.1)';
        statusEl.style.border = '1px solid rgba(245, 158, 11, 0.3)';
        statusEl.style.color = 'rgb(245, 158, 11)';
    }
    
    setTimeout(() => {
        statusEl.style.display = 'none';
    }, 5000);
}

// Load config.yml content
async function loadConfig() {
    try {
        const response = await fetchWithAuth('/api/settings/config');
        const data = await response.json();
        
        // Wait for Monaco Editor to be ready
        const waitForEditor = setInterval(() => {
            if (window.editorReady && window.setEditorContent) {
                clearInterval(waitForEditor);
                window.setEditorContent(data.content);
                console.log('Config loaded into Monaco Editor');
            }
        }, 100);
        
        // Timeout after 10 seconds
        setTimeout(() => {
            clearInterval(waitForEditor);
            if (!window.editorReady) {
                console.error('Monaco Editor failed to initialize');
                showStatus('Editor failed to load', 'error');
            }
        }, 10000);
        
    } catch (error) {
        console.error('Failed to load config:', error);
        showStatus('Failed to load config.yml', 'error');
    }
}

// Save config
document.getElementById('saveBtn').addEventListener('click', async () => {
    const content = window.getEditorContent();
    
    if (!content) {
        showStatus('Editor not ready', 'warning');
        return;
    }
    
    try {
        const response = await fetchWithAuth('/api/settings/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            showStatus(data.message || 'Configuration saved successfully!', 'success');
            document.getElementById('restartBtn').style.display = 'inline-flex';
        } else {
            showStatus(data.detail || 'Failed to save config', 'error');
        }
        
    } catch (error) {
        console.error('Failed to save config:', error);
        showStatus('Failed to save config. Check console for details.', 'error');
    }
});

// Restart button
document.getElementById('restartBtn').addEventListener('click', async () => {
    if (!confirm('Restart ScanScribe to apply configuration changes?\n\nThe application will be unavailable for a few seconds.')) {
        return;
    }
    
    try {
        await fetchWithAuth('/api/settings/restart', { method: 'POST' });
        
        showStatus('Application is restarting...', 'warning');
        
        // Wait 3 seconds then reload
        setTimeout(() => {
            window.location.reload();
        }, 3000);
        
    } catch (error) {
        console.error('Restart initiated:', error);
        showStatus('Application is restarting...', 'warning');
        
        // Still reload after 3 seconds
        setTimeout(() => {
            window.location.reload();
        }, 3000);
    }
});

// Reload config button
document.getElementById('reloadBtn').addEventListener('click', async () => {
    if (confirm('Reload config.yml from disk? Unsaved changes will be lost.')) {
        try {
            const response = await fetchWithAuth('/api/settings/config');
            const data = await response.json();
            window.setEditorContent(data.content);
            showStatus('Config reloaded', 'success');
            document.getElementById('restartBtn').style.display = 'none';
        } catch (error) {
            console.error('Failed to reload config:', error);
            showStatus('Failed to reload config', 'error');
        }
    }
});

// Download backup button
document.getElementById('downloadBtn').addEventListener('click', () => {
    const content = window.getEditorContent();
    const blob = new Blob([content], { type: 'text/yaml' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `config-backup-${new Date().toISOString().split('T')[0]}.yml`;
    a.click();
    URL.revokeObjectURL(url);
    showStatus('Config downloaded', 'success');
});

// Audio Storage Management
async function loadStorageStats() {
    try {
        const response = await fetchWithAuth('/api/settings/audio-storage/stats');
        const data = await response.json();
        
        document.getElementById('storageTotalFiles').textContent = data.total_files.toLocaleString();
        
        // Show size in GB if > 1GB, otherwise MB
        if (data.total_size_gb >= 1) {
            document.getElementById('storageTotalSize').textContent = `${data.total_size_gb} GB`;
        } else {
            document.getElementById('storageTotalSize').textContent = `${data.total_size_mb} MB`;
        }
        
        document.getElementById('storageDirectory').textContent = '/audio_storage';
        
    } catch (error) {
        console.error('Failed to load storage stats:', error);
        document.getElementById('storageTotalFiles').textContent = 'Error';
        document.getElementById('storageTotalSize').textContent = 'Error';
    }
}

// Refresh storage stats
document.getElementById('refreshStorageBtn').addEventListener('click', async () => {
    await loadStorageStats();
    document.getElementById('storageMessage').textContent = '✅ Stats refreshed';
    setTimeout(() => {
        document.getElementById('storageMessage').textContent = '';
    }, 3000);
});

// Download all as ZIP
document.getElementById('downloadZipBtn').addEventListener('click', async () => {
    try {
        document.getElementById('downloadZipBtn').disabled = true;
        document.getElementById('downloadZipBtn').textContent = '📦 Creating ZIP...';
        
        // Create download URL with auth token as query param (for file download)
        const url = `/api/settings/audio-storage/download-zip?token=${encodeURIComponent(token)}`;
        
        // Trigger download
        const a = document.createElement('a');
        a.href = url;
        a.style.display = 'none';
        document.body.appendChild(a);
        
        // Add auth header by using fetch and blob
        const response = await fetchWithAuth('/api/settings/audio-storage/download-zip');
        
        if (response.ok) {
            const blob = await response.blob();
            const downloadUrl = window.URL.createObjectURL(blob);
            
            // Get filename from Content-Disposition header
            const disposition = response.headers.get('Content-Disposition');
            let filename = 'scanscribe_audio.zip';
            if (disposition && disposition.includes('filename=')) {
                filename = disposition.split('filename=')[1].replace(/"/g, '');
            }
            
            a.href = downloadUrl;
            a.download = filename;
            a.click();
            
            window.URL.revokeObjectURL(downloadUrl);
            document.body.removeChild(a);
            
            document.getElementById('storageMessage').textContent = '✅ ZIP download started';
            document.getElementById('storageMessage').style.color = 'var(--accent-success)';
        } else {
            const data = await response.json();
            document.getElementById('storageMessage').textContent = `❌ ${data.detail || 'Download failed'}`;
            document.getElementById('storageMessage').style.color = 'var(--accent-error)';
        }
        
    } catch (error) {
        console.error('Failed to download ZIP:', error);
        document.getElementById('storageMessage').textContent = '❌ Download failed';
        document.getElementById('storageMessage').style.color = 'var(--accent-error)';
    } finally {
        document.getElementById('downloadZipBtn').disabled = false;
        document.getElementById('downloadZipBtn').textContent = '📦 Download All as ZIP';
        
        setTimeout(() => {
            document.getElementById('storageMessage').textContent = '';
        }, 5000);
    }
});

// Purge audio storage
document.getElementById('purgeAudioBtn').addEventListener('click', async () => {
    if (!confirm('⚠️ WARNING: This will permanently delete ALL saved audio files!\n\nDatabase entries will remain but audio paths will be set to "file not saved".\n\nThis action cannot be undone. Continue?')) {
        return;
    }
    
    // Second confirmation
    if (!confirm('Are you absolutely sure? This will delete all audio files in /audio_storage.')) {
        return;
    }
    
    try {
        document.getElementById('purgeAudioBtn').disabled = true;
        document.getElementById('purgeAudioBtn').textContent = '🗑️ Purging...';
        
        const response = await fetchWithAuth('/api/settings/audio-storage/purge', {
            method: 'POST'
        });
        
        const data = await response.json();
        
        if (response.ok) {
            document.getElementById('storageMessage').textContent = `✅ Purged ${data.deleted_files} files (${data.deleted_size_mb} MB)`;
            document.getElementById('storageMessage').style.color = 'var(--accent-success)';
            await loadStorageStats();
        } else {
            document.getElementById('storageMessage').textContent = `❌ ${data.detail || 'Purge failed'}`;
            document.getElementById('storageMessage').style.color = 'var(--accent-error)';
        }
        
    } catch (error) {
        console.error('Failed to purge audio storage:', error);
        document.getElementById('storageMessage').textContent = '❌ Purge failed';
        document.getElementById('storageMessage').style.color = 'var(--accent-error)';
    } finally {
        document.getElementById('purgeAudioBtn').disabled = false;
        document.getElementById('purgeAudioBtn').textContent = '🗑️ Purge Saved Audio';
        
        setTimeout(() => {
            document.getElementById('storageMessage').textContent = '';
        }, 5000);
    }
});

// Load retention config for manual cleanup
async function loadRetentionConfig() {
    const hintEl = document.getElementById('retentionConfigHint');
    const inputEl = document.getElementById('retentionDaysInput');
    if (!hintEl || !inputEl) return;
    try {
        const response = await fetchWithAuth('/api/maintenance/retention-config');
        const data = await response.json();
        const days = data.retention_days;
        hintEl.textContent = 'Config: ' + (days === 0 ? 'keep forever (0)' : days + ' days') + (data.cleanup_hour != null ? ' • cleanup_hour: ' + data.cleanup_hour + ':00' : '');
        if (inputEl.value === '' || inputEl.placeholder) inputEl.placeholder = days;
    } catch (e) {
        hintEl.textContent = 'Config: could not load';
    }
}

// Run retention cleanup (manual)
document.getElementById('runRetentionCleanupBtn')?.addEventListener('click', async () => {
    const inputEl = document.getElementById('retentionDaysInput');
    const msgEl = document.getElementById('retentionCleanupMessage');
    if (!inputEl || !msgEl) return;
    const days = parseInt(inputEl.value, 10);
    if (Number.isNaN(days) || days < 0) {
        msgEl.textContent = 'Enter a valid number of days (0 = do not delete by age).';
        msgEl.style.color = 'var(--accent-warning)';
        return;
    }
    if (days === 0) {
        msgEl.textContent = 'Use 0 only to skip; enter a positive number to purge old data.';
        msgEl.style.color = 'var(--accent-warning)';
        return;
    }
    if (!confirm(`Delete all database entries and their audio files older than ${days} days? This cannot be undone.`)) return;
    msgEl.textContent = 'Running...';
    msgEl.style.color = 'var(--grey-text-muted)';
    try {
        const response = await fetchWithAuth('/api/maintenance/purge', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ retention_days: days })
        });
        const data = await response.json();
        msgEl.textContent = `Removed ${data.deleted_count || 0} entries and ${data.audio_files_deleted || 0} audio files (older than ${data.cutoff_date || 'cutoff'}).`;
        msgEl.style.color = 'var(--accent-success)';
    } catch (err) {
        msgEl.textContent = err.message || 'Cleanup failed';
        msgEl.style.color = 'var(--accent-danger)';
    }
    setTimeout(() => { msgEl.textContent = ''; }, 8000);
});

// Monaco Editor initialization (loader script must load first)
function initMonacoEditor() {
    const req = typeof require !== 'undefined' ? require : (typeof window !== 'undefined' && window.require);
    if (!req) {
        setTimeout(initMonacoEditor, 50);
        return;
    }
    req.config({ paths: { vs: 'https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/0.45.0/min/vs' } });
    req(['vs/editor/editor.main'], function () {
        const container = document.getElementById('editorContainer');
        if (!container) return;
        try {
            window.monacoEditor = monaco.editor.create(container, {
                value: '# Loading...',
                language: 'yaml',
                theme: 'vs-dark',
                fontSize: 14,
                automaticLayout: true,
                minimap: { enabled: false },
                scrollBeyondLastLine: false,
                wordWrap: 'on',
                tabSize: 2,
                insertSpaces: true
            });
            window.getEditorContent = () => window.monacoEditor ? window.monacoEditor.getValue() : '';
            window.setEditorContent = (content) => { if (window.monacoEditor) window.monacoEditor.setValue(content); };
            window.editorReady = true;
        } catch (e) {
            console.error('Monaco init failed:', e);
            showStatus('Editor failed to initialize', 'error');
        }
    }, function (err) {
        console.error('Monaco load failed:', err);
        showStatus('Editor failed to load', 'error');
    });
}
initMonacoEditor();

// Load config and storage stats on page load
loadConfig();
loadStorageStats();
loadRetentionConfig();
