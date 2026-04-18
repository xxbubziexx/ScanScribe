/**
 * Events page: Events + Debug tab; Monitors tab (comma-separated talkgroups + today’s log list).
 */
const token = () => localStorage.getItem('access_token');
const username = localStorage.getItem('username');

if (!token()) {
    window.location.href = '/login';
}

async function api(path, options = {}) {
    const res = await fetch(path, {
        ...options,
        headers: { Authorization: `Bearer ${token()}`, ...options.headers },
    });
    if (!res.ok) throw new Error(res.statusText);
    return options.json !== false ? res.json() : res;
}

function escapeHtml(s) {
    if (s == null) return '';
    const div = document.createElement('div');
    div.textContent = s;
    return div.innerHTML;
}

function renderClosedEvents(list, monitorById) {
    const tbody = document.getElementById('closedEventsBody');
    if (!tbody) return;
    tbody.innerHTML = list.length === 0
        ? '<tr><td colspan="11" class="events-table-empty">No closed incidents</td></tr>'
        : list.map(e => `
            <tr>
                <td><a href="/events/${escapeHtml(e.event_id)}" class="events-id-link"><code>${escapeHtml(e.event_id)}</code></a></td>
                <td>${monitorById[e.monitor_id] ? escapeHtml(monitorById[e.monitor_id].name) : e.monitor_id}</td>
                <td>${escapeHtml(e.broadcast_type ? `${e.event_type || '—'} (${e.broadcast_type})` : (e.event_type || '—'))}</td>
                <td>${escapeHtml(e.location || '—')}</td>
                <td>${escapeHtml(e.units || '—')}</td>
                <td>${e.spans_attached ?? 0}</td>
                <td>${escapeHtml(e.talkgroup || '—')}</td>
                <td>${e.incident_at ? new Date(e.incident_at).toLocaleString() : '—'}</td>
                <td>${e.created_at ? new Date(e.created_at).toLocaleString() : '—'}</td>
                <td>${e.closed_at ? new Date(e.closed_at).toLocaleString() : '—'}</td>
                <td class="events-actions">
                    <button type="button" class="events-btn events-btn--reopen event-reopen-btn" data-event-id="${escapeHtml(e.event_id)}">Reopen</button>
                    <button type="button" class="events-btn events-btn--danger event-delete-btn" data-event-id="${escapeHtml(e.event_id)}">Delete</button>
                </td>
            </tr>
        `).join('');
}

function renderRecentlyClosed(list, monitorById) {
    const tbody = document.getElementById('recentlyClosedBody');
    if (!tbody) return;
    tbody.innerHTML = list.length === 0
        ? '<tr><td colspan="6" class="events-table-empty">No recently closed incidents</td></tr>'
        : list.map(e => `
            <tr>
                <td><a href="/events/${escapeHtml(e.event_id)}" class="events-id-link"><code>${escapeHtml(e.event_id)}</code></a></td>
                <td>${monitorById[e.monitor_id] ? escapeHtml(monitorById[e.monitor_id].name) : e.monitor_id}</td>
                <td>${escapeHtml(e.broadcast_type ? `${e.event_type || '—'} (${e.broadcast_type})` : (e.event_type || '—'))}</td>
                <td>${escapeHtml(e.location || '—')}</td>
                <td>${e.closed_at ? new Date(e.closed_at).toLocaleString() : '—'}</td>
                <td class="events-actions"><button type="button" class="events-btn events-btn--reopen event-reopen-btn" data-event-id="${escapeHtml(e.event_id)}">Reopen</button></td>
            </tr>
        `).join('');
}

