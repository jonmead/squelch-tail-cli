/**
 * pygame-display — optional plugin that launches and drives the
 * squelch-tail-display pygame application.
 *
 * The display application is expected at PYGAME_DISPLAY_HOME, which
 * defaults to the sibling directory ./pygame-display relative to
 * wherever squelch-tail-cli lives.
 *
 * Enable in config.json:
 *   "plugins": [{ "path": "./src/plugins/pygame-display.js", "enabled": true }]
 *
 * Configure via environment variables:
 *   PYGAME_DISPLAY_HOME    path to pygame-display (default: ./pygame-display)
 *   SQUELCH_DISPLAY_MODE    lcd | eink                   (default: lcd)
 *   SQUELCH_DISPLAY_WIDTH   pixels                       (default: 480 / 250)
 *   SQUELCH_DISPLAY_HEIGHT  pixels                       (default: 320 / 122)
 *   SQUELCH_DISPLAY_PYTHON  python binary                (default: python3)
 *   SQUELCH_DISPLAY_ROTATE  0|90|180|270                 (default: 0)
 *   SQUELCH_DISPLAY_TEST    1  → open a desktop window instead of Pi framebuffer
 *   SQUELCH_DISPLAY_EXTRA   extra args appended to main.py invocation
 */

import { spawn, spawnSync } from 'child_process';
import { existsSync }       from 'fs';
import path              from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// Default: two levels up from src/plugins/ → squelch-tail-cli root, then
// one level up to the workspace root, then into squelch-tail-display.
const _CLI_ROOT     = path.resolve(__dirname, '..', '..');
const _DISPLAY_HOME = path.resolve(_CLI_ROOT, 'pygame-display');

class PygameDisplayPlugin {
    constructor() {
        this.ctrl  = null;
        this.log   = null;
        this.proc  = null;
        this._buf  = '';
        this._opts = this._readEnv();
    }

    _readEnv() {
        const home = process.env.PYGAME_DISPLAY_HOME || _DISPLAY_HOME;
        const mode = process.env.SQUELCH_DISPLAY_MODE || 'lcd';
        const test = process.env.SQUELCH_DISPLAY_TEST === '1';
        const venvPython = path.join(home, '.venv-pygame-display', 'bin', 'python3');
        return {
            home,
            mode,
            test,
            width:   parseInt(process.env.SQUELCH_DISPLAY_WIDTH  || (mode === 'eink' ? '250' : '480'), 10),
            height:  parseInt(process.env.SQUELCH_DISPLAY_HEIGHT || (mode === 'eink' ? '122' : '320'), 10),
            python:  process.env.SQUELCH_DISPLAY_PYTHON || (existsSync(venvPython) ? venvPython : 'python3'),
            rotate:  process.env.SQUELCH_DISPLAY_ROTATE || '0',
            extra:   (process.env.SQUELCH_DISPLAY_EXTRA || '').split(' ').filter(Boolean),
        };
    }

    // ── Plugin lifecycle ──────────────────────────────────────────────────────

    init(config, controller, logger) {
        this.ctrl = controller;
        this.log  = logger?.child?.({ label: 'pygame-display' }) ?? console;
        this._launch();
        if (config?.testData) {
            this._startTestLoop(config.callSecs ?? 3, config.standbySecs ?? 3);
        }
    }

    onState(controller) {
        this.ctrl = controller;
        this._sendState();
    }

    destroy() {
        if (!this.proc) return;
        try { this.proc.stdin.write(JSON.stringify({ type: 'quit' }) + '\n'); } catch (_) {}
        setTimeout(() => { try { this.proc?.kill('SIGTERM'); } catch (_) {} }, 600);
        this.proc = null;
    }

    // ── Launch ────────────────────────────────────────────────────────────────

    _launch() {
        const o          = this._opts;
        const mainPy     = path.join(o.home, 'main.py');
        const ensureVenv = path.join(o.home, 'ensure-venv.sh');

        if (!existsSync(mainPy)) {
            this.log.error?.(`pygame-display: main.py not found at ${mainPy}`);
            this.log.error?.(`Set PYGAME_DISPLAY_HOME to the pygame-display directory.`);
            return;
        }

        if (existsSync(ensureVenv)) {
            this.log.info?.('pygame-display: setting up venv…');
            const r = spawnSync('bash', [ensureVenv], { stdio: 'inherit' });
            if (r.status !== null && r.status !== 0) {
                this.log.error?.(`pygame-display: ensure-venv.sh failed (exit ${r.status})`);
                return;
            }
            // Re-resolve python now that venv is guaranteed to exist
            const venvPython = path.join(o.home, '.venv-pygame-display', 'bin', 'python3');
            if (!process.env.SQUELCH_DISPLAY_PYTHON && existsSync(venvPython)) {
                o.python = venvPython;
            }
        }

        const args = [
            mainPy,
            '--mode',   o.mode,
            '--width',  String(o.width),
            '--height', String(o.height),
            '--rotate', o.rotate,
            ...(o.test ? ['--test'] : []),
            ...o.extra,
        ];

        this.log.info?.(`pygame-display: ${o.python} ${args.join(' ')}`);

        this.proc = spawn(o.python, args, {
            stdio: ['pipe', 'pipe', 'inherit'],
            env:   { ...process.env },
        });

        this.proc.on('error', (err) => {
            this.log.error?.(`pygame-display process error: ${err.message}`);
            this.proc = null;
        });

        this.proc.on('exit', (code, signal) => {
            this.log.info?.(`pygame-display exited (code=${code} signal=${signal})`);
            this.proc = null;
        });

        this.proc.stdout.setEncoding('utf8');
        this.proc.stdout.on('data', (chunk) => {
            this._buf += chunk;
            const lines = this._buf.split('\n');
            this._buf = lines.pop();
            for (const line of lines) {
                if (line.trim()) this._handleCommand(line.trim());
            }
        });

        if (this.ctrl) this._sendState();
    }

