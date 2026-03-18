import fs   from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import logger from './logger.js';

const log = logger.child({ label: 'config' });
const __dirname = path.dirname(fileURLToPath(import.meta.url));

/**
 * Build a lookup structure from a monitor config array.
 *
 * Each entry: { system: <id>, talkgroups: [<id>, ...] }
 *   - "talkgroups" is optional; omitting it means all talkgroups in this system
 *
 * Returns null when monitorCfg is null/absent (= monitor everything).
 * Returns Map<systemId, Set<tgId>|null>:
 *   - null value  → all talkgroups in that system
 *   - Set value   → only those specific talkgroup IDs
 */
function buildMonitorMap(monitorCfg) {
    if (!monitorCfg || !Array.isArray(monitorCfg)) return null;
    const map = new Map();
    for (const entry of monitorCfg) {
        if (entry.system == null) continue;
        const sysId = Number(entry.system);
        map.set(sysId, Array.isArray(entry.talkgroups)
            ? new Set(entry.talkgroups.map(Number))
            : null
        );
    }
    return map;
}

function isMonitored(monitorMap, sysId, tgId) {
    if (!monitorMap) return true;
    const tgs = monitorMap.get(Number(sysId));
    if (tgs === undefined) return false;
    if (tgs === null)      return true;
    return tgs.has(Number(tgId));
}

function isExcluded(excludeMap, sysId, tgId) {
    if (!excludeMap) return false;
    return isMonitored(excludeMap, sysId, tgId);
}

const DEFAULT_SEARCH_PATHS = [
    path.resolve(process.cwd(), 'config.json'),
    path.resolve(__dirname, '..', 'config.json'),
];

function readConfigFile(configPath) {
    const candidates = configPath
        ? [path.resolve(configPath)]
        : DEFAULT_SEARCH_PATHS;

    for (const p of candidates) {
        if (!fs.existsSync(p)) continue;
        try {
            const data = JSON.parse(fs.readFileSync(p, 'utf8'));
            log.info(`Loaded ${p}`);
            return { data, path: p };
        } catch (err) {
            log.error(`Failed to parse ${p}: ${err.message}`);
        }
    }

    return { data: {}, path: null };
}

/**
 * Merge config.json and CLI args into one resolved options object.
 * Priority: CLI args > config.json > built-in defaults.
 */
function mergeConfig(args) {
    const { data: cfg } = readConfigFile(args.config);
    const audio = cfg.audio || {};

    const pluginMap = new Map();
    for (const entry of [...(cfg.plugins || []), ...(args.plugins || [])]) {
        const p = typeof entry === 'string' ? entry : entry.path;
        if (p && !pluginMap.has(p)) pluginMap.set(p, entry);
    }
    const plugins = [...pluginMap.values()];

    // Normalise server URL to WebSocket URL
    let url = args.url ?? cfg.server ?? null;
    if (url && url.startsWith('http://'))  url = 'ws://'  + url.slice(7);
    if (url && url.startsWith('https://')) url = 'wss://' + url.slice(8);
    // Append /ws if no path given
    if (url && !url.includes('/ws')) url = url.replace(/\/$/, '') + '/ws';

    return {
        url,

        monitor:        buildMonitorMap(cfg.monitor        ?? null),
        monitorExclude: buildMonitorMap(cfg.monitorExclude ?? null),
        systemId:       args.systemId    ?? cfg.systemId    ?? null,
        talkgroupId:    args.talkgroupId ?? cfg.talkgroupId ?? null,
        unitId:         args.unitId      ?? cfg.unitId      ?? null,

        interactive:  args.interactive || cfg.interactive  || false,
        search:       args.search      || cfg.search       || false,
        autoPlay:     args.autoPlay    || cfg.autoPlay     || false,

        noAudio:      args.noAudio     || audio.noAudio    || cfg.noAudio    || false,
        player:       args.player      ?? audio.player     ?? cfg.player     ?? null,
        volume:       args.volume      ?? audio.volume     ?? cfg.volume     ?? 100,

        avoidMinutes: args.avoidMinutes ?? cfg.avoidMinutes ?? 15,

        testData:     args.testData    || false,
        callSecs:     args.callSecs    ?? 3,
        standbySecs:  args.standbySecs ?? 3,

        logLevel:     cfg.logLevel ?? process.env.LOG_LEVEL ?? 'info',
        logFilePath:  cfg.logFilePath ?? null,

        plugins,
    };
}

export { mergeConfig, buildMonitorMap, isMonitored, isExcluded };
