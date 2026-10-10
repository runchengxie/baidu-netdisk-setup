import { readFileSync } from 'node:fs';
import { execFile, execFileSync, spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { join } from 'node:path';
import { createInterface } from 'node:readline';
import { promisify } from 'node:util';
import { SessionRelay } from './session-relay.mjs';

const here=fileURLToPath(new URL('.',import.meta.url));
const execute=promisify(execFile);
let worker, stopping=false, timer, reconnectTimeout, polling=false;
const safe=value=>String(value).replace(/access_token=[^\s&"'<>\\]+/gi,'access_token=[REDACTED]')
  .replace(/Bearer\s+[^\s"']+/gi,'Bearer [REDACTED]');
function stop(code=0) {
  if (stopping) return;
  stopping=true; clearInterval(timer); clearTimeout(reconnectTimeout); worker?.kill(); process.exitCode=code;
  process.stdin.destroy();
}
try {
  const base=JSON.parse(readFileSync(join(here,'settings.json'),'utf8').replace(/^\uFEFF/,''));
  const settings=JSON.parse(execFileSync(base.powershell,['-NoProfile','-NonInteractive','-File',join(here,'load-settings.ps1')],
    {encoding:'utf8',windowsHide:true,stdio:['ignore','pipe','pipe'],timeout:15000}));
  async function ensure() {
    const {stdout}=await execute(settings.powershell,['-NoProfile','-NonInteractive','-File',join(here,'ensure-authorization.ps1')],
      {encoding:'utf8',windowsHide:true,timeout:95000});
    const result=JSON.parse(stdout);
    if (['expired','unknown'].includes(result.status)) {
      const error=new Error('Unusable authorization'); error.code='authorization_expired'; throw error;
    }
    if (['failed','unavailable'].includes(result.refreshAction)) {
      console.error(`Baidu refresh unavailable (${result.refreshFailure}); current authorization remains in use while valid.`);
    }
    return result;
  }
  let current=await ensure();
  let revision=current.revision;
  let nextCheck=Date.now()+(['failed','unavailable'].includes(current.refreshAction)?3600000:86400000);
  function emit(message) { process.stdout.write(safe(JSON.stringify(message))+'\n'); }
  const relay=new SessionRelay({send:message=>{
    if (!worker?.stdin.writable) throw new Error('Connection unavailable');
    worker.stdin.write(JSON.stringify(message)+'\n');
  },emit,restart:()=>{
    worker?.kill(); startWorker();
    reconnectTimeout=setTimeout(()=>{
      console.error('Baidu MCP reconnection timed out; restart the MCP.'); stop(1);
    },95000);
  }});
  function startWorker() {
    const child=spawn(process.execPath,[join(here,'remote-worker.mjs')],{windowsHide:true,stdio:['pipe','pipe','pipe']});
    worker=child;
    const lines=createInterface({input:child.stdout});
    lines.on('line',line=>{
      if (child !== worker || stopping) return;
      try {
        relay.fromRemote(JSON.parse(line));
        if (relay.phase==='running') clearTimeout(reconnectTimeout);
      }
      catch { console.error('Baidu MCP connection protocol failed; restart the MCP.'); stop(1); }
    });
    child.stderr.on('data',data=>process.stderr.write(safe(data.toString('utf8'))));
    child.on('error',()=>{if(child===worker){console.error('Baidu MCP worker failed to start.');stop(1);}});
    child.on('exit',code=>{if(child===worker && !stopping){console.error('Baidu MCP connection ended; restart the MCP.');stop(code||1);}});
    child.stdin.on('error',()=>{if(child===worker && !stopping) stop(1);});
    relay.connected();
  }
  startWorker();
  const input=createInterface({input:process.stdin});
  input.on('line',line=>{
    try {relay.fromHost(JSON.parse(line));}
    catch { console.error('Baidu MCP request protocol failed.'); stop(1); }
  });
  input.on('close',()=>stop());
  for (const signal of ['SIGINT','SIGTERM']) process.on(signal,()=>stop());
  // File changes from the other MCP are adopted at the next minute poll.
  timer=setInterval(async()=>{
    if (polling || stopping) return;
    let saved;
    try {saved=JSON.parse(readFileSync(settings.tokenFile,'utf8').replace(/^\uFEFF/,''));}
    catch {return;}
    const changed=Date.parse(saved.saved_at_utc)!==Date.parse(revision);
    if (!changed && Date.now()<nextCheck) return;
    if (!relay.pause()) return;
    polling=true;
    try {
      current=await ensure();
      if (stopping) return;
      nextCheck=Date.now()+(['failed','unavailable'].includes(current.refreshAction)?3600000:86400000);
      if (current.revision!==revision) {
        revision=current.revision; relay.rotate();
        console.error('Baidu authorization updated; reconnecting the remote MCP.');
      } else relay.resume();
    } catch (error) {
      if (stopping) return;
      console.error('Baidu authorization check failed; restart or reauthorize if expired.');
      if (error.code==='authorization_expired') stop(1);
      else {nextCheck=Date.now()+3600000; relay.resume();}
    } finally {polling=false;}
  },60000);
} catch {
  console.error('Baidu MCP could not start. Check installation, refresh configuration and authorization.');
  stop(1);
}
