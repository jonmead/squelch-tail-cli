import { AudioPlayer, fetchBuf } from './audio.js';
import { SquelchClient }         from './client.js';
import { PluginManager }         from './plugins/loader.js';
import { Controller }            from './controller.js';
import { buildMonitorMap, isMonitored, isExcluded } from './config.js';
import log from './logger.js';

/**
 * Core — application engine for Squelch Tail CLI.
 *
 * Owns the WebSocket connection, call queue, audio playback, hold/avoid,
 * subscription filter, search, and plugin orchestration.  No UI code;
 * all UI is delegated to plugins.
 *
 * Call objects use Squelch Tail field names:
 *   systemId, talkgroupId, startTime, freq, audioType, audioUrl,
 *   units[], tgLabel, tgName, tgGroup, tgGroupTag, emergency, encrypted
 * Core adds: dateTime (Date), systemLabel, audioBuf (once fetched)
 */
class Core {
    constructor(args) {
        this.args    = args;
        this.client  = null;
        this.audio   = new AudioPlayer(args);
        this.plugins = new PluginManager();

        // ── Connection state ──────────────────────────────────────────────────
        this.connected = false;
        this.systems   = [];
        this.lfActive  = false;

        // ── Mode ('live' | 'search' | 'select') ──────────────────────────────
        this.mode = args.search ? 'search' : 'live';

        // ── Subscription filter map ───────────────────────────────────────────
        this.lfMap = {};

        // ── Queue / playback ──────────────────────────────────────────────────
        this.queue       = [];
        this.currentCall = null;
        this.playing     = false;
        this.paused      = false;
        this.elapsed     = 0;
        this.progressTmr = null;

        // ── Hold / avoid ──────────────────────────────────────────────────────
        this.holdSys   = null;
        this.holdTg    = null;
        this.avoidList = [];

        // ── Search ────────────────────────────────────────────────────────────
        this.searchResults = null;
        this.searchOpts    = {
            systemId:    args.systemId    || null,
            talkgroupId: args.talkgroupId || null,
            unitId:      null,
            before:      null,
            after:       null,
            limit:       50,
            offset:      0,
        };
        this.searchIdx       = 0;
        this._pendingFetch   = null;  // { resolve } for in-flight fetch

        // ── Auto-play ─────────────────────────────────────────────────────────
        this._autoPlaySeq    = [];
        this._autoPlayActive = false;

        // ── Category selection ────────────────────────────────────────────────
        this.catSysIdx = 0;

        // ── Input blocking (for readline prompts in UI plugins) ───────────────
        this.blocking = false;

        // ── Controller (plugin-facing API surface) ────────────────────────────
        this._controller = new Controller(this);
    }

    get controller() { return this._controller; }

    // ── Startup ───────────────────────────────────────────────────────────────
    async start() {
        process.stdout.on('error', (err) => { if (err.code !== 'EIO' && err.code !== 'EPIPE') throw err; });
        process.stderr.on('error', (err) => { if (err.code !== 'EIO' && err.code !== 'EPIPE') throw err; });

        process.on('SIGINT',  () => this.quit());
        process.on('SIGTERM', () => this.quit());

        for (const p of (this.args.plugins || [])) await this.plugins.load(p);

        this.client = new SquelchClient(this.args.url);
        this._wire();
        this.client.connect();
    }

    // ── WebSocket wiring ──────────────────────────────────────────────────────
    _wire() {
        const c = this.client;

        c.on('open', () => {
            this.connected = true;
            this.plugins.emit('onStatus', true);
            this._notify();
        });

        c.on('close', () => {
            this.connected = false;
            this.lfActive  = false;
            this.plugins.emit('onStatus', false);
            this._notify();
        });

        c.on('config', (msg) => this._onConfig(msg));

        c.on('call', (msg) => {
            if (!msg.call) return;
            const call = this._parseCall(msg.call);

            // Correlation: pending fetch for search / auto-play
            if (this._pendingFetch) {
                const { resolve } = this._pendingFetch;
                this._pendingFetch = null;
                resolve(call);
                return;
            }

            // Only queue live calls
            if (this.mode !== 'live') return;
            if (this._isAvoided(call)) return;

            this.queue.push(call);
            this._notify();
            this._processQueue();
        });

        c.on('calls', (msg) => this._onSearchResults(msg));

        c.on('error', (msg) => {
            log.warn(`Server error: ${msg.message}`);
        });
    }

    // ── Config ────────────────────────────────────────────────────────────────
    _onConfig(msg) {
        this.systems = msg.systems || [];

        log.info(`Config loaded: ${this.systems.length} system(s)`);

        this._buildLFMap();

        this.plugins.emit('onConfig', this.systems);
        this.plugins.emit('init', msg, this._controller);

        if (this.mode === 'live')   this._activateLF();
        if (this.mode === 'search') this._runSearch();

        this._notify();
    }

