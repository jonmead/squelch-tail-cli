/**
 * Controller — the read/write interface given to every plugin via init().
 *
 * Plugins use this object to read application state and invoke actions.
 * Never exposes Core internals directly.
 */
class Controller {
    constructor(core) {
        this._core = core;
    }

    // ── State getters ─────────────────────────────────────────────────────────
    get connected()     { return this._core.connected; }
    get mode()          { return this._core.mode; }
    get systems()       { return this._core.systems; }
    get lfActive()      { return this._core.lfActive; }
    get lfMap()         { return this._core.lfMap; }
    get queue()         { return this._core.queue; }
    get currentCall()   { return this._core.currentCall; }
    get playing()       { return this._core.playing; }
    get paused()        { return this._core.paused; }
    get elapsed()       { return this._core.elapsed; }
    get holdSys()       { return this._core.holdSys; }
    get holdTg()        { return this._core.holdTg; }
    get avoidList()     { return this._core.avoidList; }
    get searchOpts()    { return this._core.searchOpts; }
    get searchResults() { return this._core.searchResults; }
    get searchIdx()     { return this._core.searchIdx; }
    get catSysIdx()     { return this._core.catSysIdx; }
    get blocking()      { return this._core.blocking; }
    get url()           { return this._core.args.url; }
    get avoidMinutes()  { return this._core.args.avoidMinutes; }
    get volume()        { return this._core.audio.volume; }

    cols() { return process.stdout.columns || 80; }
    rows() { return process.stdout.rows || 24; }

    // ── Actions ───────────────────────────────────────────────────────────────

    activateLF()              { this._core._activateLF(); this._core._notify(); }
    deactivateLF()            { this._core._deactivateLF(); this._core._notify(); }

    setMode(mode)             { this._core._setMode(mode); }

    setHoldSys(sysId)         { this._core._holdSys(sysId); }
    setHoldTg(tgId)           { this._core._holdTg(tgId); }
    avoidTg(call)             { this._core._avoidTg(call); }
    avoidSys(call)            { this._core._avoidSys(call); }

    skipCall()                { this._core._skipCall(); }
    togglePause()             { this._core._togglePause(); }

    setVolume(v) {
        this._core.audio.volume = Math.max(0, Math.min(100, v));
        this._core._notify();
    }

    runSearch(overrides)      { this._core._runSearch(overrides); }
    setSearchOpts(opts)       { this._core.searchOpts = opts; }
    setSearchIdx(n)           { this._core.searchIdx = n; this._core._notify(); }
    setCatSysIdx(n)           { this._core.catSysIdx = n; this._core._notify(); }

    playSearchItem(item)      { this._core._playSearchItem(item); }
    toggleCatSys(sysIdx)      { this._core._toggleCatSys(sysIdx); }

    setBlocking(b)            { this._core.blocking = b; }

    quit()                    { this._core.quit(); }
}

export { Controller };
