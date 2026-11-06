// Dispatch only on the explicitly installed backend; no credential inference.
import { readFileSync } from 'node:fs';
import { execFile, execFileSync } from 'node:child_process';
import { join } from 'node:path';
import { promisify } from 'node:util';
const execute = promisify(execFile);

export function helperCommand(settings, here, command) {
  if (settings.platform === 'linux') {
    return [settings.python, [join(here, 'credential-helper.py'), '--settings', join(here, 'settings.json'), command]];
  }
  const scripts = { settings: 'load-settings.ps1', ensure: 'ensure-authorization.ps1', token: 'read-credential.ps1', status: 'read-credential.ps1' };
  if (!scripts[command]) throw new Error('Unknown helper operation');
  const args = ['-NoProfile', '-NonInteractive', '-File', join(here, scripts[command])];
  if (command === 'token' || command === 'status') args.push('-TokenFile', settings.tokenFile, '-Mode', command === 'token' ? 'token' : 'status');
  return [settings.powershell, args];
}

export function helperSync(settings, here, command) {
  const [program, args] = helperCommand(settings, here, command);
  return execFileSync(program, args, { encoding: 'utf8', windowsHide: true,
    stdio: ['ignore', 'pipe', 'pipe'], timeout: command === 'ensure' ? 95000 : 15000 }).trim();
}

export async function helperAsync(settings, here, command) {
  const [program, args] = helperCommand(settings, here, command);
  const { stdout } = await execute(program, args, { encoding: 'utf8', windowsHide: true, timeout: 95000 });
  return stdout.trim();
}

export function loadPlatformSettings(here) {
  const base = JSON.parse(readFileSync(join(here, 'settings.json'), 'utf8').replace(/^\uFEFF/, ''));
  return JSON.parse(helperSync(base, here, 'settings'));
}

export function authorizationUsable(state, now = Date.now()) {
  const expiration = Date.parse(state.expiresAtUtc);
  return ['valid', 'expiring'].includes(state.status) && Number.isFinite(expiration) && expiration > now;
}

export function assertForwardAuthorization(observed, current, now = Date.now()) {
  if (!authorizationUsable(observed, now) || observed.revision !== current.revision) {
    throw new Error('Authorization changed or expired; restart or reauthorize');
  }
}