    // ── Call parsing ──────────────────────────────────────────────────────────
    _parseCall(p) {
        const call = { ...p, dateTime: new Date(p.startTime) };
        this._enrichCall(call);
        return call;
    }

    _enrichCall(call) {
        const sys = this.systems.find(s => s.id === call.systemId);
        if (sys) {
            call.systemData  = sys;
            call.systemLabel = sys.label;
            const tg = (sys.talkgroups || []).find(t => t.id === call.talkgroupId);
            if (tg) {
                call.talkgroupData = tg;
                call.tgLabel       = call.tgLabel || tg.label;
                call.tgName        = call.tgName  || tg.name;
            }
        }
    }

    // ── Search results ────────────────────────────────────────────────────────
    _onSearchResults(msg) {
        if (!msg) return;
        this.searchResults = {
            total:   msg.total || 0,
            results: (msg.calls || []).map(r => {
                const call = this._parseCall(r);
                return call;
            }),
        };
        this.searchIdx = 0;

        this.plugins.emit('onSearchResults', this.searchResults);

        if (this.args.autoPlay && !this._autoPlayActive) {
            this._autoPlaySeq = [...this.searchResults.results];
            this._autoPlayNext();
        }

        this._notify();
    }

    // ── Subscription filter map ───────────────────────────────────────────────
    _buildLFMap() {
        const map = {};
        const now = Date.now();
        this.avoidList = this.avoidList.filter(a => a.until > now);

        for (const sys of this.systems) {
            map[String(sys.id)] = {};
            for (const tg of (sys.talkgroups || [])) {
                let active = isMonitored(this.args.monitor, sys.id, tg.id) &&
                             !isExcluded(this.args.monitorExclude, sys.id, tg.id);
                if (this.holdSys !== null && sys.id !== this.holdSys) active = false;
                if (this.holdTg  !== null && tg.id  !== this.holdTg)  active = false;
                if (this._isAvoidedSysTg(sys.id, tg.id))              active = false;
                map[String(sys.id)][String(tg.id)] = active;
            }
        }
        this.lfMap = map;
    }

    _activateLF() {
        this._buildLFMap();
        // Filter out systems/tgs with no active talkgroups for a cleaner subscribe payload
        const hasActive = Object.values(this.lfMap).some(tgs =>
            Object.values(tgs).some(v => v)
        );
        if (hasActive) {
            this.client.subscribe({ systems: this.lfMap });
        } else {
            this.client.subscribe(null);
        }
        this.lfActive = true;
        this._notify();
    }

    _deactivateLF() {
        this.client.unsubscribe();
        this.lfActive = false;
    }

    _isAvoided(call) {
        const now = Date.now();
        return this.avoidList.some(a =>
            a.until > now &&
            a.system === call.systemId &&
            (a.talkgroup === null || a.talkgroup === call.talkgroupId)
        );
    }

    _isAvoidedSysTg(sysId, tgId) {
        const now = Date.now();
        return this.avoidList.some(a =>
            a.until > now &&
            a.system === sysId &&
            (a.talkgroup === null || a.talkgroup === tgId)
        );
    }

    // ── Queue / playback ──────────────────────────────────────────────────────
    _processQueue() {
        if (this.paused || this.playing || this.queue.length === 0) return;
        this._playCall(this.queue.shift());
    }

    _playCall(call) {
        if (!call) { this._processQueue(); return; }
        this.playing = true;
        this.elapsed = 0;
        this._startProgress();

        this._fetchAudio(call).then((buf) => {
            this.plugins.runAudioPipeline(buf, call.audioType, call, (processedBuf) => {
                // Set call state and notify display at the same moment audio begins,
                // so the screen update and audio playback are fired together.
                this.currentCall = call;
                this.plugins.emit('onCallStart', call);
                this._notify();
                this.audio.play(processedBuf, call.audioType, () => {
                    this._stopProgress();
                    this.plugins.emit('onCallEnd');
                    this.playing     = false;
                    this.currentCall = null;
                    this._notify();
                    setTimeout(() => this._processQueue(), 150);
                });
            });
        }).catch((err) => {
            log.warn(`Audio fetch failed: ${err.message}`);
            this._stopProgress();
            this.playing     = false;
            this.currentCall = null;
            this._notify();
            setTimeout(() => this._processQueue(), 150);
        });
    }

    _fetchAudio(call) {
        if (!call.audioUrl) return Promise.resolve(null);
        // audioUrl is a relative path like /audio/2024/01/15/...
        const base = this.args.url.replace(/^ws/, 'http').replace(/\/ws$/, '');
        const url  = call.audioUrl.startsWith('http') ? call.audioUrl : `${base}${call.audioUrl}`;
        return fetchBuf(url);
    }

