// Verdent fork build: a plain esbuild bundle -> dist/worker.js.
// BPB v5's self-rebuilding panel machinery (terser-minified HTML assets,
// terser + base64 embedding of the script itself) was removed with the
// customer-facing panel (Document 1, "BPB Fork Scope" #6). The output is a
// standard ESM worker suitable for `wrangler deploy` (wrangler also bundles
// directly from src/worker.ts — this bundle exists for review and for
// API-based script upload without wrangler).

import { writeFileSync, mkdirSync } from 'fs';
import { join, dirname as pathDirname } from 'path';
import { fileURLToPath } from 'url';
import { build } from 'esbuild';
import pkg from '../package.json' with { type: 'json' };

const __filename = fileURLToPath(import.meta.url);
const __dirname = pathDirname(__filename);

const DIST_PATH = join(__dirname, '../dist/');

const green = '\x1b[32m';
const red = '\x1b[31m';
const reset = '\x1b[0m';

const success = `${green}\u2714${reset}`;
const failure = `${red}\u2717${reset}`;

async function buildWorker() {
    const code = await build({
        entryPoints: [join(__dirname, '../src/worker.ts')],
        bundle: true,
        format: 'esm',
        write: false,
        external: [
            'cloudflare:sockets',
            'node:crypto'
        ],
        platform: 'browser',
        target: 'esnext',
        loader: { '.ts': 'ts', '.html': 'text' }
    });

    mkdirSync(DIST_PATH, { recursive: true });
    writeFileSync('./dist/worker.js', code.outputFiles[0].text, 'utf8');

    console.log(`${success} Verdent Node built -> dist/worker.js (v${pkg.version})`);
}

buildWorker().catch(err => {
    console.error(`${failure} Build failed:`, err);
    process.exit(1);
});
