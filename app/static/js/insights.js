/**
 * ScanScribe Insights Page
 */

// State
let currentView = 'hourly';
let currentDate = new Date().toISOString().split('T')[0];
let activityChart = null;

// Search/Filter State
let searchFilters = {
    keyword: '',
    talkgroups: [],
    hour: '',
    sort: 'newest'
};
let searchDebounceTimer = null;

// Tab switching
function switchInsightsTab(tabId) {
    document.querySelectorAll('.insights-tab-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.tab === tabId);
        btn.setAttribute('aria-selected', btn.dataset.tab === tabId);
    });
    document.querySelectorAll('.insights-tab-pane').forEach(pane => {
        pane.classList.toggle('active', pane.id === 'insights-tab-' + tabId);
    });
    localStorage.setItem('insights_active_tab', tabId);
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.insights-tab-btn').forEach(btn => {
        btn.addEventListener('click', () => switchInsightsTab(btn.dataset.tab));
    });
    const savedTab = localStorage.getItem('insights_active_tab');
    if (savedTab && ['search', 'talkgroup', 'summaries', 'recent'].includes(savedTab)) {
        switchInsightsTab(savedTab);
    }

    const token = localStorage.getItem('access_token');
    const username = localStorage.getItem('username');
    if (!token) {
        window.location.href = '/login';
        return;
    }
    document.getElementById('currentUser').textContent = username || 'User';
    document.getElementById('logoutBtn').addEventListener('click', () => {
        localStorage.removeItem('access_token');
        localStorage.removeItem('username');
        window.location.href = '/login';
    });

    initDatePicker();
    initViewToggle();
    initSearchPanel();
    initSummariesPanel();
    startLiveCpmPolling();
});