function renderEvents(list, monitorById) {
    const tbody = document.getElementById('eventsBody');
    tbody.innerHTML = list.length === 0
        ? '<tr><td colspan="12" class="events-table-empty">No open incidents</td></tr>'
        : list.map(e => `
            <tr>
                <td><a href="/events/${escapeHtml(e.event_id)}" class="events-id-link"><code>${escapeHtml(e.event_id)}</code></a></td>
                <td>${monitorById[e.monitor_id] ? escapeHtml(monitorById[e.monitor_id].name) : e.monitor_id}</td>
                <td>${e.status === 'open' ? '<span class="events-status events-status--open">Open</span>' : escapeHtml(e.status)}</td>
                <td>${escapeHtml(e.broadcast_type ? `${e.event_type || '—'} (${e.broadcast_type})` : (e.event_type || '—'))}</td>
                <td>${escapeHtml(e.location || '—')}</td>
                <td>${escapeHtml(e.units || '—')}</td>
                <td>${e.spans_attached ?? 0}</td>
                <td>${escapeHtml(e.talkgroup || '—')}</td>
                <td>${e.incident_at ? new Date(e.incident_at).toLocaleString() : '—'}</td>
                <td>${e.created_at ? new Date(e.created_at).toLocaleString() : '—'}</td>
                <td>${e.close_recommendation && e.status === 'open' ? '<span class="events-pill-warn" title="Summary suggests closing">Close?</span>' : '—'}</td>
                <td class="events-actions">
                    ${e.status === 'open' ? `<button type="button" class="events-btn events-btn--close event-close-btn" data-event-id="${escapeHtml(e.event_id)}">Close</button>` : ''}
                    <button type="button" class="events-btn events-btn--danger event-delete-btn" data-event-id="${escapeHtml(e.event_id)}">Delete</button>
                </td>
            </tr>
        `).join('');
}

let monitorsList = [];

function renderMonitors(list) {
    monitorsList = list || [];
    const tbody = document.getElementById('monitorsBody');
    if (!tbody) return;
    tbody.innerHTML = list.length === 0
        ? '<tr><td colspan="6" class="text-gray-400">No monitors</td></tr>'
        : list.map(m => `
            <tr>
                <td>${m.id}</td>
                <td>${escapeHtml(m.name)}</td>
                <td>${m.enabled ? 'Yes' : 'No'}</td>
                <td>${(m.talkgroup_ids || []).join(', ') || '—'}</td>
                <td>${(m.start_event_labels || []).join(', ') || '—'}</td>
                <td>
                    <button type="button" class="monitor-edit-btn px-2 py-1 rounded bg-gray-600 hover:bg-gray-700 text-xs" data-id="${m.id}">Edit</button>
                    <button type="button" class="monitor-delete-btn px-2 py-1 rounded bg-red-900/50 hover:bg-red-800/60 text-red-300 text-xs ml-1" data-id="${m.id}">Delete</button>
                </td>
            </tr>
        `).join('');
    tbody.querySelectorAll('.monitor-edit-btn').forEach(btn => {
        btn.addEventListener('click', () => openEditMonitor(parseInt(btn.dataset.id, 10)));
    });
    tbody.querySelectorAll('.monitor-delete-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            deleteMonitor(parseInt(btn.dataset.id, 10));
        });
    });
}

function openEditMonitor(id) {
    const m = monitorsList.find(x => x.id === id);
    if (!m) return;
    const formTitle = document.getElementById('monitorFormTitle');
    if (formTitle) formTitle.textContent = 'Edit monitor';
    document.getElementById('monitorName').value = m.name || '';
    const tgEl = document.getElementById('monitorTalkgroups');
    if (tgEl) tgEl.value = (m.talkgroup_ids || []).join(', ');
    document.querySelectorAll('input[name="start_label"]').forEach(cb => {
        cb.checked = (m.start_event_labels || []).includes(cb.value);
    });
    document.getElementById('editingMonitorId').value = String(id);
    const enabledWrap = document.getElementById('monitorEnabledWrap');
    const enabledCb = document.getElementById('monitorEnabled');
    if (enabledWrap && enabledCb) {
        enabledWrap.classList.remove('hidden');
        enabledCb.checked = !!m.enabled;
    }
    document.getElementById('addMonitorBtn').textContent = 'Save';
    const cancelBtn = document.getElementById('cancelEditBtn');
    if (cancelBtn) cancelBtn.classList.remove('hidden');
}

async function deleteMonitor(id) {
    const m = monitorsList.find(x => x.id === id);
    if (!m || !confirm(`Delete monitor "${m.name}"? This will also delete all its events.`)) return;
    try {
        await api('/api/events/monitors/' + id, { method: 'DELETE', json: false });
        clearMonitorForm();
        loadMonitors();
        loadAll();
    } catch (e) {
        console.error(e);
        alert('Failed to delete monitor');
    }
}

