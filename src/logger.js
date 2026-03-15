import fs      from 'fs';
import path    from 'path';
import winston from 'winston';

const { combine, colorize, timestamp, printf } = winston.format;

const isTTY = !!process.stderr.isTTY;

const fmt = printf(({ level, message, timestamp: ts, label }) => {
    const time = isTTY ? `\x1b[2m${ts}\x1b[0m` : ts;
    const tag  = label ? (isTTY ? ` \x1b[36m[${label}]\x1b[0m` : ` [${label}]`) : '';
    return `${time}${tag} ${level}: ${message}`;
});

const fileFmt = printf(({ level, message, timestamp: ts, label }) => {
    const tag = label ? ` [${label}]` : '';
    return `${ts}${tag} ${level}: ${message}`;
});

const logger = winston.createLogger({
    level: process.env.LOG_LEVEL || 'info',
    format: isTTY
        ? combine(colorize({ level: true }), timestamp({ format: 'HH:mm:ss' }), fmt)
        : combine(timestamp({ format: 'HH:mm:ss' }), fmt),
    transports: [
        new winston.transports.Console({ stream: process.stderr }),
    ],
});

function addFileTransport(dir) {
    const logDir = dir ? path.resolve(dir) : process.cwd();
    fs.mkdirSync(logDir, { recursive: true });

    const now = new Date();
    const pad = (n) => String(n).padStart(2, '0');
    const name = [
        now.getFullYear(),
        pad(now.getMonth() + 1),
        pad(now.getDate()),
        pad(now.getHours()),
        pad(now.getMinutes()),
        pad(now.getSeconds()),
    ].join('-') + '.log';

    const filePath = path.join(logDir, name);
    logger.add(new winston.transports.File({
        filename: filePath,
        format:   combine(timestamp({ format: 'HH:mm:ss' }), fileFmt),
    }));
    logger.info(`Log file: ${filePath}`);
}

export default logger;
export { addFileTransport };
