const ESC   = '\x1b';
const R     = `${ESC}[0m`;
const BOLD  = `${ESC}[1m`;
const DIM   = `${ESC}[2m`;
const RED   = `${ESC}[31m`;
const GREEN = `${ESC}[32m`;
const YEL   = `${ESC}[33m`;
const CYAN  = `${ESC}[36m`;
const WHITE = `${ESC}[37m`;
const BGBLU = `${ESC}[44m`;
const CLS   = `${ESC}[2J${ESC}[H`;
const HIDEC = `${ESC}[?25l`;
const SHOWC = `${ESC}[?25h`;
const CLRL  = `${ESC}[2K`;

function goto(row, col = 1)  { return `${ESC}[${row};${col}H`; }
function clrline(row)        { process.stdout.write(goto(row) + CLRL); }
function writeat(row, text)  { process.stdout.write(goto(row) + CLRL + text); }
function trunc(s, n)         { return s.length > n ? s.slice(0, n - 1) + '…' : s; }
function pad(s, n)           { s = String(s ?? ''); return s.length >= n ? s.slice(0, n) : s + ' '.repeat(n - s.length); }

export {
    ESC, R, BOLD, DIM, RED, GREEN, YEL, CYAN, WHITE, BGBLU,
    CLS, HIDEC, SHOWC, CLRL,
    goto, clrline, writeat, trunc, pad,
};