function clearMonitorForm() {
    const formTitle = document.getElementById('monitorFormTitle');
    if (formTitle) formTitle.textContent = 'Add monitor';
    document.getElementById('monitorName').value = '';
    document.getElementById('editingMonitorId').value = '';
    const tgClear = document.getElementById('monitorTalkgroups');
    if (tgClear) tgClear.value = '';
    document.querySelectorAll('input[name="start_label"]').forEach(c => {
        c.checked = c.value === 'EVT_TYPE';
    });
    const enabledWrap = document.getElementById('monitorEnabledWrap');
    const enabledCb = document.getElementById('monitorEnabled');
    if (enabledWrap) enabledWrap.classList.add('hidden');
    if (enabledCb) enabledCb.checked = true;
    document.getElementById('addMonitorBtn').textContent = 'Add monitor';
    const cancelBtn = document.getElementById('cancelEditBtn');
    if (cancelBtn) cancelBtn.classList.add('hidden');
}

function formatDebugTime(ts) {
    if (!ts) return '—';
    const d = new Date(ts * 1000);
    return d.toLocaleTimeString();
}

function renderDebug(list) {
    const tbody = document.getElementById('debugBody');
    if (!tbody) return;
    const monitorById = Object.fromEntries((monitorsList || []).map((m) => [m.id, m]));
    if (list.length === 0) {
        tbody.innerHTML = '<tr><td colspan="9" class="text-gray-400">No debug entries yet</td></tr>';
        return;
    }
    tbody.innerHTML = list.map((row, idx) => {
        const action = String(row.action || '').toLowerCase();
        const isWorker = action.startsWith('worker_');
        const isMaster = action.startsWith('master_');
        const llmModel = String(row.llm_model || row.role || '').trim();
        const errTrim = (row.error || '').trim();
        const reasonLabel =
            row.action && String(row.action).startsWith('llm_') ? 'LLM reason' : 'Note / error';
        const reasonHtml = escapeHtml(errTrim);
        const reasonBlock = errTrim
            ? `
                <div class="debug-detail-block">
                    <div class="debug-detail-label">${reasonLabel}</div>
                    <pre class="debug-detail-pre">${reasonHtml}</pre>
                </div>
            `
            : '';
        const hasNerDetail = ((row.transcript || row.entities || row.raw_output || errTrim).trim().length > 0);
        const hasLlmDetail = ((row.llm_output || '').trim().length > 0);
        const hasDetail = hasNerDetail || hasLlmDetail;
        const outputHtml = escapeHtml((row.llm_output || '').trim() || '(none)');
        const rawOutputHtml = escapeHtml((row.raw_output || '').trim() || '[]');
        const transcriptHtml = escapeHtml((row.transcript || '').trim() || '(none)');
        const entitiesHtml = escapeHtml((row.entities || '').trim() || '(none)');
        const roleClass = isWorker ? 'role-worker' : (isMaster ? 'role-master' : 'role-ner');
        // Always show span context + NER; Worker/Master rows also include LLM blocks (previously LLM-only hid NER).
        const nerBlock = `
                ${reasonBlock}
                <div class="debug-detail-block">
                    <div class="debug-detail-label">Original transcription</div>
                    <pre class="debug-detail-pre">${transcriptHtml}</pre>
                </div>
                <div class="debug-detail-block">
                    <div class="debug-detail-label">NER (parsed entities)</div>
                    <pre class="debug-detail-pre">${entitiesHtml}</pre>
                </div>
                <div class="debug-detail-block">
                    <div class="debug-detail-label">Raw NER (token-level)</div>
                    <pre class="debug-detail-pre">${rawOutputHtml}</pre>
                </div>`;
        const llmBlock = hasLlmDetail
            ? `
                <div class="debug-detail-block">
                    <div class="debug-detail-label">LLM output</div>
                    <pre class="debug-detail-pre">${outputHtml}</pre>
                </div>`
            : '';
        const expandContent = nerBlock + llmBlock;
        return `
            <tr class="debug-row" data-debug-idx="${idx}">
                <td><button type="button" class="debug-toggle" aria-label="Toggle">${hasDetail ? '▶' : '—'}</button> ${formatDebugTime(row.ts)}</td>
                <td><span class="${roleClass}">${escapeHtml(llmModel || '—')}</span></td>
                <td>${row.monitor_id != null ? escapeHtml((monitorById[row.monitor_id]?.name || String(row.monitor_id))) : '—'}</td>
                <td>${row.log_entry_id != null ? row.log_entry_id : '—'}</td>
                <td>${escapeHtml(row.action || '')}</td>
                <td><code>${escapeHtml(row.event_id || '')}</code></td>
                <td>${row.duration_ms != null ? row.duration_ms : '—'}</td>
                <td>${isMaster && row.closed ? 'Yes' : '—'}</td>
                <td class="error" title="${escapeHtml(row.error || '')}">${escapeHtml((row.error || '').slice(0, 40))}</td>
            </tr>
            <tr class="debug-expand-row" data-debug-idx="${idx}">
                <td colspan="9">${expandContent}</td>
            </tr>
        `;
    }).join('');
}