// Poll live CPM every 10s
function startLiveCpmPolling() {
    const token = localStorage.getItem('access_token');
    if (!token) return;
    const poll = async () => {
        try {
            const r = await fetch('/api/insights/live-cpm?window=1', {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            if (r.ok) {
                const d = await r.json();
                updateLiveCpm(d.calls_per_minute);
            }
        } catch (_) { /* ignore */ }
    };
    poll(); // run immediately
    setInterval(poll, 10000);
}

// Date picker initialization
async function initDatePicker() {
    const token = localStorage.getItem('access_token');
    
    try {
        // Fetch active dates from API
        const response = await fetch('/api/logs/active-dates', {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        
        if (!response.ok) throw new Error('Failed to fetch active dates');
        
        const data = await response.json();
        const enabledDates = data.dates || [];
        
        // Initialize flatpickr with only active dates enabled
        flatpickr('#date-picker', {
            dateFormat: 'Y-m-d',
            defaultDate: enabledDates.length > 0 ? enabledDates[enabledDates.length - 1] : currentDate,
            enable: enabledDates,
            onChange: (selectedDates, dateStr) => {
                currentDate = dateStr;
                document.getElementById('stats-date').textContent = formatDate(dateStr);
                loadInsights();
            }
        });
        
        // Set initial date to most recent with data
        if (enabledDates.length > 0) {
            currentDate = enabledDates[enabledDates.length - 1];
        }
        
        document.getElementById('stats-date').textContent = formatDate(currentDate);
        loadInsights();
        
    } catch (error) {
        console.error('Error initializing date picker:', error);
        // Fallback - allow all dates
        flatpickr('#date-picker', {
            dateFormat: 'Y-m-d',
            defaultDate: currentDate,
            onChange: (selectedDates, dateStr) => {
                currentDate = dateStr;
                document.getElementById('stats-date').textContent = formatDate(dateStr);
                loadInsights();
            }
        });
        document.getElementById('stats-date').textContent = formatDate(currentDate);
        loadInsights();
    }
}

// View toggle buttons
function initViewToggle() {
    const buttons = {
        'view-hourly-btn': 'hourly',
        'view-daily-btn': 'daily',
        'view-weekly-btn': 'weekly'
    };
    
    Object.entries(buttons).forEach(([id, view]) => {
        document.getElementById(id).addEventListener('click', () => {
            currentView = view;
            updateViewButtons();
            loadInsights();
        });
    });
}

function updateViewButtons() {
    document.querySelectorAll('.view-toggle-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    document.getElementById(`view-${currentView}-btn`).classList.add('active');
}

// Load all insights data
async function loadInsights() {
    const token = localStorage.getItem('access_token');
    
    try {
        const response = await fetch(`/api/insights/stats?date=${currentDate}&view=${currentView}`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        
        if (!response.ok) throw new Error('Failed to load insights');
        
        const data = await response.json();
        updateStats(data.summary);
        updateChart(data.activity);
        updateTalkgroups(data.talkgroups, data.talkgroups_all);
        updateRecentActivity(data.recent);
        await refreshSummariesUI();
        
    } catch (error) {
        console.error('Error loading insights:', error);
    }
}

// Update live CPM (called by updateStats and by polling)
function updateLiveCpm(value) {
    const el = document.getElementById('stat-calls-per-min');
    if (el) el.textContent = (value != null ? value : 0).toFixed(2);
}

// Update stat cards
function updateStats(summary) {
    if (!summary) return;
    document.getElementById('stat-total').textContent = summary.total || 0;
    updateLiveCpm(summary.calls_per_minute);
    document.getElementById('stat-talkgroups').textContent = summary.unique_talkgroups || 0;
    document.getElementById('stat-avg-duration').textContent = `${(summary.avg_duration || 0).toFixed(1)}s`;
    document.getElementById('stat-peak-hour').textContent = summary.peak_hour || '--';
}

// Update activity chart
function updateChart(activityData) {
    const ctx = document.getElementById('activity-chart').getContext('2d');
    
    if (activityChart) {
        activityChart.destroy();
    }
    
    const labels = activityData.map(d => d.label);
    const values = activityData.map(d => d.count);
    
    // Create gradient fill
    const gradient = ctx.createLinearGradient(0, 0, 0, 300);
    gradient.addColorStop(0, 'rgba(59, 130, 246, 0.4)');
    gradient.addColorStop(1, 'rgba(59, 130, 246, 0.0)');
    
    activityChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'Transcriptions',
                data: values,
                fill: true,
                backgroundColor: gradient,
                borderColor: 'rgba(59, 130, 246, 1)',
                borderWidth: 2,
                tension: 0.3,
                pointBackgroundColor: 'rgba(59, 130, 246, 1)',
                pointBorderColor: '#fff',
                pointBorderWidth: 1,
                pointRadius: 4,
                pointHoverRadius: 7,
                pointHoverBackgroundColor: 'rgba(234, 179, 8, 1)',
                pointHoverBorderColor: '#fff',
                pointHoverBorderWidth: 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                intersect: false,
                mode: 'index'
            },
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    callbacks: {
                        footer: () => 'Click to filter by this hour'
                    }
                }
            },
            scales: {
                x: {
                    grid: {
                        color: 'rgba(255, 255, 255, 0.05)'
                    },
                    ticks: {
                        color: 'rgba(255, 255, 255, 0.6)'
                    }
                },
                y: {
                    beginAtZero: true,
                    grid: {
                        color: 'rgba(255, 255, 255, 0.05)'
                    },
                    ticks: {
                        color: 'rgba(255, 255, 255, 0.6)',
                        stepSize: 1
                    }
                }
            },
            onClick: (event, elements) => {
                if (elements.length > 0 && currentView === 'hourly') {
                    const index = elements[0].index;
                    const label = labels[index];
                    handleGraphClick(label);
                }
            },
            onHover: (event, elements) => {
                const canvas = event.chart.canvas;
                canvas.style.cursor = elements.length > 0 && currentView === 'hourly' ? 'pointer' : 'default';
            }
        }
    });
}

