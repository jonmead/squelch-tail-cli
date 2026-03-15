import readline from 'readline';
import { YEL, R, CLS, HIDEC, SHOWC, goto, CLRL } from '../ansi.js';
import { TuiRenderer } from './tui-renderer.js';

/**
 * TuiPlugin — interactive terminal UI plugin for Squelch Tail.
 *
 * Receives a Controller in init() and uses it for all state reads and
 * action invocations.  Has no direct dependency on Core internals.
 */
class TuiPlugin {
    constructor() {
        this.ctrl        = null;
        this._renderer   = null;
        this._renderTmr  = null;
        this._initDone   = false;
    }

    init(config, controller /*, logger */) {
        if (this._initDone) {
            this._schedRender();
            return;
        }
        this._initDone = true;
        this.ctrl = controller;

        this._renderer = new TuiRenderer(this);

        if (process.stdout.isTTY) process.stdout.write(HIDEC);
        process.stdout.on('resize', () => this._schedRender());
        process.on('exit', () => { if (process.stdout.isTTY) process.stdout.write(SHOWC); });
        process.stdout.on('error', (err) => { if (err.code !== 'EIO' && err.code !== 'EPIPE') throw err; });

        this._setupInput();
        this._schedRender();
    }

    onState(controller) {
        this._schedRender();
    }

    onStatus(/* connected */) {
        this._schedRender();
    }

    destroy() {
        if (this._renderTmr) { clearTimeout(this._renderTmr); this._renderTmr = null; }
        if (process.stdout.isTTY) process.stdout.write(SHOWC + CLS);
    }

    get mode()          { return this.ctrl?.mode; }
    get blocking()      { return this.ctrl?.blocking; }
    get searchOpts()    { return this.ctrl?.searchOpts; }
    get searchResults() { return this.ctrl?.searchResults; }
    get searchIdx()     { return this.ctrl?.searchIdx; }
    get catSysIdx()     { return this.ctrl?.catSysIdx; }

    _schedRender() {
        if (this._renderTmr) return;
        this._renderTmr = setTimeout(() => {
            this._renderTmr = null;
            try { this._renderer?.render(); } catch (_) {}
        }, 40);
    }

    _setupInput() {
        if (!process.stdin.isTTY) return;
        process.stdin.setRawMode(true);
        process.stdin.resume();
        process.stdin.setEncoding('utf8');
        process.stdin.on('data', (k) => {
            if (this.ctrl?.blocking) return;
            if (k === '\x03') { this.ctrl.quit(); return; }
            try { this._handleKey(k); } catch (_) {}
        });
    }

    _handleKey(k) {
        if (k === '\x1b[A') return this._navUp();
        if (k === '\x1b[B') return this._navDown();
        if (k === '\x1b[C') return this._navRight();
        if (k === '\x1b[D') return this._navLeft();
        if (k === '\x1b')   return this._escKey();

        switch (this.ctrl.mode) {
            case 'live':   this._liveKey(k);   break;
            case 'search': this._searchKey(k); break;
            case 'select': this._selectKey(k); break;
        }
    }

    _liveKey(k) {
        const c = this.ctrl;
        switch (k) {
            case 'l': c.setMode('live');   break;
            case 's': c.setMode('search'); break;
            case 'c': c.setMode('select'); break;
            case ' ': c.skipCall();        break;
            case 'p': c.togglePause();     break;
            case 'h': { const call = c.currentCall; if (call) c.setHoldTg(call.talkgroupId);  break; }
            case 'H': { const call = c.currentCall; if (call) c.setHoldSys(call.systemId);    break; }
            case 'a': { const call = c.currentCall; if (call) c.avoidTg(call);                break; }
            case 'A': { const call = c.currentCall; if (call) c.avoidSys(call);               break; }
            case '+': case '=': c.setVolume(c.volume + 10); break;
            case '-':           c.setVolume(c.volume - 10); break;
            case 'q': c.quit(); break;
        }
    }

