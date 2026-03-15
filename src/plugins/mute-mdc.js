import fs    from 'fs';
import os    from 'os';
import path  from 'path';
import { spawn } from 'child_process';
import { _ext }  from '../audio.js';
import logger from '../logger.js';

/**
 * MuteMdcPlugin — detects and mutes MDC1200 bursts and CTCSS reverse bursts.
 *
 * MDC1200 (Motorola Data Communications) transmits short FSK data packets over
 * the audio channel at ~1200 Hz / ~1800 Hz, heard as audible chirps before and
 * after voice transmissions.
 *
 * CTCSS reverse bursts are brief pure tones (one of the 50 standard PL tones,
 * 67–254 Hz) sent at key-off to snap the receiving squelch shut quickly.
 *
 * Audio arrives as m4a from squelch-tail; ffmpeg transcodes to WAV for native
 * processing, then re-encodes to the original format.
 */

// ─── WAV codec ────────────────────────────────────────────────────────────────

function parseWav(buf) {
    if (buf.length < 44)                              return null;
    if (buf.toString('ascii', 0, 4)  !== 'RIFF')     return null;
    if (buf.toString('ascii', 8, 12) !== 'WAVE')      return null;

    let offset = 12;
    let channels, sampleRate, bitsPerSample, dataOffset, dataLen;

    while (offset < buf.length - 8) {
        const id   = buf.toString('ascii', offset, offset + 4);
        const size = buf.readUInt32LE(offset + 4);
        if (id === 'fmt ') {
            if (buf.readUInt16LE(offset + 8) !== 1) return null;  // not PCM
            channels      = buf.readUInt16LE(offset + 10);
            sampleRate    = buf.readUInt32LE(offset + 12);
            bitsPerSample = buf.readUInt16LE(offset + 22);
        } else if (id === 'data') {
            dataOffset = offset + 8;
            dataLen    = size;
            break;
        }
        offset += 8 + size + (size & 1);
    }

    if (!dataOffset || !channels || !sampleRate) return null;
    return { channels, sampleRate, bitsPerSample, dataOffset, dataLen };
}

function buildWav(samples, sampleRate) {
    const dataSize = samples.length * 2;
    const buf      = Buffer.alloc(44 + dataSize);
    buf.write('RIFF', 0);
    buf.writeUInt32LE(36 + dataSize, 4);
    buf.write('WAVE', 8);
    buf.write('fmt ', 12);
    buf.writeUInt32LE(16,          16);
    buf.writeUInt16LE(1,           20);
    buf.writeUInt16LE(1,           22);
    buf.writeUInt32LE(sampleRate,  24);
    buf.writeUInt32LE(sampleRate * 2, 28);
    buf.writeUInt16LE(2,           32);
    buf.writeUInt16LE(16,          34);
    buf.write('data', 36);
    buf.writeUInt32LE(dataSize,    40);
    for (let i = 0; i < samples.length; i++) {
        buf.writeInt16LE(Math.round(samples[i]), 44 + i * 2);
    }
    return buf;
}

// ─── Goertzel algorithm ───────────────────────────────────────────────────────

function goertzel(samples, freq, sampleRate) {
    const omega = 2 * Math.PI * freq / sampleRate;
    const coeff = 2 * Math.cos(omega);
    let s1 = 0, s2 = 0;
    for (let i = 0; i < samples.length; i++) {
        const s0 = samples[i] + coeff * s1 - s2;
        s2 = s1;
        s1 = s0;
    }
    return s1 * s1 + s2 * s2 - coeff * s1 * s2;
}

const MDC_PROBE_FREQS = [1150, 1200, 1250, 1750, 1800, 1850];