// Update talkgroup breakdown
function updateTalkgroups(talkgroups, allTalkgroups) {
    const container = document.getElementById('talkgroup-breakdown');
    
    // Update the talkgroup filter dropdown with ALL talkgroups
    updateTalkgroupFilter(allTalkgroups || talkgroups);
    
    if (!talkgroups || talkgroups.length === 0) {
        container.innerHTML = '<div class="text-gray-400 text-sm">No data for selected period</div>';
        return;
    }
    
    const maxCount = Math.max(...talkgroups.map(t => t.count));
    
    container.innerHTML = talkgroups.slice(0, 10).map(tg => `
        <div class="flex items-center gap-4 cursor-pointer talkgroup-row" data-talkgroup="${tg.talkgroup}">
            <div class="w-32 text-sm truncate" title="${tg.talkgroup}">${tg.talkgroup}</div>
            <div class="flex-1">
                <div class="talkgroup-bar" style="width: ${(tg.count / maxCount * 100)}%"></div>
            </div>
            <div class="w-16 text-right text-sm text-gray-400">${tg.count}</div>
        </div>
    `).join('');
    
    // Add click handlers to talkgroup rows (add to filter)
    container.querySelectorAll('.talkgroup-row').forEach(row => {
        row.addEventListener('click', () => {
            const talkgroup = row.dataset.talkgroup;
            addTalkgroupToFilter(talkgroup);
            executeSearch();
        });
    });
}

// Update recent activity
function updateRecentActivity(recent) {
    const container = document.getElementById('recent-activity');
    
    if (!recent || recent.length === 0) {
        container.innerHTML = '<div class="text-gray-400 text-sm">No recent activity</div>';
        return;
    }
    
    container.innerHTML = recent.map(entry => `
        <div class="flex items-center gap-3 p-2 rounded" style="background: rgba(255,255,255,0.02);">
            <div class="text-xs text-gray-500 w-20">${formatTime(entry.timestamp)}</div>
            <div class="text-xs px-2 py-1 rounded" style="background: rgba(59, 130, 246, 0.2);">${entry.talkgroup || 'N/A'}</div>
            <div class="flex-1 text-sm truncate">${truncate(entry.transcript, 80)}</div>
            <div class="text-xs text-gray-500">${entry.duration?.toFixed(1) || 0}s</div>
        </div>
    `).join('');
}

// Helpers
function formatDate(dateStr) {
    const date = new Date(dateStr + 'T00:00:00');
    return date.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' });
}

function formatTime(timestamp) {
    const date = new Date(timestamp);
    return date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
}

function truncate(text, length) {
    if (!text) return '';
    return text.length > length ? text.substring(0, length) + '...' : text;
}

// Initialize search panel
function initSearchPanel() {
    // Keyword search with debounce
    document.getElementById('search-keyword').addEventListener('input', (e) => {
        clearTimeout(searchDebounceTimer);
        searchDebounceTimer = setTimeout(() => {
            searchFilters.keyword = e.target.value;
            executeSearch();
        }, 300);
    });
    
    // Talkgroup dropdown toggle
    document.getElementById('tg-filter-trigger').addEventListener('click', (e) => {
        e.stopPropagation();
        document.getElementById('filter-talkgroup').classList.toggle('open');
    });
    document.addEventListener('click', () => {
        document.getElementById('filter-talkgroup').classList.remove('open');
    });
    document.getElementById('filter-talkgroup').addEventListener('click', (e) => e.stopPropagation());

    // Talkgroup filter (checkbox multi-select) - event delegation
    document.getElementById('filter-talkgroup').addEventListener('change', (e) => {
        if (e.target.type === 'checkbox' && e.target.name === 'tg-filter') {
            const checked = document.querySelectorAll('#filter-talkgroup input[name="tg-filter"]:checked');
            searchFilters.talkgroups = Array.from(checked).map(cb => cb.value).filter(Boolean);
            updateTgFilterTriggerLabel();
            executeSearch();
        }
    });
    
    // Hour filter
    document.getElementById('filter-hour').addEventListener('change', (e) => {
        searchFilters.hour = e.target.value;
        executeSearch();
    });
    
    // Sort option
    document.getElementById('sort-option').addEventListener('change', (e) => {
        searchFilters.sort = e.target.value;
        executeSearch();
    });
    
    // Clear filters button
    document.getElementById('clear-filters-btn').addEventListener('click', () => {
        searchFilters = { keyword: '', talkgroups: [], hour: '', sort: 'newest' };
        document.getElementById('search-keyword').value = '';
        document.querySelectorAll('#filter-talkgroup input[name="tg-filter"]').forEach(cb => cb.checked = false);
        updateTgFilterTriggerLabel();
        document.getElementById('filter-hour').value = '';
        document.getElementById('sort-option').value = 'newest';
        updateActiveFilters();
        executeSearch();
    });
    
    // Populate hour dropdown (0-23)
    const hourSelect = document.getElementById('filter-hour');
    for (let i = 0; i < 24; i++) {
        const hour12 = i === 0 ? 12 : (i > 12 ? i - 12 : i);
        const ampm = i < 12 ? 'AM' : 'PM';
        const option = document.createElement('option');
        option.value = i;
        option.textContent = `${hour12}:00 ${ampm}`;
        hourSelect.appendChild(option);
    }
}