    _searchKey(k) {
        const c = this.ctrl;
        switch (k) {
            case 'l':              c.setMode('live');   break;
            case 's': case 'r':   c.runSearch();       break;
            case '\r': case '\n': {
                const item = c.searchResults?.results?.[c.searchIdx];
                if (item) c.playSearchItem(item);
                break;
            }
            case '/': case 'f':   this._promptFilter(); break;
            case 'q':             c.quit();             break;
        }
    }

    _selectKey(k) {
        const c = this.ctrl;
        if (k === '\r' || k === '\n') { c.toggleCatSys(c.catSysIdx); return; }
        if (k === 'q') c.setMode('live');
    }

    _escKey() {
        if (this.ctrl.mode === 'select') this.ctrl.setMode('live');
    }

    _navUp() {
        const c = this.ctrl;
        if (c.mode === 'search') {
            if (c.searchIdx > 0) c.setSearchIdx(c.searchIdx - 1);
        } else if (c.mode === 'select') {
            if (c.catSysIdx > 0) c.setCatSysIdx(c.catSysIdx - 1);
        }
    }

    _navDown() {
        const c = this.ctrl;
        if (c.mode === 'search') {
            const max = (c.searchResults?.results?.length || 1) - 1;
            if (c.searchIdx < max) c.setSearchIdx(c.searchIdx + 1);
        } else if (c.mode === 'select') {
            const max = c.systems.length - 1;
            if (c.catSysIdx < max) c.setCatSysIdx(c.catSysIdx + 1);
        }
    }

    _navLeft() {
        const c = this.ctrl;
        if (c.mode === 'search' && c.searchOpts.offset >= c.searchOpts.limit) {
            c.runSearch({ offset: c.searchOpts.offset - c.searchOpts.limit });
        }
    }

    _navRight() {
        const c = this.ctrl;
        if (c.mode === 'search') {
            const total = c.searchResults?.total || 0;
            const { limit, offset } = c.searchOpts;
            if (offset + limit < total) c.runSearch({ offset: offset + limit });
        }
    }

    _promptFilter() {
        if (this.ctrl.blocking) return;
        this.ctrl.setBlocking(true);
        if (process.stdin.isTTY) process.stdin.setRawMode(false);

        const rl  = readline.createInterface({ input: process.stdin, output: process.stdout });
        const row = this.ctrl.rows();
        const o   = this.ctrl.searchOpts;
        const cur = `sys=${o.systemId??'any'} tg=${o.talkgroupId??'any'} unit=${o.unitId??'any'}`;

        process.stdout.write(goto(row - 2) + CLRL + `\x1b[2mCurrent: ${cur}\x1b[0m\n`);
        process.stdout.write(goto(row - 1) + CLRL);
        process.stdout.write(goto(row)     + CLRL);

        rl.question(`${YEL}Filter [sys=N] [tg=N] [unit=N] [before=YYYY-MM-DD] [after=YYYY-MM-DD] [clear]: ${R}`, (input) => {
            rl.close();
            this.ctrl.setBlocking(false);
            if (process.stdin.isTTY) process.stdin.setRawMode(true);
            if (input) {
                const parsed = this._parseFilter(input.trim(), this.ctrl.searchOpts);
                this.ctrl.runSearch({ ...parsed, offset: 0 });
            }
            this._schedRender();
        });
    }

    _parseFilter(input, current) {
        if (input === 'clear') {
            return { limit: 50, offset: 0, systemId: null, talkgroupId: null, unitId: null, before: null, after: null };
        }
        const opts = { ...current };
        for (const part of input.split(/\s+/)) {
            const [k, v] = part.split('=');
            if (!k || !v) continue;
            switch (k.toLowerCase()) {
                case 'sys': case 'system':    opts.systemId    = parseInt(v, 10) || null; break;
                case 'tg':  case 'talkgroup': opts.talkgroupId = parseInt(v, 10) || null; break;
                case 'unit':                  opts.unitId      = parseInt(v, 10) || null; break;
                case 'before': {
                    const d = new Date(v);
                    if (!isNaN(d.getTime())) opts.before = d.getTime();
                    break;
                }
                case 'after': {
                    const d = new Date(v);
                    if (!isNaN(d.getTime())) opts.after = d.getTime();
                    break;
                }
            }
        }
        return opts;
    }
}

export default TuiPlugin;
