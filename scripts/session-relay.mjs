import { randomUUID } from 'node:crypto';

// Keep the host's stdio session while replacing the authenticated SSE worker.
export class SessionRelay {
  constructor({send, emit, restart}) {
    Object.assign(this, {send, emit, restart});
    this.pending = new Set(); this.queue = []; this.phase = 'running';
    this.initialized = false;
  }
  fromHost(message) {
    if (message.method === 'initialize') this.initialize = message;
    if (message.method === 'notifications/initialized') this.initialized = true;
    // Cancellation of an already-running request must reach the old worker.
    if (this.phase === 'draining' && message.method === 'notifications/cancelled' &&
        this.pending.has(message.params?.requestId)) { this.send(message); return; }
    if (this.phase !== 'running') {
      if (this.queue.length >= 128) {
        if ('id' in message) this.emit({jsonrpc:'2.0',id:message.id,error:{code:-32000,message:'Authorization connection update is busy; retry after it finishes.'}});
      } else this.queue.push(message);
      return;
    }
    if ('id' in message && message.method) this.pending.add(message.id);
    this.send(message);
  }
  fromRemote(message) {
    if (this.phase === 'connecting' && message.id === this.handshakeId) {
      if (message.error) throw new Error('Replacement connection initialization failed');
      if (this.initialized) this.send({jsonrpc:'2.0',method:'notifications/initialized'});
      this.phase = 'running';
      const queued = this.queue; this.queue = [];
      for (const entry of queued) this.fromHost(entry);
      return;
    }
    if ('id' in message && !message.method) this.pending.delete(message.id);
    this.emit(message);
    this.maybeRestart();
  }
  pause() {
    if (this.phase !== 'running' || this.pending.size) return false;
    this.phase='checking'; return true;
  }
  resume() {
    if (this.phase !== 'checking') return;
    this.phase='running'; const queued=this.queue; this.queue=[];
    for (const entry of queued) this.fromHost(entry);
  }
  rotate() { if (['running','checking'].includes(this.phase)) this.phase = 'draining'; this.maybeRestart(); }
  maybeRestart() {
    if (this.phase !== 'draining' || this.pending.size) return;
    this.phase = 'connecting'; this.restart();
  }
  connected() {
    if (this.phase !== 'connecting') return;
    if (this.initialize) {
      this.handshakeId = `baidu-refresh-${randomUUID()}`;
      this.send({...this.initialize, id:this.handshakeId});
    } else {
      this.phase='running'; const queued=this.queue; this.queue=[];
      for (const entry of queued) this.fromHost(entry);
    }
  }
}