const CTCSS_FREQS = [
     67.0,  69.3,  71.9,  74.4,  77.0,  79.7,  82.5,  85.4,  88.5,  91.5,
     94.8,  97.4, 100.0, 103.5, 107.2, 110.9, 114.8, 118.8, 123.0, 127.3,
    131.8, 136.5, 141.3, 146.2, 151.4, 156.7, 159.8, 162.2, 165.5, 167.9,
    171.3, 173.8, 177.3, 179.9, 183.5, 186.2, 189.9, 192.8, 196.6, 199.5,
    203.5, 206.5, 210.7, 218.1, 225.7, 229.1, 233.6, 241.8, 250.3, 254.1,
];

function detectMdc(samples, sampleRate, sensitivity) {
    const N = samples.length;
    if (N === 0) return false;
    let sumSq = 0;
    for (let i = 0; i < N; i++) sumSq += samples[i] * samples[i];
    const rms = Math.sqrt(sumSq / N);
    if (rms < 50) return false;
    let maxAmplitude = 0;
    for (const f of MDC_PROBE_FREQS) {
        const amplitude = 2 * Math.sqrt(Math.max(0, goertzel(samples, f, sampleRate))) / N;
        if (amplitude > maxAmplitude) maxAmplitude = amplitude;
    }
    return (maxAmplitude / rms) > sensitivity;
}

function detectCtcss(samples, sampleRate, sensitivity) {
    const N = samples.length;
    if (N === 0) return false;
    let sumSq = 0;
    for (let i = 0; i < N; i++) sumSq += samples[i] * samples[i];
    const rms = Math.sqrt(sumSq / N);
    if (rms < 50) return false;
    let maxAmplitude = 0;
    for (const f of CTCSS_FREQS) {
        const amplitude = 2 * Math.sqrt(Math.max(0, goertzel(samples, f, sampleRate))) / N;
        if (amplitude > maxAmplitude) maxAmplitude = amplitude;
    }
    return (maxAmplitude / rms) > sensitivity;
}

function processSamples(mono, sampleRate, opts) {
    const { sensitivity, chirpChunks, muteExtension, attenuationDb,
            plSensitivity, plMuteExtension } = opts;
    const chunkSize    = Math.round(sampleRate * 0.020);
    const attenuFactor = Math.pow(10, -attenuationDb / 20);
    const out          = new Int16Array(mono.length);
    let muteCounter = 0, burstAge = 0, pos = 0;

    while (pos < mono.length) {
        const end   = Math.min(pos + chunkSize, mono.length);
        const chunk = mono.subarray(pos, end);

        const isMdc   = detectMdc(chunk, sampleRate, sensitivity);
        const isCtcss = !isMdc && detectCtcss(chunk, sampleRate, plSensitivity);

        if (isMdc) {
            if (muteCounter === 0) {
                burstAge = 1; muteCounter = muteExtension;
                out.set(chunk, pos);
            } else {
                burstAge++; muteCounter = muteExtension;
                if (burstAge <= chirpChunks) {
                    out.set(chunk, pos);
                } else {
                    for (let i = 0; i < chunk.length; i++) out[pos + i] = Math.round(chunk[i] * attenuFactor);
                }
            }
        } else if (isCtcss) {
            muteCounter = Math.max(muteCounter, plMuteExtension);
            burstAge = 0;
            for (let i = 0; i < chunk.length; i++) out[pos + i] = Math.round(chunk[i] * attenuFactor);
        } else if (muteCounter > 0) {
            for (let i = 0; i < chunk.length; i++) out[pos + i] = Math.round(chunk[i] * attenuFactor);
            if (--muteCounter === 0) burstAge = 0;
        } else {
            out.set(chunk, pos);
            burstAge = 0;
        }
        pos = end;
    }
    return out;
}

// ─── Plugin ───────────────────────────────────────────────────────────────────

class MuteMdcPlugin {
    constructor(options = {}) {
        this.sensitivity     = options.sensitivity     ?? Number(process.env.MUTE_MDC_SENSITIVITY ?? 1.1);
        this.chirpChunks     = options.chirpChunks     ?? 2;
        this.muteExtension   = options.muteExtension   ?? 12;
        this.attenuationDb   = options.attenuationDb   ?? 50;
        this.plSensitivity   = options.plSensitivity   ?? 0.4;
        this.plMuteExtension = options.plMuteExtension ?? 10;
        this.log             = logger.child({ label: 'mute-mdc' });
    }