// Execute search with current filters
async function executeSearch() {
    const token = localStorage.getItem('access_token');
    updateActiveFilters();
    
    try {
        const params = new URLSearchParams({
            date: currentDate,
            keyword: searchFilters.keyword,
            hour: searchFilters.hour,
            sort: searchFilters.sort,
            limit: searchFilters.hour ? '10000' : '100'
        });
        (searchFilters.talkgroups || []).forEach(tg => params.append('talkgroup', tg));
        
        const response = await fetch(`/api/insights/search?${params}`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        
        if (!response.ok) throw new Error('Search failed');
        
        const data = await response.json();
        updateSearchResults(data.results, data.total);
        
    } catch (error) {
        console.error('Search error:', error);
        document.getElementById('search-results').innerHTML = 
            '<div class="text-red-400 text-sm">Search failed. Please try again.</div>';
    }
}

// Audio player state
let currentAudio = null;
let currentPlayingId = null;

// Update search results display
function updateSearchResults(results, total) {
    const container = document.getElementById('search-results');
    document.getElementById('results-count').textContent = total;
    
    if (!results || results.length === 0) {
        container.innerHTML = '<div class="text-gray-400 text-sm">No results found</div>';
        return;
    }
    
    container.innerHTML = results.map(entry => {
        const hasAudio = entry.audio_path && entry.audio_path !== 'file not saved';
        const escapedPath = hasAudio ? encodeURIComponent(entry.audio_path) : '';
        
        return `
        <div class="flex items-start gap-3 p-3 rounded search-result-row" style="background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.05);">
            <button class="play-btn flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center transition-all"
                    style="background: rgba(59, 130, 246, 0.2); border: 1px solid rgba(59, 130, 246, 0.4);${!hasAudio ? ' opacity: 0.3; cursor: not-allowed;' : ''}"
                    data-id="${entry.id}"
                    data-audio="${escapedPath}"
                    ${!hasAudio ? 'disabled' : ''}>
                <span class="play-icon" id="play-icon-${entry.id}">▶</span>
            </button>
            <div class="flex flex-col gap-1 min-w-[80px]">
                <div class="text-xs text-gray-500">${formatTime(entry.timestamp)}</div>
                <div class="text-xs text-gray-600">${formatDateShort(entry.timestamp)}</div>
            </div>
            <div class="text-xs px-2 py-1 rounded min-w-[80px] text-center talkgroup-filter-chip" style="background: rgba(59, 130, 246, 0.2); cursor: pointer;" data-talkgroup="${escapeHtml(entry.talkgroup || 'N/A')}" title="Click to add as filter">
                ${entry.talkgroup || 'N/A'}
            </div>
            <div class="flex-1 text-sm search-result-transcript">${highlightKeyword(entry.transcript || '', searchFilters.keyword)}</div>
            <div class="flex flex-col gap-1 text-right min-w-[72px] items-end">
                <div class="flex flex-row gap-1 items-center justify-end">
                    <button type="button" class="copy-result-btn" title="Copy [talkgroup] &quot;transcript&quot;" data-talkgroup="${escapeHtml(entry.talkgroup || 'N/A')}" data-transcript="${escapeHtml(entry.transcript || '')}">📋</button>
                    <button type="button" class="download-result-btn"
                        title="${hasAudio ? 'Download audio file' : 'No audio saved for this log'}"
                        data-audio="${escapedPath}"
                        data-id="${entry.id}"
                        ${!hasAudio ? 'disabled' : ''}>💾</button>
                </div>
                <div class="text-xs text-gray-400">${(entry.duration || 0).toFixed(1)}s</div>
                <div class="text-xs text-gray-500">${formatBytes(entry.file_size || 0)}</div>
            </div>
        </div>
    `}).join('');
    
    // Add click handlers using event delegation
    container.querySelectorAll('.play-btn:not([disabled])').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const id = parseInt(btn.dataset.id);
            const audioPath = decodeURIComponent(btn.dataset.audio);
            toggleAudio(id, audioPath);
        });
    });

    // Copy result: [talkgroup] "transcript"
    container.querySelectorAll('.copy-result-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const tg = btn.dataset.talkgroup || 'N/A';
            const transcript = btn.dataset.transcript || '';
            const text = `[${tg}] "${transcript}"`;
            const doCopy = () => {
                const orig = btn.textContent;
                btn.textContent = '✓';
                setTimeout(() => { btn.textContent = orig; }, 800);
            };
            if (navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(text).then(doCopy).catch(() => fallbackCopy(text, doCopy));
            } else {
                fallbackCopy(text, doCopy);
            }
        });
    });

    container.querySelectorAll('.download-result-btn:not([disabled])').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const raw = btn.dataset.audio;
            if (!raw) return;
            const audioPath = decodeURIComponent(raw);
            if (!audioPath || audioPath === 'file not saved') return;
            const url = '/' + audioPath.replace(/^\/+/, '');
            const basename = audioPath.split('/').pop() || `log_${btn.dataset.id || 'audio'}`;
            const a = document.createElement('a');
            a.href = url;
            a.download = basename;
            a.rel = 'noopener';
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
        });
    });

    // Talkgroup chip click: add to filter
    container.querySelectorAll('.talkgroup-filter-chip').forEach(chip => {
        chip.addEventListener('click', (e) => {
            e.stopPropagation();
            const tg = chip.dataset.talkgroup;
            if (tg) {
                addTalkgroupToFilter(tg);
                executeSearch();
            }
        });
    });
}