function initDebugToggle() {
    document.getElementById('debugBody')?.addEventListener('click', (e) => {
        const tr = e.target.closest('tr.debug-row');
        if (!tr) return;
        const btn = tr.querySelector('.debug-toggle');
        const next = tr?.nextElementSibling;
        if (!next || !next.classList.contains('debug-expand-row')) return;
        if (btn?.textContent === '—') return;
        next.classList.toggle('visible');
        if (btn) btn.textContent = next.classList.contains('visible') ? '▼' : '▶';
    });
}

async function loadMonitors() {
    const list = await api('/api/events/monitors');
    renderMonitors(list);
    return list;
}

async function loadEvents() {
    const data = await api('/api/events/events?status=open&limit=200');
    return data.items || [];
}

let closedPage = 1;

function getClosedPageSize() {
    const sel = document.getElementById('closedEventsLimit');
    if (!sel) return 20;
    const n = parseInt(sel.value, 10);
    return [20, 50, 100].includes(n) ? n : 20;
}

function renderClosedPagination(total, page, pageSize) {
    const pager = document.getElementById('closedEventsPager');
    if (!pager) return;
    const totalPages = Math.max(1, Math.ceil(total / pageSize));
    const start = total === 0 ? 0 : (page - 1) * pageSize + 1;
    const end = Math.min(page * pageSize, total);
    pager.innerHTML = `
        <div class="events-pager">
            <button class="events-pager-btn" id="closedPrevBtn" ${page <= 1 ? 'disabled' : ''}>&#8592; Prev</button>
            <span class="events-pager-info">Page ${page} of ${totalPages} &nbsp;<span class="events-pager-count">${start}–${end} of ${total}</span></span>
            <button class="events-pager-btn" id="closedNextBtn" ${page >= totalPages ? 'disabled' : ''}>Next &#8594;</button>
        </div>
    `;
    document.getElementById('closedPrevBtn')?.addEventListener('click', () => {
        if (closedPage > 1) { closedPage--; loadClosedPane(); }
    });
    document.getElementById('closedNextBtn')?.addEventListener('click', () => {
        if (closedPage < totalPages) { closedPage++; loadClosedPane(); }
    });
}

async function loadClosedEvents() {
    const pageSize = getClosedPageSize();
    const offset = (closedPage - 1) * pageSize;
    return api(`/api/events/events?status=closed&limit=${pageSize}&offset=${offset}`);
}

function getDebugLimit() {
    const sel = document.getElementById('debugLimit');
    if (!sel) return 20;
    const n = parseInt(sel.value, 10);
    return [10, 20, 50, 100].includes(n) ? n : 20;
}

async function loadDebug() {
    const data = await api(`/api/events/debug?limit=${getDebugLimit()}`);
    const list = Array.isArray(data) ? data : [];
    renderDebug(list);
}

async function clearDebugLogs() {
    if (!confirm('Clear all Debug (NER) logs? This cannot be undone.')) return;
    try {
        await api('/api/events/debug', { method: 'DELETE', json: false });
        await loadDebug();
    } catch (e) {
        console.error(e);
        alert('Failed to clear debug logs');
    }
}

async function loadLlmStatus() {
    const el = document.getElementById('llmStatus');
    if (!el) return;
    try {
        const data = await api('/api/events/llm-status');
        el.className = 'llm-status ' + (data.status || '');
        const dot = '<span class="status-dot"></span>';
        if (data.status === 'disabled') {
            el.innerHTML = dot + ' NER: disabled';
        } else if (data.status === 'ok') {
            el.innerHTML = dot + ' NER model loaded';
        } else {
            el.innerHTML = dot + ' NER not loaded' + (data.message ? ': ' + escapeHtml(data.message) : '');
        }
    } catch (_) {
        el.className = 'llm-status';
        el.innerHTML = '<span class="status-dot"></span> NER: —';
    }
}

