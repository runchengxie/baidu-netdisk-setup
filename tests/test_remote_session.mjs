import test from 'node:test';
import assert from 'node:assert/strict';
import { SessionRelay } from '../scripts/session-relay.mjs';

test('rotation waits for a running write, reinitializes, and never replays it', () => {
  const sent = [], output = [], starts = [];
  const relay = new SessionRelay({ send: m => sent.push(m), emit: m => output.push(m), restart: () => starts.push(1) });
  relay.fromHost({jsonrpc:'2.0', id:1, method:'initialize', params:{protocolVersion:'2024-11-05', capabilities:{}, clientInfo:{name:'test',version:'1'}}});
  relay.fromRemote({jsonrpc:'2.0', id:1, result:{capabilities:{tools:{}}}});
  relay.fromHost({jsonrpc:'2.0', method:'notifications/initialized'});
  relay.fromHost({jsonrpc:'2.0', id:2, method:'tools/call', params:{name:'file_move'}});
  relay.rotate();
  relay.fromHost({jsonrpc:'2.0', id:3, method:'tools/list'});
  assert.equal(starts.length, 0);
  relay.fromRemote({jsonrpc:'2.0', id:2, result:{content:[]}});
  assert.equal(starts.length, 1);
  relay.connected();
  const init = sent.at(-1);
  assert.equal(init.method, 'initialize');
  relay.fromRemote({jsonrpc:'2.0', id:init.id, result:{capabilities:{tools:{}}}});
  assert.equal(sent.at(-1).id, 3);
  assert.equal(sent.filter(m => m.method === 'tools/call').length, 1);
  assert.equal(output.filter(m => m.id === 2).length, 1);
  assert.equal(output.some(m => m.id === init.id), false);
});

test('cancellation is sent while waiting for a rotation', () => {
  const sent=[];
  const relay=new SessionRelay({send:m=>sent.push(m),emit:()=>{},restart:()=>{}});
  relay.fromHost({jsonrpc:'2.0',id:1,method:'tools/call'});
  relay.rotate();
  relay.fromHost({jsonrpc:'2.0',method:'notifications/cancelled',params:{requestId:1}});
  assert.equal(sent.at(-1).method,'notifications/cancelled');
});

test('a background credential check pauses requests until it finishes', () => {
  const sent=[];
  const relay=new SessionRelay({send:m=>sent.push(m),emit:()=>{},restart:()=>{}});
  assert.equal(relay.pause(),true);
  relay.fromHost({jsonrpc:'2.0',id:1,method:'tools/list'});
  assert.equal(sent.length,0);
  relay.resume();
  assert.equal(sent[0].id,1);
  assert.equal(relay.pause(),false);
});