// Toggle audio play/stop
function toggleAudio(id, audioPath) {
    console.log('toggleAudio called:', { id, audioPath });
    
    if (!audioPath || audioPath === 'file not saved') {
        console.log('No audio path, skipping');
        return;
    }
    
    // If clicking same audio that's playing, stop it
    if (currentPlayingId === id && currentAudio) {
        stopAudio();
        return;
    }
    
    // Stop any currently playing audio
    if (currentAudio) {
        stopAudio();
    }
    
    // Start new audio (path is already like "audio_storage/filename.mp3")
    const audioUrl = `/${audioPath}`;
    console.log('Loading audio from:', audioUrl);
    currentAudio = new Audio(audioUrl);
    currentPlayingId = id;
    
    // Update button icon
    const icon = document.getElementById(`play-icon-${id}`);
    if (icon) icon.textContent = '■';
    
    // Handle audio end
    currentAudio.onended = () => {
        stopAudio();
    };
    
    // Handle error
    currentAudio.onerror = () => {
        console.error('Failed to load audio');
        stopAudio();
    };
    
    currentAudio.play().catch(err => {
        console.error('Playback error:', err);
        stopAudio();
    });
}

// Stop current audio
function stopAudio() {
    if (currentAudio) {
        currentAudio.pause();
        currentAudio.currentTime = 0;
        currentAudio = null;
    }
    
    // Reset icon
    if (currentPlayingId) {
        const icon = document.getElementById(`play-icon-${currentPlayingId}`);
        if (icon) icon.textContent = '▶';
        currentPlayingId = null;
    }
}

// Highlight search keyword in text
function highlightKeyword(text, keyword) {
    if (!keyword || !text) return text;
    const regex = new RegExp(`(${escapeRegex(keyword)})`, 'gi');
    return text.replace(regex, '<span style="background: rgba(234, 179, 8, 0.3); padding: 0 2px; border-radius: 2px;">$1</span>');
}

