import fs   from 'fs';
import http from 'http';
import https from 'https';
import os   from 'os';
import path from 'path';
import { spawn, spawnSync } from 'child_process';
import logger from './logger.js';

const log = logger.child({ label: 'audio' });

function _ext(t) {
    if (!t) return '.wav';
    if (t.includes('wav'))                        return '.wav';
    if (t.includes('mp3') || t.includes('mpeg')) return '.mp3';
    if (t.includes('mp4') || t.includes('aac') || t.includes('m4a')) return '.m4a';
    if (t.includes('ogg'))                        return '.ogg';
    if (t.includes('flac'))                       return '.flac';
    return '.wav';
}

/**
 * Fetch a URL and return a Buffer.  Follows redirects once.
 * @param {string} url  Absolute HTTP/HTTPS URL.
 * @returns {Promise<Buffer>}
 */
function fetchBuf(url) {
    return new Promise((resolve, reject) => {
        const lib = url.startsWith('https') ? https : http;
        lib.get(url, (res) => {
            if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
                return fetchBuf(res.headers.location).then(resolve, reject);
            }
            if (res.statusCode !== 200) {
                res.resume();
                return reject(new Error(`HTTP ${res.statusCode} for ${url}`));
            }
            const chunks = [];
            res.on('data', (c) => chunks.push(c));
            res.on('end',  ()  => resolve(Buffer.concat(chunks)));
            res.on('error', reject);
        }).on('error', reject);
    });
}

class AudioPlayer {
    constructor({ player, volume, noAudio }) {
        this.noAudio = noAudio;
        this.volume  = Math.max(0, Math.min(100, volume || 100));
        this.player  = player || this._detect();
        this.proc    = null;
        this.tmpFile = null;
        this.onEndCb = null;

        if (this.noAudio) {
            log.info('Audio disabled (--no-audio)');
        } else if (this.player) {
            log.info(`Audio player: ${this.player} (volume: ${this.volume}%)`);
        } else {
            log.warn('No audio player found on PATH — playback will be silent. Install mpv, ffplay, or aplay.');
        }
    }

    _detect() {
        const candidates = process.platform === 'darwin'
            ? ['afplay', 'mpv', 'ffplay', 'play']
            : ['mpv', 'ffplay', 'aplay', 'paplay', 'play'];
        for (const p of candidates) {
            try {
                const r = spawnSync('which', [p], { stdio: 'pipe' });
                if (r.status === 0) return p;
            } catch (_) {}
        }
        return null;
    }

    play(buf, audioType, onEnd) {
        if (this.noAudio || !this.player || !buf) { onEnd?.(); return; }
        log.debug(`Playing ${_ext(audioType)} audio (${buf.length} bytes)`);
        this.stop();
        const ext    = _ext(audioType);
        this.tmpFile = path.join(os.tmpdir(), `squelch-tail-${Date.now()}${ext}`);
        this.onEndCb = onEnd;
        const tmpFile = this.tmpFile;
        fs.writeFile(tmpFile, buf, (err) => {
            if (this.tmpFile !== tmpFile) {
                // Cancelled by stop() or a subsequent play() — discard.
                try { fs.unlinkSync(tmpFile); } catch (_) {}
                return;
            }
            if (err) {
                log.error(`Failed to write temp file: ${err.message}`);
                this.tmpFile = null;
                this._cleanup();
                return;
            }
            const args = this._args(tmpFile);
            this.proc  = spawn(this.player, args, { stdio: 'ignore' });
            this.proc.on('exit',  () => this._cleanup());
            this.proc.on('error', () => this._cleanup());
        });
    }

    stop() {
        if (this.proc) {
            try { this.proc.kill('SIGTERM'); } catch (_) {}
            this.proc = null;
        }
        if (this.tmpFile) {
            try { fs.unlinkSync(this.tmpFile); } catch (_) {}
            this.tmpFile = null;
        }
    }

    _cleanup() {
        this.proc = null;
        if (this.tmpFile) {
            try { fs.unlinkSync(this.tmpFile); } catch (_) {}
            this.tmpFile = null;
        }
        log.debug('Playback finished');
        const cb = this.onEndCb;
        this.onEndCb = null;
        cb?.();
    }

    _args(file) {
        const v = this.volume / 100;
        switch (this.player) {
            case 'afplay':  return ['-q', '1', ...(this.volume < 100 ? ['-v', String(v)] : []), file];
            case 'mpv':     return ['--quiet', '--no-video', `--volume=${this.volume}`, file];
            case 'ffplay':  return ['-nodisp', '-autoexit', '-loglevel', 'quiet', file];
            case 'aplay':   return [file];
            case 'paplay':  return [file];
            case 'play':    return [file, ...(this.volume < 100 ? ['vol', String(v)] : [])];
            default:        return [file];
        }
    }
}

export { AudioPlayer, fetchBuf, _ext };
