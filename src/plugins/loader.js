import path from 'path';
import { pathToFileURL } from 'url';
import { buildMonitorMap, isMonitored } from '../config.js';
import rootLogger from '../logger.js';

const log = rootLogger.child({ label: 'plugin' });

/**
 * PluginManager — loads and dispatches events to plugins.
 *
 * Plugin lifecycle methods (all optional):
 *
 *   init(config, controller, logger)
 *   onState(controller)
 *   onCallStart(call)
 *   onCallEnd()
 *   onStatus(connected)
 *   onConfig(systems)
 *   onSearchResults(results)
 *   processAudio(buf, type, call)
 *   destroy()
 */
class PluginManager {
    constructor() {
        this._plugins      = [];
        this._callActiveSet = new Set();
    }

    async load(entry) {
        const pluginPath = typeof entry === 'string' ? entry : entry.path;

        if (typeof entry === 'object' && entry.enabled === false) {
            log.debug(`Skipped (disabled): ${pluginPath}`);
            return null;
        }

        const monitorMap = (typeof entry === 'object' && entry.monitor)
            ? buildMonitorMap(entry.monitor)
            : null;

        return this._loadPath(pluginPath, monitorMap);
    }

    async loadBuiltin(pluginPath) {
        return this._loadPath(pluginPath, null, true);
    }

    async _loadPath(pluginPath, monitorMap, prepend = false) {
        const resolved = path.resolve(pluginPath);
        try {
            const mod      = await import(pathToFileURL(resolved).href);
            const exported = mod.default ?? mod;
            const instance = typeof exported === 'function' ? new exported() : exported;
            const entry    = { instance, monitorMap };
            if (prepend) this._plugins.unshift(entry);
            else         this._plugins.push(entry);
            log.info(`Loaded: ${resolved}`);
            return instance;
        } catch (err) {
            log.error(`Failed to load ${pluginPath}: ${err.message}`);
            return null;
        }
    }

    emit(event, ...args) {
        if (event === 'onCallStart') {
            const call = args[0];
            this._callActiveSet.clear();
            for (const { instance, monitorMap } of this._plugins) {
                if (!isMonitored(monitorMap, call.systemId, call.talkgroupId)) continue;
                this._callActiveSet.add(instance);
                try {
                    if (typeof instance.onCallStart === 'function') instance.onCallStart(call);
                } catch (err) {
                    log.error(`Error in onCallStart: ${err.message}`);
                }
            }
        } else if (event === 'onCallEnd') {
            for (const { instance } of this._plugins) {
                if (!this._callActiveSet.has(instance)) continue;
                try {
                    if (typeof instance.onCallEnd === 'function') instance.onCallEnd();
                } catch (err) {
                    log.error(`Error in onCallEnd: ${err.message}`);
                }
            }
            this._callActiveSet.clear();
        } else {
            for (const { instance } of this._plugins) {
                try {
                    if (typeof instance[event] === 'function') {
                        const callArgs = event === 'init' ? [...args, rootLogger] : args;
                        instance[event](...callArgs);
                    }
                } catch (err) {
                    log.error(`Error in ${event}: ${err.message}`);
                }
            }
        }
    }

    runAudioPipeline(buf, audioType, call, done) {
        const processors = this._plugins.filter(({ instance, monitorMap }) =>
            typeof instance.processAudio === 'function' &&
            isMonitored(monitorMap, call.systemId, call.talkgroupId)
        );
        if (processors.length === 0 || !buf) { done(buf); return; }

        let idx = 0;
        const next = (current) => {
            if (idx >= processors.length) { done(current); return; }
            const { instance } = processors[idx++];
            try {
                const result = instance.processAudio(current, audioType, call);
                if (result && typeof result.then === 'function') {
                    result
                        .then(newBuf => next(newBuf ?? current))
                        .catch(err  => { log.error(`processAudio error: ${err.message}`); next(current); });
                } else {
                    next(result ?? current);
                }
            } catch (err) {
                log.error(`processAudio error: ${err.message}`);
                next(current);
            }
        };
        next(buf);
    }

    destroy() {
        this.emit('destroy');
        this._plugins = [];
        this._callActiveSet.clear();
    }

    get count() { return this._plugins.length; }
}

export { PluginManager };
