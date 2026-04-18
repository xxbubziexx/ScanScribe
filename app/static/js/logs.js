// Check if user is authenticated
const token = localStorage.getItem('access_token');
const username = localStorage.getItem('username');
const isAdmin = localStorage.getItem('is_admin') === 'true';

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

// State
let currentPage = 1;
let pageSize = 50;
let totalRecords = 0;
let filterDate = '';
let selectedIds = new Set();

// Initialize Flatpickr date picker
function initializeDatepicker() {
    return fetchWithAuth('/api/logs/active-dates')
        .then(r => r.json())
        .then(d => {
            const enabledDates = d.dates || [];
            
            const config = {
                enable: enabledDates,
                dateFormat: "Y-m-d",
                onChange: function(selectedDates, dateStr, instance) {
                    instance.input.value = dateStr;
                    filterDate = dateStr;
                    currentPage = 1;
                    loadLogs();
                }
            };

            flatpickr(document.getElementById('filterDate'), config);

            if (enabledDates.length > 0) {
                const filterDateInput = document.getElementById('filterDate');
                filterDateInput.value = enabledDates[enabledDates.length - 1];
                filterDate = enabledDates[enabledDates.length - 1];
            }
        })
        .catch(err => {
            console.error('Failed to initialize datepicker:', err);
        });
}

// Search logs
document.getElementById('searchBtn').addEventListener('click', () => {
    currentPage = 1;
    loadLogs();
});

// Enter key for search
document.getElementById('searchInput').addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
        currentPage = 1;
        loadLogs();
    }
});

// Clear filters
document.getElementById('clearFiltersBtn').addEventListener('click', () => {
    document.getElementById('searchInput').value = '';
    document.getElementById('filterDate').value = '';
    filterDate = '';
    currentPage = 1;
    loadLogs();
});

// Sort change
document.getElementById('sortBy').addEventListener('change', () => {
    currentPage = 1;
    loadLogs();
});

// Pagination
document.getElementById('prevPage').addEventListener('click', () => {
    if (currentPage > 1) {
        currentPage--;
        loadLogs();
    }
});

document.getElementById('nextPage').addEventListener('click', () => {
    if (currentPage * pageSize < totalRecords) {
        currentPage++;
        loadLogs();
    }
});

// Select All checkbox
document.getElementById('selectAll').addEventListener('change', (e) => {
    const checkboxes = document.querySelectorAll('.row-checkbox');
    checkboxes.forEach(cb => {
        cb.checked = e.target.checked;
        const id = parseInt(cb.dataset.id);
        if (e.target.checked) {
            selectedIds.add(id);
        } else {
            selectedIds.delete(id);
        }
    });
    updateBulkActions();
});

// Bulk download button
document.getElementById('bulkDownloadBtn').addEventListener('click', async () => {
    if (selectedIds.size === 0) return;
    await bulkDownload(Array.from(selectedIds));
});

// Bulk delete button
document.getElementById('bulkDeleteBtn').addEventListener('click', () => {
    if (selectedIds.size === 0) return;
    showConfirmDialog(
        'Delete Selected Entries',
        `Are you sure you want to delete ${selectedIds.size} selected entries? This action cannot be undone.`,
        async () => {
            await bulkDelete(Array.from(selectedIds));
        }
    );
});

// Export CSV
document.getElementById('exportBtn').addEventListener('click', async () => {
    const searchQuery = document.getElementById('searchInput').value;
    filterDate = document.getElementById('filterDate').value || '';
    
    const params = new URLSearchParams();
    if (searchQuery) params.append('search', searchQuery);
    if (filterDate) {
        params.append('date_from', filterDate);
        params.append('date_to', filterDate);
    }
    
    try {
        const response = await fetchWithAuth(`/api/logs/export?${params}`);
        const blob = await response.blob();
        
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `scanscribe_database_${new Date().toISOString().split('T')[0]}.csv`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);
    } catch (error) {
        console.error('Export failed:', error);
        alert('Failed to export. Please try again.');
    }
});

// Format date from timestamp
function formatDate(timestamp) {
    if (!timestamp) return '-';
    try {
        const date = new Date(timestamp);
        return date.toLocaleDateString('en-US', { year: 'numeric', month: '2-digit', day: '2-digit' });
    } catch {
        return '-';
    }
}

