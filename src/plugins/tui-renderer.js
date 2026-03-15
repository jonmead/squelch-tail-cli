import { R, BOLD, DIM, RED, GREEN, YEL, CYAN, WHITE, BGBLU, CLS, writeat, trunc, pad } from '../ansi.js';
import { fmtFreq, fmtDate, fmtTime, bar } from '../format.js';

/**
 * TuiRenderer — draws the interactive TUI to stdout.
 *
 * Reads state via the TUI plugin's Controller (this.p.ctrl).
 * Adapted for Squelch Tail call fields:
 *   systemId, talkgroupId, freq, startTime/dateTime, units[], tgGroup, tgGroupTag, etc.
 */
class TuiRenderer {
    constructor(tuiPlugin) {
        this.p = tuiPlugin;
    }

    render() {
        const p = this.p;
        if (p.blocking)            return;
        if (!process.stdout.isTTY) return;
        process.stdout.write(CLS);
        if      (p.mode === 'live')   this._renderLive();
        else if (p.mode === 'search') this._renderSearch();
        else if (p.mode === 'select') this._renderSelect();
    }

    // ── Live mode ─────────────────────────────────────────────────────────────
    _renderLive() {
        const p = this.p;
        const c = p.ctrl;
        const W = c.cols(), H = c.rows();
        this._renderHeader(1, W);
        writeat(2, '─'.repeat(W));

        let row = 3;

        const liveStr  = c.paused    ? `${YEL}⏸ PAUSED${R}`
                       : c.lfActive  ? `${GREEN}● LIVE${R}`
                       :               `${DIM}○ OFFLINE${R}`;
        const holdStr  = c.holdSys != null ? `  ${CYAN}[HOLD SYS]${R}`
                       : c.holdTg  != null ? `  ${CYAN}[HOLD TG]${R}` : '';
        const qStr     = c.queue.length > 0 ? `  ${DIM}Queue: ${c.queue.length}${R}` : '';
        const avoidNow = c.avoidList.filter(a => a.until > Date.now());
        const avStr    = avoidNow.length > 0 ? `  ${YEL}Avoided: ${avoidNow.length}${R}` : '';
        writeat(row++, ` ${liveStr}${holdStr}${qStr}${avStr}`);

        row++;  // blank

        const call = c.currentCall;
        if (call) {
            const sys = call.systemData;

            writeat(row++, ` System:    ${BOLD}${trunc(call.systemLabel || `System ${call.systemId}`, W - 20)}${R} ${DIM}(${call.systemId})${R}`);

            const emerBadge = call.emergency ? `  ${RED}${BOLD}★ EMERGENCY${R}` : '';
            const encBadge  = call.encrypted ? `  ${YEL}🔒 ENCRYPTED${R}` : '';
            const tgStr     = call.tgLabel ? `${call.talkgroupId} - ${call.tgLabel}` : String(call.talkgroupId);
            const tgName    = call.tgName  ? ` ${DIM}(${call.tgName})${R}` : '';
            writeat(row++, ` Talkgroup: ${BOLD}${trunc(tgStr, W - 30)}${R}${tgName}${emerBadge}${encBadge}`);

            const grp = call.tgGroup || call.tgGroupTag;
            if (grp) {
                writeat(row++, ` Group:     ${call.tgGroup || '—'}   Tag: ${call.tgGroupTag || '—'}`);
            } else { row++; }

            writeat(row++, ` Frequency: ${CYAN}${fmtFreq(call.freq)}${R}   ${DIM}${fmtDate(call.dateTime)}${R}`);

            const patches = call.patchedTgs || [];
            if (patches.length > 0) {
                const pLabels = patches.map(pid => {
                    const ptg = (sys?.talkgroups || []).find(t => t.id === pid);
                    return ptg ? `${CYAN}${pid}${R} ${DIM}${ptg.label}${R}` : `${CYAN}${pid}${R}`;
                }).join('  ');
                writeat(row++, ` Patches:   ${DIM}${patches.join(', ')}${R}`);
            }

            row++;

            const dynEnd = H - 4;

            const units = call.units || [];
            if (units.length > 0 && row < dynEnd - 1) {
                writeat(row++, ` ${BOLD}Units${R} ${DIM}(${units.length})${'─'.repeat(Math.max(0, W - 11))}${R}`);
                for (let i = 0; i < units.length; i++) {
                    if (row >= dynEnd) { writeat(row++, `  ${DIM}… and ${units.length - i} more${R}`); break; }
                    const u      = units[i];
                    const emrMk  = u.emergency  ? `${RED}★${R} ` : '  ';
                    const posStr = u.pos != null ? `@${Number(u.pos).toFixed(1)}s` : '';
                    const timeStr = u.txTime ? fmtTime(new Date(u.txTime)) : '';
                    const posCol  = pad(posStr, 7);
                    const idCol   = pad(String(u.unitId), 8);
                    const tagPart = u.tag ? `  ${trunc(u.tag, W - 32)}` : '';
                    const timeCol = timeStr ? `  ${DIM}${timeStr}${R}` : '';
                    writeat(row++, `  ${emrMk}${DIM}${posCol}${R}  ${CYAN}${idCol}${R}${tagPart}${timeCol}`);
                }
            }

            const freqs = Array.isArray(call.freqList) ? call.freqList : [];
            if (freqs.length > 1 && row < dynEnd) {
                writeat(row++, ` ${BOLD}Freq hops${R} ${DIM}(${freqs.length})${'─'.repeat(Math.max(0, W - 15))}${R}`);
                const inline    = freqs.map(f => `${DIM}@${(f.pos || 0).toFixed(1)}s${R} ${CYAN}${fmtFreq(f.freq)}${R}`).join('  ');
                const inlineRaw = inline.replace(/\x1b\[[0-9;]*m/g, '');
                if (inlineRaw.length <= W - 2 && row < dynEnd) {
                    writeat(row, ` ${inline}`);
                } else {
                    for (const f of freqs) {
                        if (row >= dynEnd) break;
                        writeat(row++, `  ${DIM}@${(f.pos || 0).toFixed(1)}s${R}  ${CYAN}${fmtFreq(f.freq)}${R}`);
                    }
                }
            }

            const barW = Math.max(20, W - 20);
            writeat(H - 3, ` ${CYAN}${bar(c.elapsed, barW)}${R}  ${c.elapsed.toFixed(1)}s`);

        } else {
            if (!c.connected) {
                writeat(row, ` ${DIM}Connecting…${R}`);
            } else {
                writeat(row, ` ${DIM}Waiting for calls…${R}`);
            }
        }

        writeat(H - 1, '─'.repeat(W));
        writeat(H, ` ${DIM}[l]ive [s]earch [c]ategory | [SPC]skip [p]ause [H]oldSys [h]oldTG [A]voidSys [a]voidTG [+/-]vol [q]uit${R}`);
    }

    // ── Search mode ───────────────────────────────────────────────────────────
    _renderSearch() {
        const p = this.p;
        const c = p.ctrl;
        const W = c.cols(), H = c.rows();
        this._renderHeader(1, W);
        writeat(2, '─'.repeat(W));

        let row = 3;
        const o   = c.searchOpts;
        const res = c.searchResults;

        const fp = [];
        if (o.systemId)    fp.push(`Sys:${o.systemId}`);
        if (o.talkgroupId) fp.push(`TG:${o.talkgroupId}`);
        if (o.unitId)      fp.push(`Unit:${o.unitId}`);
        if (o.before)      fp.push(`Before:${new Date(o.before).toISOString().slice(0, 10)}`);
        if (o.after)       fp.push(`After:${new Date(o.after).toISOString().slice(0, 10)}`);
        const fStr = fp.length ? fp.join(' ') : 'All';
        writeat(row++, ` ${BOLD}SEARCH${R}  ${CYAN}${fStr}${R}  [/] filter`);

        if (res) {
            const page  = Math.floor(o.offset / o.limit) + 1;
            const pages = Math.ceil(res.total / o.limit) || 1;
            writeat(row++, ` ${res.total} calls | Page ${page}/${pages} | [← →] pages`);
        } else {
            writeat(row++, ` ${DIM}Loading…${R}`);
        }

        writeat(row++, '─'.repeat(W));
        row++;

        const cD = 22, cS = 18;
        const cT = Math.max(10, W - cD - cS - 8);
        writeat(row++, ` ${BOLD}${pad('#', 5)} ${pad('Date/Time', cD)} ${pad('System', cS)} ${'Talkgroup'.slice(0, cT)}${R}`);
        writeat(row++, ` ${'─'.repeat(W - 2)}`);

        const maxRows   = H - row - 3;
        const items     = res?.results || [];
        const half      = Math.floor(maxRows / 2);
        const viewStart = Math.max(0, Math.min(items.length - maxRows, c.searchIdx - half));
        const viewEnd   = Math.min(items.length, viewStart + maxRows);

        for (let i = viewStart; i < viewEnd && row < H - 3; i++) {
            const item  = items[i];
            const sel   = i === c.searchIdx;
            const num   = pad(String(o.offset + i + 1), 5);
            const dt    = pad(fmtDate(item.dateTime), cD);
            const sys   = pad(item.systemLabel || `Sys ${item.systemId}`, cS);
            const tgStr = item.tgLabel ? `${item.talkgroupId} - ${item.tgLabel}` : String(item.talkgroupId);
            if (sel) {
                writeat(row++, ` ${BGBLU}${WHITE}${BOLD}${num} ${dt} ${sys} ${trunc(tgStr, cT)}${R}`);
            } else {
                writeat(row++, ` ${num} ${DIM}${dt}${R} ${sys} ${trunc(tgStr, cT)}`);
            }
        }

        if (c.playing && c.currentCall) {
            const bw = Math.min(40, W - 20);
            writeat(H - 3, ` ${GREEN}▶ Playing:${R} ${CYAN}${bar(c.elapsed, bw)}${R} ${c.elapsed.toFixed(1)}s`);
        }

        writeat(H - 1, '─'.repeat(W));
        writeat(H, ` ${DIM}[↑↓]navigate [ENTER]play [←→]page [/]filter [l]live [q]quit${R}`);
    }

    // ── Category selection mode ───────────────────────────────────────────────
    _renderSelect() {
        const p = this.p;
        const c = p.ctrl;
        const W = c.cols(), H = c.rows();
        this._renderHeader(1, W);
        writeat(2, '─'.repeat(W));

        let row = 3;
        writeat(row++, ` ${BOLD}SYSTEM / TALKGROUP SELECTION${R}   [↑↓] navigate  [ENTER] toggle  [q/ESC] back`);
        writeat(row++, '─'.repeat(W));
        row++;

        const maxRows = H - row - 3;
        const half    = Math.floor(maxRows / 4);
        const start   = Math.max(0, c.catSysIdx - half);

        for (let si = start; si < c.systems.length && row < H - 3; si++) {
            const sys    = c.systems[si];
            const sel    = si === c.catSysIdx;
            const sysKey = String(sys.id);
            const tgs    = sys.talkgroups || [];
            const cur    = c.lfMap[sysKey] || {};
            const onCnt  = tgs.filter(tg => cur[String(tg.id)]).length;
            const dot    = onCnt === tgs.length ? `${GREEN}●`
                         : onCnt === 0           ? `${RED}○`
                         :                         `${YEL}◐`;
            const line   = ` ${dot}${R} ${sel ? BOLD + BGBLU + WHITE : ''}${pad(sys.label, 30)}${R} ${DIM}${onCnt}/${tgs.length} active (ID ${sys.id})${R}`;
            writeat(row++, line);

            if (sel && row < H - 4) {
                const sub = tgs.slice(0, 8);
                for (const tg of sub) {
                    if (row >= H - 4) break;
                    const on   = cur[String(tg.id)];
                    const dot2 = on ? `${GREEN}  ●` : `${RED}  ○`;
                    writeat(row++, `  ${dot2}${R} ${tg.label} ${DIM}(${tg.id})${R}`);
                }
                if (tgs.length > 8) writeat(row++, `     ${DIM}… and ${tgs.length - 8} more${R}`);
            }
        }

        writeat(H - 1, '─'.repeat(W));
        writeat(H, ` ${DIM}[ENTER] toggle all talkgroups in system  [q/ESC] return to live feed${R}`);
    }

    // ── Shared header ─────────────────────────────────────────────────────────
    _renderHeader(row) {
        const c      = this.p.ctrl;
        const title  = `${BOLD}${YEL} SQUELCH TAIL${R}`;
        const url    = ` ${DIM}${c.url}${R}`;
        const status = c.connected ? `${GREEN}●${R}` : `${RED}●${R}`;
        writeat(row, `${title}${url}  ${status}`);
    }
}

export { TuiRenderer };