    init(_config, _controller, logger) {
        this.log = logger.child({ label: 'mute-mdc' });
        this.log.info(`MDC mute enabled (sensitivity=${this.sensitivity}, plSensitivity=${this.plSensitivity})`);
    }

    processAudio(buf, audioType, _call) {
        if (!buf) return buf;
        if (!audioType || audioType.includes('wav')) return this._processWav(buf);
        return this._processViaFfmpeg(buf, audioType);
    }

    _processWav(buf) {
        const hdr = parseWav(buf);
        if (!hdr || hdr.bitsPerSample !== 16) return buf;

        const { channels, sampleRate, dataOffset, dataLen } = hdr;
        const frameCount = Math.floor(dataLen / (2 * channels));
        const mono = new Int16Array(frameCount);
        for (let i = 0; i < frameCount; i++) {
            let sum = 0;
            for (let c = 0; c < channels; c++) {
                sum += buf.readInt16LE(dataOffset + (i * channels + c) * 2);
            }
            mono[i] = Math.round(sum / channels);
        }

        const processed = processSamples(mono, sampleRate, {
            sensitivity:     this.sensitivity,
            chirpChunks:     this.chirpChunks,
            muteExtension:   this.muteExtension,
            attenuationDb:   this.attenuationDb,
            plSensitivity:   this.plSensitivity,
            plMuteExtension: this.plMuteExtension,
        });

        return buildWav(processed, sampleRate);
    }

    _processViaFfmpeg(buf, audioType) {
        const ext     = _ext(audioType);
        const ts      = Date.now();
        const inFile  = path.join(os.tmpdir(), `squelch-mdc-in-${ts}${ext}`);
        const wavFile = path.join(os.tmpdir(), `squelch-mdc-wav-${ts}.wav`);
        const procFile= path.join(os.tmpdir(), `squelch-mdc-proc-${ts}.wav`);
        const outFile = path.join(os.tmpdir(), `squelch-mdc-out-${ts}${ext}`);
        const rm = (...f) => { for (const x of f) try { fs.unlinkSync(x); } catch (_) {} };

        return new Promise((resolve) => {
            try { fs.writeFileSync(inFile, buf); } catch { resolve(buf); return; }

            const decode = spawn('ffmpeg', [
                '-y', '-i', inFile, '-ac', '1', '-ar', '22050', '-sample_fmt', 's16', wavFile,
            ], { stdio: 'ignore' });

            decode.on('error', () => { rm(inFile, wavFile); resolve(buf); });
            decode.on('exit', (code) => {
                rm(inFile);
                if (code !== 0) { rm(wavFile); resolve(buf); return; }

                let wavBuf;
                try { wavBuf = fs.readFileSync(wavFile); } catch { rm(wavFile); resolve(buf); return; }
                rm(wavFile);

                let processedWav;
                try {
                    processedWav = this._processWav(wavBuf);
                } catch (err) {
                    this.log.error(`Processing error: ${err.message}`);
                    resolve(buf);
                    return;
                }

                try { fs.writeFileSync(procFile, processedWav); } catch { resolve(buf); return; }

                const encode = spawn('ffmpeg', ['-y', '-i', procFile, outFile], { stdio: 'ignore' });
                encode.on('error', () => { rm(procFile, outFile); resolve(buf); });
                encode.on('exit', (code2) => {
                    rm(procFile);
                    if (code2 === 0 && fs.existsSync(outFile)) {
                        try {
                            const result = fs.readFileSync(outFile);
                            rm(outFile);
                            resolve(result);
                        } catch { rm(outFile); resolve(buf); }
                    } else {
                        rm(outFile);
                        resolve(buf);
                    }
                });
            });
        });
    }
}

export default MuteMdcPlugin;