function parseMonitorTalkgroups(raw) {
    const seen = new Set();
    const out = [];
    for (const part of String(raw || '').split(',')) {
        const t = part.trim();
        if (!t || seen.has(t)) continue;
        seen.add(t);
        out.push(t);
    }
    return out;
}

function getMonitorTalkgroups() {
    const el = document.getElementById('monitorTalkgroups');
    return parseMonitorTalkgroups(el ? el.value : '');
}

async function loadTalkgroupsTodayList() {
    const container = document.getElementById('talkgroupsTodayList');
    const loading = document.getElementById('talkgroupsLoading');
    if (!container) return;
    try {
        const data = await api('/api/logs/talkgroups?today=true');
        const list = data.talkgroups || [];
        if (loading) loading.remove();
        if (list.length === 0) {
            container.innerHTML = '<ul class="events-tg-today-list events-tg-today-list--empty"><li>No talkgroups in today\'s logs yet.</li></ul>';
            return;
        }
        container.innerHTML = `<ul class="events-tg-today-list">${list.map(tg => `<li>${escapeHtml(tg)}</li>`).join('')}</ul>`;
    } catch (e) {
        if (loading) loading.textContent = 'Failed to load today’s talkgroups';
        console.error(e);
    }
}

function getSelectedStartLabels() {
    return Array.from(document.querySelectorAll('input[name="start_label"]:checked')).map(el => el.value);
}

async function loadStartEventLabels() {
    const container = document.getElementById('startEventLabelsContainer');
    const loading = document.getElementById('startLabelsLoading');
    if (!container) return;
    try {
        const data = await api('/api/events/ner-labels');
        const list = data.labels || [];
        if (loading) loading.remove();
        if (list.length === 0) {
            container.innerHTML = '<span class="text-gray-400">No labels</span>';
            return;
        }
        container.innerHTML = list.map(lbl => `
            <label><input type="checkbox" name="start_label" value="${escapeHtml(lbl)}" ${lbl === 'EVT_TYPE' ? 'checked' : ''} /> ${escapeHtml(lbl)}</label>
        `).join('');
    } catch (e) {
        if (loading) loading.textContent = 'Failed to load labels';
        console.error(e);
    }
}

async function loadAll() {
    try {
        const [monitors, events, recentClosedData] = await Promise.all([
            loadMonitors(),
            loadEvents(),
            api('/api/events/events?status=closed&limit=5'),
        ]);
        const monitorById = Object.fromEntries((monitors || []).map((m) => [m.id, m]));
        renderEvents(events || [], monitorById);
        renderRecentlyClosed((recentClosedData.items || []), monitorById);
        await Promise.all([loadDebug(), loadLlmStatus()]);
        return monitors || [];
    } catch (err) {
        console.error('Events load failed:', err);
        const tbody = document.getElementById('eventsBody');
        if (tbody) tbody.innerHTML = '<tr><td colspan="12" class="events-table-empty" style="color:#f87171">Failed to load events. Check console.</td></tr>';
        return [];
    }
}

async function loadClosedPane(monitors = null) {
    try {
        const monitorList = monitors || await loadMonitors();
        const data = await loadClosedEvents();
        const items = data.items || [];
        const total = data.total || 0;
        const monitorById = Object.fromEntries((monitorList || []).map((m) => [m.id, m]));
        renderClosedEvents(items, monitorById);
        renderClosedPagination(total, closedPage, getClosedPageSize());
    } catch (err) {
        console.error('Closed events load failed:', err);
        const tbody = document.getElementById('closedEventsBody');
        if (tbody) tbody.innerHTML = '<tr><td colspan="11" class="text-red-400">Failed to load. Check console.</td></tr>';
    }
}

function initTabs() {
    let talkgroupsLoaded = false;
    document.getElementById('closedEventsLimit')?.addEventListener('change', () => {
        closedPage = 1;
        if (document.getElementById('paneClosed')?.classList.contains('active')) {
            loadClosedPane();
        }
    });
    document.getElementById('debugLimit')?.addEventListener('change', () => loadDebug());
    document.querySelectorAll('.events-tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const tab = btn.dataset.tab;
            document.querySelectorAll('.events-tab-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.events-tab-pane').forEach(p => p.classList.remove('active'));
            btn.classList.add('active');
            const paneMap = { events: 'paneEvents', closed: 'paneClosed', monitors: 'paneMonitors' };
            const pane = document.getElementById(paneMap[tab] || 'paneEvents');
            if (pane) pane.classList.add('active');
            if (tab === 'closed') {
                loadClosedPane();
            }
            if (tab === 'monitors') {
                if (!talkgroupsLoaded) {
                    talkgroupsLoaded = true;
                    loadTalkgroupsTodayList();
                    loadStartEventLabels();
                }
                loadMonitors();
            }
        });
    });
}

