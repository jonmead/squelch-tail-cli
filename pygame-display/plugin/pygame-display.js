/**
 * pygame-display — squelch-tail-cli plugin that launches and drives a
 * pygame-based display (LCD 320×480 or e-ink 250×122).
 *
 * Config via environment variables (set before launching squelch-tail-cli):
 *   SQUELCH_DISPLAY_MODE    lcd | eink          (default: lcd)
 *   SQUELCH_DISPLAY_WIDTH   pixels              (default: 320 / 250)
 *   SQUELCH_DISPLAY_HEIGHT  pixels              (default: 480 / 122)
 *   SQUELCH_DISPLAY_PYTHON  python binary path  (default: python3)
 *   SQUELCH_DISPLAY_ROTATE  0|90|180|270        (default: 0)
 *   SQUELCH_DISPLAY_EXTRA   extra args string   (default: '')
 *
 * Plugin lifecycle: init → onState* → destroy
 */

import { spawn }           from 'child_process';
import path                from 'path';
import { fileURLToPath }   from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

class PygameDisplayPlugin {
    constructor() {
        this.ctrl  = null;
        this.log   = null;
        this.proc  = null;
        this._buf  = '';
        this._opts = this._readEnv();
    }

    _readEnv() {
        const mode = process.env.SQUELCH_DISPLAY_MODE || 'lcd';
        return {
            mode,
            width:   parseInt(process.env.SQUELCH_DISPLAY_WIDTH  || (mode === 'eink' ? '250' : '480'), 10),
            height:  parseInt(process.env.SQUELCH_DISPLAY_HEIGHT || (mode === 'eink' ? '122' : '320'), 10),
            python:  process.env.SQUELCH_DISPLAY_PYTHON || 'python3',
            rotate:  process.env.SQUELCH_DISPLAY_ROTATE || '0',
            extra:   (process.env.SQUELCH_DISPLAY_EXTRA || '').split(' ').filter(Boolean),
        };
    }

    // ── Plugin lifecycle ──────────────────────────────────────────────────────

    init(config, controller, logger) {
        this.ctrl = controller;
        this.log  = logger?.child?.({ label: 'pygame-display' }) ?? console;
        this._launch();
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

    // ── Internal ──────────────────────────────────────────────────────────────

    _launch() {
        const o    = this._opts;
        const main = path.resolve(__dirname, '..', 'main.py');
        const args = [
            main,
            '--mode',   o.mode,
            '--width',  String(o.width),
            '--height', String(o.height),
            '--rotate', o.rotate,
            ...o.extra,
        ];

        this.log.info?.(`Launching display: ${o.python} ${args.join(' ')}`);

        this.proc = spawn(o.python, args, {
            stdio: ['pipe', 'pipe', 'inherit'],
            env:   { ...process.env },
        });

        this.proc.on('error', (err) => {
            this.log.error?.(`Display process error: ${err.message}`);
            this.proc = null;
        });

        this.proc.on('exit', (code) => {
            this.log.info?.(`Display process exited (code ${code})`);
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

        // Send initial state once connected
        if (this.ctrl) this._sendState();
    }

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
            case 'holdTg': {
                const call = c.currentCall;
                if (call) c.setHoldTg(call.talkgroupId);
                break;
            }
            case 'holdSys': {
                const call = c.currentCall;
                if (call) c.setHoldSys(call.systemId);
                break;
            }
            case 'avoidTg': {
                const call = c.currentCall;
                if (call) c.avoidTg(call);
                break;
            }
        }
    }

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
                tgLabel:     call.tgLabel     || null,
                tgName:      call.tgName      || null,
                tgGroup:     call.tgGroup     || null,
                tgGroupTag:  call.tgGroupTag  || null,
                freq:        call.freq        || null,
                emergency:   call.emergency   || false,
                encrypted:   call.encrypted   || false,
                startTime:   call.startTime   || null,
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
