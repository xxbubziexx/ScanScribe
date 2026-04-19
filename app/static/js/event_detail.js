/**
 * Event detail page: header + linked transcripts with playback.
 */
const token = () => localStorage.getItem('access_token');
const username = localStorage.getItem('username');

if (!token()) {
    window.location.href = '/login';
}

function getEventIdFromPath() {
    const parts = window.location.pathname.split('/').filter(Boolean);
    return parts[parts.length - 1] || '';
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

const BROADCAST_SLUG_LABELS = {
    storm_warning: 'STORM WARNING',
    cni_drivers: 'CNI DRIVER',
    road_debris: 'ROAD DEBRIS',
    attempt_to_locate: 'ATTEMPT TO LOCATE',
};

function broadcastCategoryLabel(slug) {
    if (!slug) return '';
    const s = String(slug).trim().toLowerCase();
    if (BROADCAST_SLUG_LABELS[s]) return BROADCAST_SLUG_LABELS[s];
    return s.split('_').filter(Boolean).map((w) => w.toUpperCase()).join(' ');
}

function audioUrl(audioPath) {
    if (!audioPath || audioPath === 'file not saved') return null;
    const name = audioPath.split('/').pop() || audioPath;
    return '/audio_storage/' + encodeURIComponent(name);
}

function renderHeader(ev) {
    const hero = document.getElementById('eventHeaderHero');
    const statusOpen = (ev.status || '').toLowerCase() === 'open';
    const statusClass = statusOpen ? 'ed-status ed-status--open' : 'ed-status ed-status--closed';
    const recommendBanner =
        ev.close_recommendation && statusOpen
            ? '<div class="ed-recommend-banner">Summary recommends closing this incident.</div>'
            : '';
    const typeLine = (() => {
        const b = ev.broadcast_type && String(ev.broadcast_type).trim();
        if (b) {
            return 'BROADCAST: ' + broadcastCategoryLabel(b);
        }
        const t = ev.event_type && String(ev.event_type).trim();
        if (t && t.toUpperCase() === 'BROADCAST') {
            return 'BROADCAST';
        }
        return t ? t : '—';
    })();
    if (hero) {
        hero.innerHTML = `
            ${recommendBanner}
            <div class="ed-hero-row">
                <code class="ed-hero-id">${escapeHtml(ev.event_id || '')}</code>
                <span class="${statusClass}">${escapeHtml(ev.status || '—')}</span>
            </div>
            <div class="ed-hero-sub"><span class="ed-hero-sub-muted">Type</span> ${escapeHtml(typeLine)}</div>
        `;
    }

    const multiline = (label, value) => {
        const v = value != null && String(value).trim() !== '' ? String(value) : '';
        const cls = v ? 'ed-header-value ed-header-value--multiline' : 'ed-header-value';
        return `<dt class="ed-header-label">${escapeHtml(label)}</dt><dd class="${cls}">${v ? escapeHtml(v) : '—'}</dd>`;
    };

    const line = (label, value) => {
        const v = value != null && String(value).trim() !== '' ? String(value) : '';
        return `<dt class="ed-header-label">${escapeHtml(label)}</dt><dd class="ed-header-value">${v ? escapeHtml(v) : '—'}</dd>`;
    };

    const commaBubbleField = (label, raw) => {
        const s = raw != null ? String(raw).trim() : '';
        const parts = s ? s.split(',').map(p => p.trim()).filter(Boolean) : [];
        const inner =
            parts.length === 0
                ? '<span class="ed-chip-bubbles-muted">—</span>'
                : `<div class="ed-chip-bubbles" role="list">${parts.map(p => `<span class="ed-chip-bubble" role="listitem">${escapeHtml(p)}</span>`).join('')}</div>`;
        return `<dt class="ed-header-label">${escapeHtml(label)}</dt><dd class="ed-header-value ed-header-value--chips">${inner}</dd>`;
    };

    const fieldsHtml = [
        line('Monitor', ev.monitor_name),
        commaBubbleField('Locations Mentioned', ev.location),
        commaBubbleField('Units', ev.units),
        line('Status detail', ev.status_detail),
        line('Incident time (log)', ev.incident_at ? new Date(ev.incident_at).toLocaleString() : ''),
        line('System time', ev.created_at ? new Date(ev.created_at).toLocaleString() : ''),
        line('Closed', ev.closed_at ? new Date(ev.closed_at).toLocaleString() : ''),
        multiline('Original transcription', ev.original_transcription),
        multiline('Summary', ev.summary),
    ].join('');
    document.getElementById('eventHeader').innerHTML = `<dl class="ed-header-list">${fieldsHtml}</dl>`;
}

function formatEntities(entities) {
    if (!entities || typeof entities !== 'object') return '';
    const parts = [];
    for (const [label, values] of Object.entries(entities)) {
        if (Array.isArray(values) && values.length) {
            const vals = values.map(v => escapeHtml(String(v))).join(', ');
            parts.push(`<span class="entity-tag"><strong>${escapeHtml(label)}:</strong> ${vals}</span>`);
        }
    }
    return parts.length ? `<div class="event-ner-output">${parts.join(' ')}</div>` : '';
}

function renderTranscripts(list) {
    const container = document.getElementById('eventTranscripts');
    if (!list || list.length === 0) {
        container.innerHTML = '<p class="ed-transcripts-empty">No linked transcripts.</p>';
        return;
    }
    container.innerHTML = list.map(t => {
        const timeStr = t.timestamp ? new Date(t.timestamp).toLocaleString() : '—';
        const url = audioUrl(t.audio_path);
        const audioHtml =
            t.has_playback && url
                ? `<div class="event-transcript-audio"><audio controls preload="none" src="${escapeHtml(url)}"></audio></div>`
                : '';
        const triggerBadge = t.is_trigger ? '<span class="event-transcript-trigger-badge">Trigger</span>' : '';
        const nerHtml = formatEntities(t.entities);
        const reasonRaw = (t.llm_reason || '').trim();
        const llmReasonHtml = reasonRaw
            ? `<div class="ed-llm-reason"><div class="ed-llm-reason-label">Attach reason</div><div class="ed-llm-reason-text">${escapeHtml(reasonRaw)}</div></div>`
            : `<div class="ed-llm-reason ed-llm-reason--empty"><div class="ed-llm-reason-label">Attach reason</div><div class="ed-llm-reason-muted">—</div></div>`;
        return `
            <div class="event-transcript-card">
                <div class="event-transcript-meta">${triggerBadge}${escapeHtml(timeStr)} · ${escapeHtml(t.talkgroup || '—')} · log #${t.log_entry_id}</div>
                ${llmReasonHtml}
                <div class="event-transcript-text">${escapeHtml(t.transcript || '')}</div>
                ${nerHtml}
                ${audioHtml}
            </div>
        `;
    }).join('');
}

document.addEventListener('DOMContentLoaded', async () => {
    document.getElementById('currentUser').textContent = username || 'User';
    document.getElementById('logoutBtn')?.addEventListener('click', () => {
        localStorage.removeItem('access_token');
        localStorage.removeItem('username');
        window.location.href = '/login';
    });

    const eventId = getEventIdFromPath();
    const loading = document.getElementById('eventLoading');
    const errorEl = document.getElementById('eventError');
    const content = document.getElementById('eventContent');

    if (!eventId) {
        loading.classList.add('hidden');
        errorEl.textContent = 'Invalid event ID';
        errorEl.classList.remove('hidden');
        return;
    }

    try {
        const data = await api('/api/events/events/' + encodeURIComponent(eventId));
        loading.classList.add('hidden');
        content.classList.remove('hidden');
        document.title = `ScanScribe · ${data.event?.event_id || eventId}`;
        renderHeader(data.event);
        renderTranscripts(data.transcripts || []);

        const closeBtn = document.getElementById('eventCloseBtn');
        if (closeBtn && data.event.status === 'open') {
            closeBtn.classList.remove('hidden');
            closeBtn.addEventListener('click', async () => {
                if (!confirm('Close this incident? New transcripts will no longer attach to it.')) return;
                try {
                    await api('/api/events/events/' + encodeURIComponent(eventId) + '/close', { method: 'POST', json: false });
                    window.location.reload();
                } catch (err) {
                    alert('Failed to close event');
                }
            });
        }

        document.getElementById('eventDeleteBtn').addEventListener('click', async () => {
            if (!confirm('Delete this event? This cannot be undone.')) return;
            try {
                await api('/api/events/events/' + encodeURIComponent(eventId), { method: 'DELETE', json: false });
                window.location.href = '/events';
            } catch (err) {
                alert('Failed to delete event');
            }
        });
    } catch (e) {
        loading.classList.add('hidden');
        errorEl.textContent = e.message || 'Failed to load event';
        errorEl.classList.remove('hidden');
    }
});
