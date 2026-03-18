#!/usr/bin/env node

import { parseArgs, HELP } from './src/args.js';
import { mergeConfig }     from './src/config.js';
import logger, { addFileTransport } from './src/logger.js';
import { Core }            from './src/core.js';
import { printBanner }     from './src/banner.js';

const VERSION = '1.0.0';

const rawArgs = parseArgs(process.argv);

if (rawArgs.help)    { console.log(HELP); process.exit(0); }
if (rawArgs.version) { console.log(`squelch-tail-cli v${VERSION}`); process.exit(0); }
printBanner();

const args = mergeConfig(rawArgs);

if (!args.url && !args.testData) {
    console.error('Error: server URL is required.\n\nUsage: squelch-tail <ws://host:5000> [options]\n       squelch-tail --help');
    process.exit(1);
}

// Configure logger
logger.level = args.logLevel || 'info';
if (args.logFilePath) addFileTransport(args.logFilePath);

logger.info(`Squelch Tail CLI v${VERSION}`);

// ── Test-data mode ────────────────────────────────────────────────────────────
if (args.testData) {
    logger.info('Test-data mode: driving display with simulated call data');

    const { default: PygameDisplayPlugin } = await import('./src/plugins/pygame-display.js');
    const plugin = new PygameDisplayPlugin();
    plugin.init(
        { testData: true, callSecs: args.callSecs, standbySecs: args.standbySecs },
        null,
        logger,
    );

    process.on('SIGINT',  () => { plugin.destroy(); process.exit(0); });
    process.on('SIGTERM', () => { plugin.destroy(); process.exit(0); });

} else {
    // ── Normal / live-server mode ─────────────────────────────────────────────
    logger.info(`Server: ${args.url}`);

    const core = new Core(args);

    // Load built-in plugins
    if (args.interactive) {
        await core.plugins.loadBuiltin(new URL('./src/plugins/tui.js', import.meta.url).pathname);
    } else {
        await core.plugins.loadBuiltin(new URL('./src/plugins/daemon-json.js', import.meta.url).pathname);
    }

    if (args.muteMdc !== false) {
        await core.plugins.loadBuiltin(new URL('./src/plugins/mute-mdc.js', import.meta.url).pathname);
    }

    await core.start();
}