function escapeRegex(str) {
    return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

// Update active filters display
function updateActiveFilters() {
    const container = document.getElementById('active-filters');
    const tagsContainer = document.getElementById('filter-tags');
    const hasFilters = searchFilters.keyword || (searchFilters.talkgroups && searchFilters.talkgroups.length > 0) || searchFilters.hour;
    
    if (!hasFilters) {
        container.style.display = 'none';
        return;
    }
    
    container.style.display = 'flex';
    let tags = [];
    
    if (searchFilters.keyword) {
        tags.push(`<span class="px-2 py-1 rounded" style="background: rgba(59,130,246,0.2);">Keyword: "${searchFilters.keyword}"</span>`);
    }
    if (searchFilters.talkgroups && searchFilters.talkgroups.length > 0) {
        tags.push(`<span class="px-2 py-1 rounded" style="background: rgba(34,197,94,0.2);">TG: ${searchFilters.talkgroups.join(', ')}</span>`);
    }
    if (searchFilters.hour !== '') {
        const hour = parseInt(searchFilters.hour);
        const hour12 = hour === 0 ? 12 : (hour > 12 ? hour - 12 : hour);
        const ampm = hour < 12 ? 'AM' : 'PM';
        tags.push(`<span class="px-2 py-1 rounded" style="background: rgba(168,85,247,0.2);">Hour: ${hour12} ${ampm}</span>`);
    }
    
    tagsContainer.innerHTML = tags.join('');
}

function updateTgFilterTriggerLabel() {
    const n = (searchFilters.talkgroups || []).length;
    const trigger = document.getElementById('tg-filter-trigger');
    if (trigger) trigger.textContent = n ? `Talkgroups (${n})` : 'Talkgroups';
}

// Add talkgroup to filter (from chip click or talkgroup row)
function addTalkgroupToFilter(talkgroup) {
    if (!talkgroup) return;
    if (!searchFilters.talkgroups) searchFilters.talkgroups = [];
    if (!searchFilters.talkgroups.includes(talkgroup)) {
        searchFilters.talkgroups.push(talkgroup);
    }
    const container = document.getElementById('filter-talkgroup');
    let cb = Array.from(container.querySelectorAll('input[name="tg-filter"]')).find(i => i.value === talkgroup);
    if (!cb) {
        const label = document.createElement('label');
        cb = document.createElement('input');
        cb.type = 'checkbox';
        cb.name = 'tg-filter';
        cb.value = talkgroup;
        cb.checked = true;
        label.appendChild(cb);
        label.appendChild(document.createTextNode(talkgroup));
        container.appendChild(label);
        const ph = container.querySelector('.tg-filter-placeholder');
        if (ph) ph.remove();
    } else {
        cb.checked = true;
    }
}

// Populate talkgroup filter from data
function updateTalkgroupFilter(talkgroups) {
    const container = document.getElementById('filter-talkgroup');
    const selected = searchFilters.talkgroups || [];
    
    container.innerHTML = '';
    
    if (talkgroups && talkgroups.length > 0) {
        [...talkgroups].sort((a, b) => (b.count || 0) - (a.count || 0)).forEach(tg => {
            const label = document.createElement('label');
            const cb = document.createElement('input');
            cb.type = 'checkbox';
            cb.name = 'tg-filter';
            cb.value = tg.talkgroup;
            cb.checked = selected.includes(tg.talkgroup);
            label.appendChild(cb);
            label.appendChild(document.createTextNode(`${tg.talkgroup} (${tg.count})`));
            container.appendChild(label);
        });
    } else {
        container.innerHTML = '<div class="tg-filter-placeholder text-gray-500 text-sm">No talkgroups</div>';
    }
    updateTgFilterTriggerLabel();
}

// Handle graph point click
function handleGraphClick(hourLabel) {
    // Parse hour from label (e.g., "12 AM" -> 0, "1 PM" -> 13)
    const match = hourLabel.match(/(\d+)\s*(AM|PM)/i);
    if (match) {
        let hour = parseInt(match[1]);
        const isPM = match[2].toUpperCase() === 'PM';
        
        if (hour === 12) {
            hour = isPM ? 12 : 0;
        } else if (isPM) {
            hour += 12;
        }
        
        searchFilters.hour = hour.toString();
        document.getElementById('filter-hour').value = hour.toString();
        executeSearch();
    }
}

// Format bytes to human readable
function formatBytes(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

function formatDateShort(timestamp) {
    const date = new Date(timestamp);
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

// ====================
// Summaries (hour-level)
// ====================
let hourSummariesByHour = new Map(); // hour(int) -> summary object

function handleCitationPlayClick(e) {
    const toggle = e.target.closest('.summary-citations-toggle');
    if (toggle) {
        const block = toggle.closest('.summary-citations');
        const body = block?.querySelector('.summary-citations-body');
        const chevron = block?.querySelector('.summary-citations-chevron');
        if (body && chevron) {
            const isHidden = body.style.display === 'none';
            body.style.display = isHidden ? 'block' : 'none';
            chevron.textContent = isHidden ? '▼' : '▶';
        }
        return;
    }
    const btn = e.target.closest('[data-audio-src]');
    if (!btn) return;
    const audio = document.getElementById('insightsCitationAudio');
    if (audio && btn.dataset.audioSrc) {
        audio.src = btn.dataset.audioSrc;
        audio.play().catch(() => {});
    }
}

function initSummariesPanel() {
    const hourSelect = document.getElementById('summaryHourSelect');
    const generateBtn = document.getElementById('summaryGenerateBtn');
    const regenerateBtn = document.getElementById('summaryRegenerateBtn');
    const deleteBtn = document.getElementById('summaryDeleteBtn');
    const summariesList = document.getElementById('summariesList');

    if (!hourSelect || !generateBtn || !regenerateBtn || !deleteBtn) {
        return;
    }
    if (summariesList) {
        summariesList.addEventListener('click', handleCitationPlayClick);
    }

    hourSelect.addEventListener('change', () => {
        updateSummariesStatus();
    });

    generateBtn.addEventListener('click', async () => {
        await generateHourSummary(false);
    });

    regenerateBtn.addEventListener('click', async () => {
        await generateHourSummary(true);
    });

    deleteBtn.addEventListener('click', async () => {
        await deleteHourSummary();
    });
}

function getSelectedSummaryHour() {
    const hourSelect = document.getElementById('summaryHourSelect');
    if (!hourSelect) return null;
    const v = hourSelect.value;
    if (v === '') return null;
    const h = parseInt(v, 10);
    return Number.isFinite(h) ? h : null;
}

function hourToLabel(hour) {
    const h = parseInt(hour, 10);
    const hour12 = h === 0 ? 12 : (h > 12 ? h - 12 : h);
    const ampm = h < 12 ? 'AM' : 'PM';
    return `${hour12}:00 ${ampm}`;
}

function setSummariesStatus(text) {
    const el = document.getElementById('summariesStatus');
    if (el) el.textContent = text;
}

function updateSummariesStatus() {
    const hour = getSelectedSummaryHour();
    if (hour === null) {
        setSummariesStatus('Select an hour to generate.');
        return;
    }
    if (hourSummariesByHour.has(hour)) {
        setSummariesStatus(`Summary exists for ${hourToLabel(hour)}.`);
    } else {
        setSummariesStatus(`No summary yet for ${hourToLabel(hour)}.`);
    }
}

async function refreshSummariesUI() {
    await Promise.all([loadSummaryHours(), loadSummaries()]);
    updateSummariesStatus();
}

async function loadSummaryHours() {
    const token = localStorage.getItem('access_token');
    const hourSelect = document.getElementById('summaryHourSelect');
    if (!hourSelect) return;

    try {
        const res = await fetch(`/api/insights/summaries/hours?date=${currentDate}`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        if (!res.ok) throw new Error('Failed to load hours');
        const data = await res.json();
        const hours = data.hours || [];

        const prev = hourSelect.value;
        hourSelect.innerHTML = '<option value="">Hours with activity...</option>';

        hours.forEach(h => {
            const option = document.createElement('option');
            option.value = String(h.hour);
            option.textContent = `${hourToLabel(h.hour)} (${h.count})`;
            hourSelect.appendChild(option);
        });

        // restore selection if still present
        if (prev && Array.from(hourSelect.options).some(o => o.value === prev)) {
            hourSelect.value = prev;
        } else {
            hourSelect.value = '';
        }
    } catch (e) {
        console.error('Failed to load summary hours:', e);
        hourSelect.innerHTML = '<option value="">Hours with activity...</option>';
    }
}

async function loadSummaries() {
    const token = localStorage.getItem('access_token');
    const listEl = document.getElementById('summariesList');
    if (!listEl) return;

    try {
        const res = await fetch(`/api/insights/summaries?date=${currentDate}`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        if (!res.ok) throw new Error('Failed to load summaries');
        const data = await res.json();
        const summaries = data.summaries || [];

        hourSummariesByHour = new Map();
        summaries.forEach(s => hourSummariesByHour.set(parseInt(s.hour, 10), s));

        if (summaries.length === 0) {
            listEl.innerHTML = '<div class="text-gray-400 text-sm">No summaries saved for this day.</div>';
            return;
        }

        const renderMarkdown = (raw) => {
            if (typeof marked === 'undefined' || !marked.parse) return escapeHtml(raw).replace(/\n/g, '<br>');
            const out = marked.parse(raw);
            return (typeof out === 'string') ? out : escapeHtml(raw).replace(/\n/g, '<br>');
        };
        listEl.innerHTML = summaries.map(s => {
            const html = renderMarkdown(s.text || '');
            const timestampLabel = s.updated_at ? 'Updated' : 'Created';
            const timestampValue = s.updated_at || s.created_at || '';
            return `
            <div class="summary-card" style="background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.06); padding: 0.75rem; border-radius: 6px; margin-bottom: 0.5rem;">
                <button type="button" class="summary-card-header flex-between" onclick="toggleSummaryCard(this)" style="width: 100%; gap: 1rem; margin-bottom: 0.25rem;">
                    <div class="text-caption" style="font-weight: 600; text-align: left;">${hourToLabel(s.hour)}</div>
                    <div class="flex items-center gap-2 text-caption" style="opacity: 0.7;">
                        <span>${timestampLabel} ${timestampValue}</span>
                        <span class="summary-toggle-icon" aria-hidden="true">▶</span>
                    </div>
                </button>
                <div class="summary-card-body summary-markdown" style="display: none;">${html}</div>
            </div>
        `;
        }).join('');
    } catch (e) {
        console.error('Failed to load summaries:', e);
        listEl.innerHTML = '<div class="text-red-400 text-sm">Failed to load summaries.</div>';
    }
}

function toggleSummaryCard(headerEl) {
    if (!headerEl) return;
    const card = headerEl.closest('.summary-card');
    if (!card) return;
    const body = card.querySelector('.summary-card-body');
    if (!body) return;
    const isOpen = body.style.display === 'block';
    body.style.display = isOpen ? 'none' : 'block';
    card.classList.toggle('open', !isOpen);
}

async function generateHourSummary(force) {
    const token = localStorage.getItem('access_token');
    const hour = getSelectedSummaryHour();
    if (hour === null) {
        setSummariesStatus('Select an hour first.');
        return;
    }

    setSummariesStatus(force ? 'Regenerating…' : 'Generating…');

    try {
        const res = await fetch('/api/insights/summaries/generate', {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ date: currentDate, hour, force: !!force })
        });

        const data = await res.json();
        if (!res.ok) {
            setSummariesStatus(data.detail || 'Failed to generate summary.');
            return;
        }

        await loadSummaries();
        setSummariesStatus(`Saved summary for ${hourToLabel(hour)}.`);
    } catch (e) {
        console.error('Generate summary failed:', e);
        setSummariesStatus('Failed to generate summary.');
    }
}

async function deleteHourSummary() {
    const token = localStorage.getItem('access_token');
    const hour = getSelectedSummaryHour();
    if (hour === null) {
        setSummariesStatus('Select an hour first.');
        return;
    }

    setSummariesStatus('Deleting…');

    try {
        const res = await fetch(`/api/insights/summaries?date=${currentDate}&hour=${hour}`, {
            method: 'DELETE',
            headers: { 'Authorization': `Bearer ${token}` }
        });

        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
            setSummariesStatus(data.detail || 'Failed to delete summary.');
            return;
        }

        await loadSummaries();
        setSummariesStatus(`Deleted summary for ${hourToLabel(hour)}.`);
    } catch (e) {
        console.error('Delete summary failed:', e);
        setSummariesStatus('Failed to delete summary.');
    }
}

function fallbackCopy(text, onSuccess) {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    try {
        if (document.execCommand('copy')) onSuccess();
    } finally {
        document.body.removeChild(ta);
    }
}

function escapeHtml(str) {
    return String(str)
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#039;');
}
