# Configuration Reference

Config is loaded from `./config.json` (or the path given by `--config`).
CLI arguments always override config file values.

---

## All options

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `server` | string | — | Server URL (`http://`, `https://`, `ws://`, or `wss://`) |
| `monitor` | array | *(all)* | Include filter — see below |
| `monitorExclude` | array | *(none)* | Exclude filter — see below |
| `interactive` | boolean | `false` | Launch the full TUI |
| `search` | boolean | `false` | Start in search/playback mode |
| `autoPlay` | boolean | `false` | Auto-play all search results sequentially |
| `audio.noAudio` | boolean | `false` | Suppress audio playback |
| `audio.player` | string | *(auto)* | Force a player binary (`mpv`, `aplay`, `afplay`, `ffplay`) |
| `audio.volume` | integer | `100` | Playback volume (0–100) |
| `avoidMinutes` | integer | `15` | Minutes a talkgroup/system stays avoided |
| `logLevel` | string | `"info"` | Winston log level (`error`, `warn`, `info`, `debug`) |
| `logFilePath` | string | `null` | Write logs to this file (in addition to stderr) |
| `plugins` | array | `[]` | Plugin paths to load (strings or `{ "path": "..." }` objects) |

---

## `monitor` and `monitorExclude` — include/exclude filter rules

Both fields accept the same array format:

```json
[
  { "system": <systemId> },
  { "system": <systemId>, "talkgroups": [<tgId>, ...] }
]
```

- **Omit `talkgroups`** → all talkgroups in that system match.
- **Provide `talkgroups`** → only those specific talkgroup IDs match.

The two fields are applied together: a call is active when it **matches `monitor`** AND **does not match `monitorExclude`**.

---

## Common patterns

### 1. Monitor everything (default)

Omit both `monitor` and `monitorExclude`, or set them to `null`.

```json
{}
```

---

### 2. One whole system

```json
{
  "monitor": [
    { "system": 101 }
  ]
}
```

All talkgroups in system 101; nothing else.

---

### 3. Specific talkgroups within one system

```json
{
  "monitor": [
    { "system": 101, "talkgroups": [1001, 1002, 1003] }
  ]
}
```

Only TGs 1001, 1002, 1003 in system 101.

---

### 4. Multiple systems, mixed specificity

```json
{
  "monitor": [
    { "system": 101 },
    { "system": 202, "talkgroups": [2001, 2002] },
    { "system": 303 }
  ]
}
```

- System 101 → all TGs
- System 202 → TGs 2001 and 2002 only
- System 303 → all TGs

---

### 5. All systems except specific talkgroups

Monitor everything but suppress a few noisy TGs:

```json
{
  "monitorExclude": [
    { "system": 101, "talkgroups": [9001, 9002] }
  ]
}
```

---

### 6. All systems except an entire system

```json
{
  "monitorExclude": [
    { "system": 404 }
  ]
}
```

Everything except system 404.

---

### 7. Allowlist a system, then blocklist noisy TGs within it

```json
{
  "monitor": [
    { "system": 101 },
    { "system": 202 }
  ],
  "monitorExclude": [
    { "system": 101, "talkgroups": [9999] },
    { "system": 202, "talkgroups": [8888, 8889] }
  ]
}
```

- System 101 → all TGs except 9999
- System 202 → all TGs except 8888 and 8889

---

### 8. Tight allowlist with a single exception

Include only three talkgroups, but one of those has a sub-channel you want to suppress:

```json
{
  "monitor": [
    { "system": 101, "talkgroups": [100, 200, 300] }
  ],
  "monitorExclude": [
    { "system": 101, "talkgroups": [200] }
  ]
}
```

Result: TGs 100 and 300 only (200 is re-excluded).

---

## Priority rules (quick reference)

| `monitor` | `monitorExclude` | Result |
|-----------|-----------------|--------|
| absent / null | absent / null | **all calls pass** |
| present, system matched, no TG list | — | all TGs in that system pass monitor |
| present, system matched, TG list | — | only listed TGs pass monitor |
| present, system **not** matched | — | call blocked |
| — | present, matched | call blocked regardless of monitor |
| — | present, not matched | no effect |

Exclusion always wins: if a call matches both `monitor` and `monitorExclude`, it is suppressed.
