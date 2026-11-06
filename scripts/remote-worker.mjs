import { readFileSync } from 'node:fs';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { join } from 'node:path';
import { loadPlatformSettings, helperSync } from './platform-config.mjs';

const here = fileURLToPath(new URL('.', import.meta.url));
try {
  const settings = loadPlatformSettings(here);
  const tokenFile = settings.tokenFile;
  const token = helperSync(settings, here, 'token');
  if (!token) throw new Error('Empty credential');
  const safe = value => String(value).replaceAll(token, '[REDACTED]')
    .replace(/access_token=[^\s&"'<>\\]+/gi, 'access_token=[REDACTED]');
  // Bridge diagnostics are untrusted: redact before writing to either stream.
  for (const stream of [process.stderr, process.stdout]) {
    const write = stream.write.bind(stream);
    stream.write = (chunk, ...args) => write(safe(Buffer.isBuffer(chunk) ? chunk.toString('utf8') : chunk), ...args);
  }
  const metadata = JSON.parse(readFileSync(tokenFile, 'utf8').replace(/^\uFEFF/, ''));
  if (metadata.saved_at_utc && metadata.expires_in &&
      Date.parse(metadata.saved_at_utc) + Number(metadata.expires_in) * 1000 - Date.now() < 7 * 86400000) {
    console.error('Baidu authorization expires within 7 days. Reauthorize soon.');
  }
  process.argv = [process.execPath, settings.bridge, `https://mcp-pan.baidu.com/sse?access_token=${encodeURIComponent(token)}`,
    '--transport', 'sse-only', '--silent'];
  await import(pathToFileURL(settings.bridge).href);
} catch {
  console.error('Baidu MCP could not start. Check installation and authorization; reauthorize if expired.');
  process.exitCode = 1;
}