document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('currentUser').textContent = username || 'User';
    document.getElementById('eventsRefreshBtn')?.addEventListener('click', async () => {
        const monitors = await loadAll();
        const closedPane = document.getElementById('paneClosed');
        if (closedPane?.classList.contains('active')) {
            await loadClosedPane(monitors);
        }
        if (document.getElementById('paneMonitors')?.classList.contains('active')) {
            await loadTalkgroupsTodayList();
            renderMonitors(monitors || []);
        }
    });
    document.getElementById('logoutBtn')?.addEventListener('click', () => {
        localStorage.removeItem('access_token');
        localStorage.removeItem('username');
        window.location.href = '/login';
    });
    document.getElementById('clearDebugLogsBtn')?.addEventListener('click', clearDebugLogs);
    initTabs();
    initDebugToggle();
    loadAll();

    function onEventsTableClick(e) {
        const reopenBtn = e.target.closest('.event-reopen-btn');
        if (reopenBtn) {
            const eventId = reopenBtn.dataset.eventId;
            if (!eventId) return;
            (async () => {
                try {
                    await api('/api/events/events/' + encodeURIComponent(eventId) + '/reopen', {
                        method: 'POST',
                        json: false,
                    });
                    loadAll();
                    loadClosedPane();
                } catch (err) {
                    console.error(err);
                    alert('Failed to reopen event');
                }
            })();
            return;
        }
        const closeBtn = e.target.closest('.event-close-btn');
        if (closeBtn) {
            const eventId = closeBtn.dataset.eventId;
            if (!eventId || !confirm('Close this incident? New transcripts will no longer attach to it.')) return;
            (async () => {
                try {
                    await api('/api/events/events/' + encodeURIComponent(eventId) + '/close', {
                        method: 'POST',
                        json: false,
                    });
                    loadAll();
                    loadClosedPane();
                } catch (err) {
                    console.error(err);
                    alert('Failed to close event');
                }
            })();
            return;
        }
        const btn = e.target.closest('.event-delete-btn');
        if (!btn) return;
        const eventId = btn.dataset.eventId;
        if (!eventId || !confirm('Delete this event? This cannot be undone.')) return;
        (async () => {
            try {
                await api('/api/events/events/' + encodeURIComponent(eventId), { method: 'DELETE', json: false });
                loadAll();
                loadClosedPane();
            } catch (err) {
                console.error(err);
                alert('Failed to delete event');
            }
        })();
    }
    document.getElementById('eventsBody')?.addEventListener('click', onEventsTableClick);
    document.getElementById('closedEventsBody')?.addEventListener('click', onEventsTableClick);
    document.getElementById('recentlyClosedBody')?.addEventListener('click', onEventsTableClick);

    document.getElementById('addMonitorBtn')?.addEventListener('click', async () => {
        const name = document.getElementById('monitorName').value.trim();
        const talkgroup_ids = getMonitorTalkgroups();
        const start_event_labels = getSelectedStartLabels();
        const editingId = document.getElementById('editingMonitorId')?.value?.trim();
        if (!name) {
            alert('Enter a monitor name.');
            return;
        }
        if (start_event_labels.length === 0) {
            alert('Select at least one Start event by label.');
            return;
        }
        try {
            if (editingId) {
                const body = { name, talkgroup_ids, start_event_labels };
                const enabledCb = document.getElementById('monitorEnabled');
                if (enabledCb) body.enabled = enabledCb.checked;
                await api('/api/events/monitors/' + editingId, {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body),
                });
            } else {
                await api('/api/events/monitors', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name, talkgroup_ids, start_event_labels }),
                });
            }
            clearMonitorForm();
            loadMonitors();
            loadAll();
        } catch (e) {
            console.error(e);
            alert(editingId ? 'Failed to update monitor' : 'Failed to add monitor');
        }
    });

    document.getElementById('cancelEditBtn')?.addEventListener('click', () => clearMonitorForm());

});
