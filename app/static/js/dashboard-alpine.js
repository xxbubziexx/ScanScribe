/**
 * Must load before Alpine.js. Provides wsManager and registers transcriptionCards component.
 */
window.wsManager = {
    handlers: {},
    addMessageHandler(type, callback) {
        if (!this.handlers[type]) this.handlers[type] = [];
        this.handlers[type].push(callback);
    },
    triggerHandlers(type, data) {
        if (this.handlers[type]) this.handlers[type].forEach(cb => cb(data));
    }
};

document.addEventListener('alpine:init', () => {
    Alpine.data('transcriptionCards', () => ({
        cards: [],
        maxCards: 100,
        autoScroll: true,
        async init() {
            await this.loadRecent();
            this.connectWebSocket();
        },
        async loadRecent() {
            try {
                const token = localStorage.getItem('access_token');
                const response = await fetch('/api/transcriptions/recent?limit=50', {
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                if (response.ok) {
                    const data = await response.json();
                    this.cards = data.transcriptions || [];
                }
            } catch (error) {
                console.error('Failed to load recent transcriptions:', error);
            }
        },
        connectWebSocket() {
            window.wsManager.addMessageHandler('transcription', (data) => {
                this.addCard(data.data);
            });
        },
        addCard(data) {
            if (!data || this.cards.findIndex(card => card.id === data.id) !== -1) return;
            this.cards.unshift(data);
            if (this.cards.length > this.maxCards) this.cards = this.cards.slice(0, this.maxCards);
            if (this.autoScroll) {
                const container = document.getElementById('transcriptionsList');
                if (container) {
                    this.$nextTick(() => {
                        requestAnimationFrame(() => {
                            requestAnimationFrame(() => {
                                container.scrollTo({ top: 0, behavior: 'smooth' });
                            });
                        });
                    });
                }
            }
        },
        clearAll() { this.cards = []; },
        handleScroll() {},
        formatTime(isoString) {
            const date = new Date(isoString);
            return date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true });
        },
        formatBytes(bytes) {
            if (bytes === 0) return '0 B';
            const k = 1024;
            const sizes = ['B', 'KB', 'MB', 'GB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
        },
        getConfidenceClass(confidence) {
            if (confidence >= 0.8) return 'confidence-high';
            if (confidence >= 0.5) return 'confidence-medium';
            return 'confidence-low';
        },
        truncate(text, maxLength) {
            if (!text || text.length <= maxLength) return text || '';
            return text.substring(0, maxLength) + '...';
        },
        formatTranscript(text) {
            if (!text || text.trim() === '') return '[No transcript]';
            return '"' + text + '"';
        }
    }));
});