// Format time from timestamp
function formatTime(timestamp) {
    if (!timestamp) return '-';
    try {
        const date = new Date(timestamp);
        return date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true });
    } catch {
        return '-';
    }
}

// Format bytes to human readable
function formatBytes(bytes) {
    if (!bytes || bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

// Toggle row expansion
function toggleExpand(id, event) {
    // Don't toggle if clicking on interactive elements
    if (event.target.tagName === 'INPUT' || event.target.tagName === 'BUTTON' || event.target.tagName === 'A' || event.target.tagName === 'AUDIO') {
        return;
    }
    
    const mainRow = document.querySelector(`tr[data-id="${id}"]`);
    const expandRow = document.getElementById(`expand-${id}`);
    
    if (!mainRow || !expandRow) return;
    
    const isExpanded = expandRow.classList.contains('visible');
    
    // Collapse all other rows first
    document.querySelectorAll('.expand-row.visible').forEach(row => {
        row.classList.remove('visible');
    });
    document.querySelectorAll('tr.expanded').forEach(row => {
        row.classList.remove('expanded');
    });
    
    // Toggle this row
    if (!isExpanded) {
        expandRow.classList.add('visible');
        mainRow.classList.add('expanded');
        // Lazy-init waveform audio player when row is expanded
        var container = expandRow.querySelector('.sc-audio-player-container[data-src]');
        if (container && !container.hasAttribute('data-inited') && typeof window.initScanscribeAudioPlayer === 'function') {
            window.initScanscribeAudioPlayer(container, container.getAttribute('data-src'));
        }
    }
}

// Make toggleExpand globally accessible
window.toggleExpand = toggleExpand;

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

// Load logs from API
async function loadLogs() {
    const searchQuery = document.getElementById('searchInput').value;
    const sortBy = document.getElementById('sortBy').value;
    filterDate = document.getElementById('filterDate').value || '';
    
    const params = new URLSearchParams({
        page: currentPage,
        page_size: pageSize,
        sort_by: sortBy
    });
    
    if (searchQuery) params.append('search', searchQuery);
    if (filterDate) {
        params.append('date_from', filterDate);
        params.append('date_to', filterDate);
    }
    
    try {
        const response = await fetchWithAuth(`/api/logs?${params}`);
        const data = await response.json();
        
        totalRecords = data.total;
        
        const tbody = document.getElementById('logsTableBody');
        
        if (data.logs.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="11" style="padding: 2rem; text-align: center; color: var(--grey-text-muted);">
                        No entries found. ${searchQuery || filterDate ? 'Try adjusting your filters.' : 'Database is empty.'}
                    </td>
                </tr>
            `;
        } else {
            tbody.innerHTML = data.logs.map(log => {
                const hasAudio = log.audio_path && log.audio_path !== 'file not saved';
                const audioSrc = hasAudio ? `/${log.audio_path}` : '';
                const confidence = log.confidence ? (log.confidence * 100).toFixed(0) + '%' : '-';
                const fileSize = log.file_size ? formatBytes(log.file_size) : '-';
                const transcriptPreview = log.transcript ? (log.transcript.length > 50 ? log.transcript.substring(0, 50) + '...' : log.transcript) : '-';
                const escapedTranscript = (log.transcript || '').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
                
                return `
                <tr data-id="${log.id}" class="expandable" onclick="toggleExpand(${log.id}, event)">
                    <td onclick="event.stopPropagation()"><input type="checkbox" class="row-checkbox db-checkbox" data-id="${log.id}" ${selectedIds.has(log.id) ? 'checked' : ''}></td>
                    <td style="color: var(--grey-text-muted);"><span class="expand-icon">▶</span>${log.id}</td>
                    <td>${formatDate(log.timestamp)}</td>
                    <td>${formatTime(log.timestamp)}</td>
                    <td class="filename-cell" title="${log.filename}">${log.filename || '-'}</td>
                    <td>${log.talkgroup || '-'}</td>
                    <td class="transcript-cell">${transcriptPreview}</td>
                    <td>${log.duration ? log.duration.toFixed(1) + 's' : '-'}</td>
                    <td>${confidence}</td>
                    <td onclick="event.stopPropagation()">
                        ${hasAudio ? `<audio class="db-audio" controls preload="none"><source src="${audioSrc}" type="audio/mpeg"></audio>` : '<span style="color: var(--grey-text-muted); font-size: 0.7rem;">No audio</span>'}
                    </td>
                    <td style="display: flex; gap: 4px;" onclick="event.stopPropagation()">
                        ${hasAudio ? `<a href="${audioSrc}" download class="db-download-btn" title="Download audio">⬇</a>` : `<span class="db-download-btn disabled" title="No audio">⬇</span>`}
                        <button class="db-delete-btn" onclick="deleteSingle(${log.id})" title="Delete entry">🗑</button>
                    </td>
                </tr>
                <tr class="expand-row" id="expand-${log.id}">
                    <td colspan="11">
                        <div class="expand-content">
                            <div class="expand-grid">
                                <div class="expand-field">
                                    <span class="expand-label">ID</span>
                                    <span class="expand-value">${log.id}</span>
                                </div>
                                <div class="expand-field">
                                    <span class="expand-label">Filename</span>
                                    <span class="expand-value">${log.filename || '-'}</span>
                                </div>
                                <div class="expand-field">
                                    <span class="expand-label">Talkgroup</span>
                                    <span class="expand-value">${log.talkgroup || '-'}</span>
                                </div>
                                <div class="expand-field">
                                    <span class="expand-label">Date & Time</span>
                                    <span class="expand-value">${formatDate(log.timestamp)} ${formatTime(log.timestamp)}</span>
                                </div>
                                <div class="expand-field">
                                    <span class="expand-label">Duration</span>
                                    <span class="expand-value">${log.duration ? log.duration.toFixed(2) + ' seconds' : '-'}</span>
                                </div>
                                <div class="expand-field">
                                    <span class="expand-label">File Size</span>
                                    <span class="expand-value">${fileSize}</span>
                                </div>
                                <div class="expand-field">
                                    <span class="expand-label">Confidence</span>
                                    <span class="expand-value">${confidence}</span>
                                </div>
                                <div class="expand-field">
                                    <span class="expand-label">Audio Path</span>
                                    <span class="expand-value">${log.audio_path || '-'}</span>
                                </div>
                            </div>
                            <div class="expand-field" style="margin-bottom: 1rem;">
                                <span class="expand-label">Full Transcript</span>
                                <div class="expand-transcript">${escapedTranscript || '[No transcript]'}</div>
                            </div>
                            ${hasAudio ? `
                            <div class="expand-audio">
                                <span class="expand-label">Audio Playback</span>
                                <div class="sc-audio-player-container" data-src="${audioSrc}" style="margin-top: 0.5rem;"></div>
                            </div>
                            ` : ''}
                        </div>
                    </td>
                </tr>
            `}).join('');
            
            // Add event listeners for checkboxes
            document.querySelectorAll('.row-checkbox').forEach(cb => {
                cb.addEventListener('change', (e) => {
                    const id = parseInt(e.target.dataset.id);
                    if (e.target.checked) {
                        selectedIds.add(id);
                    } else {
                        selectedIds.delete(id);
                    }
                    updateBulkActions();
                    updateSelectAll();
                });
            });
        }
        
        // Update pagination
        const start = data.total > 0 ? (currentPage - 1) * pageSize + 1 : 0;
        const end = Math.min(currentPage * pageSize, data.total);
        
        document.getElementById('resultCount').textContent = `${data.total} entries`;
        document.getElementById('showingStart').textContent = start;
        document.getElementById('showingEnd').textContent = end;
        document.getElementById('totalLogs').textContent = data.total;
        document.getElementById('currentPage').textContent = `Page ${currentPage} of ${data.total_pages || 1}`;
        
        document.getElementById('prevPage').disabled = currentPage === 1;
        document.getElementById('nextPage').disabled = currentPage >= data.total_pages;
        
        // Reset select all
        document.getElementById('selectAll').checked = false;
        updateBulkActions();
        
    } catch (error) {
        console.error('Failed to load logs:', error);
        const tbody = document.getElementById('logsTableBody');
        tbody.innerHTML = `
            <tr>
                <td colspan="11" style="padding: 2rem; text-align: center; color: var(--accent-danger);">
                    Error loading database. Please try again.
                </td>
            </tr>
        `;
    }
}

// Update bulk actions visibility
function updateBulkActions() {
    const bulkActions = document.getElementById('bulkActions');
    const selectedCount = document.getElementById('selectedCount');
    
    if (selectedIds.size > 0) {
        bulkActions.classList.add('visible');
        selectedCount.textContent = selectedIds.size;
    } else {
        bulkActions.classList.remove('visible');
    }
}

// Update select all checkbox state
function updateSelectAll() {
    const checkboxes = document.querySelectorAll('.row-checkbox');
    const allChecked = checkboxes.length > 0 && Array.from(checkboxes).every(cb => cb.checked);
    document.getElementById('selectAll').checked = allChecked;
}

// Delete single entry
async function deleteSingle(id) {
    showConfirmDialog(
        'Delete Entry',
        'Are you sure you want to delete this entry? This action cannot be undone.',
        async () => {
            try {
                const response = await fetchWithAuth(`/api/logs/${id}`, {
                    method: 'DELETE'
                });
                
                if (response.ok) {
                    selectedIds.delete(id);
                    loadLogs();
                } else {
                    const data = await response.json();
                    alert(data.detail || 'Failed to delete entry');
                }
            } catch (error) {
                console.error('Delete failed:', error);
                alert('Failed to delete entry');
            }
        }
    );
}

// Bulk download as ZIP
async function bulkDownload(ids) {
    const btn = document.getElementById('bulkDownloadBtn');
    const statusEl = document.getElementById('bulkDownloadStatus');
    if (!btn || !statusEl) return;

    function setDownloading(loading) {
        btn.disabled = loading;
        if (loading) {
            statusEl.style.display = 'inline';
            statusEl.textContent = 'Downloading…';
            statusEl.classList.add('loading');
        } else {
            statusEl.style.display = 'none';
            statusEl.textContent = '';
            statusEl.classList.remove('loading');
        }
    }

    setDownloading(true);
    try {
        const response = await fetchWithAuth('/api/logs/bulk-download', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ids })
        });
        if (!response.ok) {
            const data = await response.json().catch(() => ({}));
            alert(data.detail || 'Failed to download');
            return;
        }
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `scanscribe_bulk_${new Date().toISOString().split('T')[0]}.zip`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);
    } catch (error) {
        console.error('Bulk download failed:', error);
        alert('Failed to download. Please try again.');
    } finally {
        setDownloading(false);
    }
}

// Bulk delete
async function bulkDelete(ids) {
    try {
        const response = await fetchWithAuth('/api/logs/bulk-delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ids })
        });
        
        if (response.ok) {
            const data = await response.json();
            selectedIds.clear();
            loadLogs();
            console.log(`Deleted ${data.deleted} entries`);
        } else {
            const data = await response.json();
            alert(data.detail || 'Failed to delete entries');
        }
    } catch (error) {
        console.error('Bulk delete failed:', error);
        alert('Failed to delete entries');
    }
}

// Confirmation dialog
let confirmCallback = null;

function showConfirmDialog(title, message, callback) {
    document.getElementById('confirmTitle').textContent = title;
    document.getElementById('confirmMessage').textContent = message;
    document.getElementById('confirmModal').classList.remove('hidden');
    confirmCallback = callback;
}

document.getElementById('confirmCancel').addEventListener('click', () => {
    document.getElementById('confirmModal').classList.add('hidden');
    confirmCallback = null;
});

document.getElementById('confirmOk').addEventListener('click', async () => {
    document.getElementById('confirmModal').classList.add('hidden');
    if (confirmCallback) {
        await confirmCallback();
        confirmCallback = null;
    }
});

// Close modal on backdrop click
document.getElementById('confirmModal').addEventListener('click', (e) => {
    if (e.target.id === 'confirmModal') {
        document.getElementById('confirmModal').classList.add('hidden');
        confirmCallback = null;
    }
});

// Make deleteSingle globally accessible
window.deleteSingle = deleteSingle;

// Initial load
initializeDatepicker().then(() => {
    loadLogs();
});