    // ── Commands from display → controller ───────────────────────────────────

    _handleCommand(line) {
        let cmd;
        try { cmd = JSON.parse(line); } catch (_) { return; }
        const c = this.ctrl;
        if (!c) return;

        switch (cmd.type) {
            case 'skip':    c.skipCall();                          break;
            case 'pause':   c.togglePause();                       break;
            case 'volume':  c.setVolume(Number(cmd.value) || 0);  break;
            case 'quit':    c.quit();                              break;
            case 'holdTg':  { const call = c.currentCall; if (call) c.setHoldTg(call.talkgroupId);  break; }
            case 'holdSys': { const call = c.currentCall; if (call) c.setHoldSys(call.systemId);     break; }
            case 'avoidTg': { const call = c.currentCall; if (call) c.avoidTg(call);                 break; }
        }
    }

    // ── Test-data loop ────────────────────────────────────────────────────────

    _startTestLoop(callSecs, standbySecs) {
        const TEST_CALL = {
            systemId:    1,
            systemLabel: 'system-name',
            talkgroupId: 1001,
            tgLabel:     'Talkgroup Name',
            tgName:      null, tgGroup: null, tgGroupTag: null,
            freq:        123287500,
            emergency:   false, encrypted: false, startTime: null,
            units: [
                { unitId: -1,    tag: 'Dispatch', emergency: false },
                { unitId: 12334, tag: null,        emergency: false },
            ],
        };

        let _call = null, _playing = false, _volume = 100, _paused = false;

        const mockCtrl = {
            get connected()   { return true; },
            get mode()        { return 'live'; },
            get playing()     { return _playing; },
            get paused()      { return _paused; },
            get elapsed()     { return 0; },
            get queue()       { return []; },
            get volume()      { return _volume; },
            get lfActive()    { return true; },
            get holdSys()     { return null; },
            get holdTg()      { return null; },
            get avoidList()   { return []; },
            get currentCall() { return _call; },
            skipCall()        { },
            togglePause()     { _paused = !_paused; },
            setVolume(v)      { _volume = v; },
            setHoldTg()       { },
            setHoldSys()      { },
            avoidTg()         { },
            quit()            { process.exit(0); },
        };

        this.ctrl = mockCtrl;

        const showCall = () => {
            _call = TEST_CALL; _playing = true;
            this._sendState();
            setTimeout(showStandby, callSecs * 1000);
        };

        const showStandby = () => {
            _call = null; _playing = false;
            this._sendState();
            setTimeout(showCall, standbySecs * 1000);
        };

        // Delay first call until Python process has had time to initialise
        setTimeout(showCall, 3000);
    }

    // ── State → display ───────────────────────────────────────────────────────

    _sendState() {
        if (!this.proc) return;
        const c    = this.ctrl;
        const call = c.currentCall;

        const msg = {
            type:       'state',
            connected:  c.connected,
            mode:       c.mode,
            playing:    c.playing,
            paused:     c.paused,
            elapsed:    c.elapsed,
            queueLen:   c.queue.length,
            volume:     c.volume,
            lfActive:   c.lfActive,
            holdSys:    c.holdSys,
            holdTg:     c.holdTg,
            avoidCount: c.avoidList.filter(a => a.until > Date.now()).length,
            call: call ? {
                systemId:    call.systemId,
                systemLabel: call.systemLabel || `System ${call.systemId}`,
                talkgroupId: call.talkgroupId,
                tgLabel:     call.tgLabel    || null,
                tgName:      call.tgName     || null,
                tgGroup:     call.tgGroup    || null,
                tgGroupTag:  call.tgGroupTag || null,
                freq:        call.freq       || null,
                emergency:   call.emergency  || false,
                encrypted:   call.encrypted  || false,
                startTime:   call.startTime  || null,
                units: (call.units || []).slice(0, 12).map(u => ({
                    unitId:    u.unitId,
                    tag:       u.tag       || null,
                    emergency: u.emergency || false,
                })),
            } : null,
        };

        try {
            this.proc.stdin.write(JSON.stringify(msg) + '\n');
        } catch (_) {}
    }
}

export default PygameDisplayPlugin;
