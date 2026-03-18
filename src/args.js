const HELP = `
Squelch Tail CLI v1.0.0

Usage: squelch-tail <server-url> [options]

  server-url             WebSocket URL  (e.g. ws://localhost:5000 or http://host:5000)
                         Overrides "server" in config.json when given.

Options:
  -c, --config <path>    Path to config file (default: ./config.json)
  -s, --system <id>      Pre-filter by system ID
  -t, --talkgroup <id>   Pre-filter by talkgroup ID
  -u, --unit <id>        Pre-filter by unit ID
      --interactive      Run the full TUI (default: non-interactive / daemon mode)
      --no-audio         Metadata display only, no audio playback
      --player <cmd>     Force a specific audio player (mpv, aplay, afplay, ffplay …)
      --volume <0-100>   Playback volume (default: 100)
      --avoid-minutes N  Duration for avoid (default: 15)
      --search           Start in search/playback mode (implies --interactive)
      --auto-play        Auto-play all search results sequentially
      --plugin <path>    Load a display plugin (e.g. ./plugins/my-plugin.js)
                         May be specified multiple times
  -v, --version          Show version
  -h, --help             Show this help

All options above can be set in config.json instead of (or as defaults for) the
command line.  CLI arguments always take precedence over config file values.

Live-feed keys:
  l          Live feed mode
  s          Search/playback mode
  c          Category selection (toggle systems/talkgroups)
  SPACE      Skip current call
  p          Pause / resume queue
  H          Hold current system (toggle)
  h          Hold current talkgroup (toggle)
  A          Avoid current system for --avoid-minutes minutes
  a          Avoid current talkgroup for --avoid-minutes minutes
  +/-        Volume up / down
  q / Ctrl+C Quit

Search keys:
  ↑ / ↓     Navigate result list
  ← / →     Previous / next page
  ENTER      Play selected call
  /          Open filter prompt
  l          Switch to live feed
  q / Ctrl+C Quit

Category selection keys:
  ↑ / ↓     Navigate systems
  ENTER      Toggle all talkgroups in system on/off
  q / ESC    Return to live feed
`.trim();

function parseArgs(argv) {
    const a = {
        url: null, config: null, systemId: null, talkgroupId: null, unitId: null,
        noAudio: false, player: null,
        volume: null,
        avoidMinutes: null,
        interactive: false, search: false, autoPlay: false,
        plugins: [],
        testData: false, callSecs: 3, standbySecs: 3,
        help: false, version: false,
    };
    for (let i = 2; i < argv.length; i++) {
        switch (argv[i]) {
            case '-c': case '--config':        a.config        = argv[++i]; break;
            case '-s': case '--system':        a.systemId      = parseInt(argv[++i], 10); break;
            case '-t': case '--talkgroup':     a.talkgroupId   = parseInt(argv[++i], 10); break;
            case '-u': case '--unit':          a.unitId        = parseInt(argv[++i], 10); break;
            case '--player':                   a.player        = argv[++i]; break;
            case '--volume':                   a.volume        = parseInt(argv[++i], 10); break;
            case '--avoid-minutes':            a.avoidMinutes  = parseInt(argv[++i], 10); break;
            case '--no-audio':                 a.noAudio       = true; break;
            case '--interactive':              a.interactive   = true; break;
            case '--search':                   a.search        = true; a.interactive = true; break;
            case '--auto-play':                a.autoPlay      = true; break;
            case '--plugin':                   a.plugins.push(argv[++i]); break;
            case '--test-data':                a.testData      = true; break;
            case '--call-secs':                a.callSecs      = parseFloat(argv[++i]); break;
            case '--standby-secs':             a.standbySecs   = parseFloat(argv[++i]); break;
            case '-v': case '--version':       a.version       = true; break;
            case '-h': case '--help':          a.help          = true; break;
            default:
                if (!argv[i].startsWith('-')) a.url = argv[i];
        }
    }
    return a;
}

export { parseArgs, HELP };
