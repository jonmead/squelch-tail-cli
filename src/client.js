import WebSocket from 'ws';
import logger from './logger.js';

const log = logger.child({ label: 'ws' });

/**
 * SquelchClient — WebSocket client for the Squelch Tail server.
 *
 * Messages are plain JSON objects: { type, ...payload }
 * Server sends: hello, config, call, calls, units, error
 * Client sends: subscribe, unsubscribe, search, fetch, units
 */
class SquelchClient {
    constructor(url) {
        this.url    = url;
        this.ws     = null;
        this.alive  = false;
        this._h     = {};      // event handlers  { event: [fn, ...] }
        this._retry = null;
    }

    connect() {
        if (this.ws) { try { this.ws.terminate(); } catch (_) {} }
        log.debug(`Connecting to ${this.url}`);
        this.ws = new WebSocket(this.url);
        this.ws.on('open',    ()    => { this.alive = true;  this._emit('open'); });
        this.ws.on('close',   ()    => { this.alive = false; this._emit('close'); this._reconnect(); });
        this.ws.on('error',   (e)   => { log.debug(`WebSocket error: ${e.message}`); this._emit('error', e); });
        this.ws.on('message', (raw) => {
            try {
                const msg = JSON.parse(raw.toString());
                if (msg && typeof msg.type === 'string') {
                    this._emit('msg', msg);
                    this._emit(msg.type, msg);
                }
            } catch (_) {}
        });
    }

    _send(obj) {
        if (!this.alive) return;
        try { this.ws.send(JSON.stringify(obj)); } catch (_) {}
    }

    subscribe(filter)   { this._send(filter ? { type: 'subscribe', filter } : { type: 'subscribe' }); }
    unsubscribe()       { this._send({ type: 'unsubscribe' }); }
    search(opts)        { this._send({ type: 'search', ...opts }); }
    fetch(id)           { this._send({ type: 'fetch', id }); }
    listUnits(opts)     { this._send({ type: 'units', ...opts }); }

    on(ev, fn)          { (this._h[ev] = this._h[ev] || []).push(fn); return this; }
    _emit(ev, ...a)     { (this._h[ev] || []).forEach(fn => { try { fn(...a); } catch (_) {} }); }

    _reconnect() {
        if (this._retry) return;
        log.debug('Reconnecting in 2s…');
        this._retry = setTimeout(() => { this._retry = null; this.connect(); }, 2000);
    }

    disconnect() {
        if (this._retry) { clearTimeout(this._retry); this._retry = null; }
        try { this.ws?.terminate(); } catch (_) {}
    }
}

export { SquelchClient };
