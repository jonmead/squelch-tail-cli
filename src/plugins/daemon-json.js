/**
 * DaemonJsonPlugin — non-interactive (daemon) output plugin.
 *
 * Writes one JSON line per call to stdout (machine-readable; safe to pipe).
 * Logs human-readable summaries to stderr via the logger.
 *
 * Automatically loaded by index.js when --interactive is not given.
 */
class DaemonJsonPlugin {
    init(config, controller, logger) {
        this._log  = logger.child({ label: 'daemon' });
        this._ctrl = controller;
    }

    onCallStart(call) {
        const line = JSON.stringify({
            id:          call.id,
            startTime:   call.startTime,
            systemId:    call.systemId,
            systemLabel: call.systemLabel,
            talkgroupId: call.talkgroupId,
            tgLabel:     call.tgLabel,
            tgName:      call.tgName,
            freq:        call.freq,
            audioType:   call.audioType,
            audioUrl:    call.audioUrl,
            emergency:   call.emergency,
            units:       (call.units || []).map(u => ({ unitId: u.unitId, txTime: u.txTime })),
        });
        process.stdout.write(line + '\n');

        const sys  = call.systemLabel             || `System ${call.systemId}`;
        const tg   = call.tgLabel                 || `TG ${call.talkgroupId}`;
        const freq = call.freq ? `${(call.freq / 1e6).toFixed(4)} MHz` : '';
        const ts   = call.startTime || '';
        this._log.info(`[CALL] ${ts}  ${sys}  ${tg}  ${freq}`);
    }

    onStatus(connected) {
        if (this._log) {
            if (connected) this._log.info('Connected');
            else           this._log.warn('Disconnected. Reconnecting\u2026');
        }
    }
}

export default DaemonJsonPlugin;