    _startProgress() {
        this._stopProgress();
        const t0 = Date.now();
        this.progressTmr = setInterval(() => {
            this.elapsed = (Date.now() - t0) / 1000;
            this._notify();
        }, 500);
    }

    _stopProgress() {
        if (this.progressTmr) { clearInterval(this.progressTmr); this.progressTmr = null; }
    }

    _skipCall() {
        this.audio.stop();
        this._stopProgress();
        this.plugins.emit('onCallEnd');
        this.playing     = false;
        this.currentCall = null;
        this._notify();
        setTimeout(() => this._processQueue(), 100);
    }

    _togglePause() {
        this.paused = !this.paused;
        if (!this.paused) this._processQueue();
        this._notify();
    }

    // ── Mode switching ────────────────────────────────────────────────────────
    _setMode(mode) {
        log.debug(`Mode: ${mode}`);
        this.mode = mode;
        if (mode === 'live') {
            this._activateLF();
        } else {
            this._deactivateLF();
            if (mode === 'search') this._runSearch();
        }
        this._notify();
    }

    // ── Search ────────────────────────────────────────────────────────────────
    _runSearch(overrides) {
        if (overrides) Object.assign(this.searchOpts, overrides);
        const o = this.searchOpts;
        const clean = { limit: o.limit ?? 50, offset: o.offset ?? 0 };
        if (o.systemId    != null) clean.systemId    = o.systemId;
        if (o.talkgroupId != null) clean.talkgroupId = o.talkgroupId;
        if (o.unitId      != null) clean.unitId      = o.unitId;
        if (o.before      != null) clean.before      = o.before instanceof Date ? o.before.getTime() : o.before;
        if (o.after       != null) clean.after       = o.after  instanceof Date ? o.after.getTime()  : o.after;
        this.client.search(clean);
    }

    _playSearchItem(item) {
        this.client.fetch(item.id);
        this._pendingFetch = {
            resolve: (call) => {
                if (!call) return;
                this.audio.stop();
                this._stopProgress();
                this._playCall(call);
            }
        };
    }

    _autoPlayNext() {
        if (this._autoPlaySeq.length === 0) { this._autoPlayActive = false; return; }
        this._autoPlayActive = true;
        const item = this._autoPlaySeq.shift();
        this.client.fetch(item.id);
        this._pendingFetch = {
            resolve: (call) => {
                if (!call) { this._autoPlayNext(); return; }
                this._playCall(call);
                const waitEnd = setInterval(() => {
                    if (!this.playing) { clearInterval(waitEnd); this._autoPlayNext(); }
                }, 500);
            }
        };
    }

    // ── Hold / avoid ──────────────────────────────────────────────────────────
    _holdSys(sysId) {
        this.holdSys = (this.holdSys === sysId) ? null : sysId;
        this.holdTg  = null;
        log.debug(this.holdSys !== null ? `Hold system: ${sysId}` : 'System hold cleared');
        this._activateLF();
        this._notify();
    }

    _holdTg(tgId) {
        this.holdTg = (this.holdTg === tgId) ? null : tgId;
        log.debug(this.holdTg !== null ? `Hold talkgroup: ${tgId}` : 'Talkgroup hold cleared');
        this._activateLF();
        this._notify();
    }

    _avoidTg(call) {
        if (!call) return;
        const until = Date.now() + this.args.avoidMinutes * 60000;
        log.info(`Avoiding talkgroup ${call.talkgroupId} (system ${call.systemId}) for ${this.args.avoidMinutes} min`);
        this.avoidList.push({ system: call.systemId, talkgroup: call.talkgroupId, until });
        this._activateLF();
        this._skipCall();
    }

    _avoidSys(call) {
        if (!call) return;
        const until = Date.now() + this.args.avoidMinutes * 60000;
        log.info(`Avoiding system ${call.systemId} for ${this.args.avoidMinutes} min`);
        this.avoidList.push({ system: call.systemId, talkgroup: null, until });
        this._activateLF();
        this._skipCall();
    }

    // ── Category toggle ───────────────────────────────────────────────────────
    _toggleCatSys(sysIdx) {
        const sys = this.systems[sysIdx];
        if (!sys) return;
        const sysKey = String(sys.id);
        const tgs    = sys.talkgroups || [];
        const cur    = this.lfMap[sysKey] || {};
        const allOn  = tgs.every(tg => cur[String(tg.id)]);
        for (const tg of tgs) cur[String(tg.id)] = !allOn;
        this.lfMap[sysKey] = cur;
        this.client.subscribe({ systems: this.lfMap });
        this._notify();
    }

    // ── State notification ────────────────────────────────────────────────────
    _notify() {
        this.plugins.emit('onState', this._controller);
    }

    // ── Lifecycle ─────────────────────────────────────────────────────────────
    quit() {
        this.audio.stop();
        this._stopProgress();
        this.client?.disconnect();
        this.plugins.destroy();
        process.exit(0);
    }
}

export { Core };
