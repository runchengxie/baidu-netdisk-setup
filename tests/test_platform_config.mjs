import test from 'node:test';
import assert from 'node:assert/strict';
import { helperCommand, authorizationUsable } from '../scripts/platform-config.mjs';

test('Linux dispatch uses Python without Windows arguments or credentials', () => {
  const settings = { platform:'linux', python:'/runtime/python', tokenFile:'/private/token.json' };
  const [program, args] = helperCommand(settings, '/private', 'token');
  assert.equal(program, '/runtime/python');
  assert.deepEqual(args, ['/private/credential-helper.py','--settings','/private/settings.json','token']);
});
test('Windows dispatch retains its explicit token helper', () => {
  const [program, args] = helperCommand({ powershell:'pwsh',tokenFile:'C:/private/token.json' }, 'C:/private', 'token');
  assert.equal(program,'pwsh');
  assert.deepEqual(args.slice(-4),['-TokenFile','C:/private/token.json','-Mode','token']);
});
test('Requests stop at actual expiration, including malformed metadata', () => {
  const state={status:'valid',expiresAtUtc:'2026-11-06T15:00:00Z'};
  assert.equal(authorizationUsable(state,Date.parse('2026-11-06T14:59:59Z')),true);
  assert.equal(authorizationUsable(state,Date.parse('2026-11-06T15:00:00Z')),false);
  assert.equal(authorizationUsable({status:'valid'}),false);
  assert.equal(authorizationUsable({...state,status:'unknown'},0),false);
});

test('queued calls are rechecked when the relay flushes after expiration', async () => {
  const { SessionRelay } = await import('../scripts/session-relay.mjs');
  const { assertForwardAuthorization } = await import('../scripts/platform-config.mjs');
  let now = Date.parse('2026-11-06T14:59:59Z');
  const state={status:'valid',expiresAtUtc:'2026-11-06T15:00:00Z',revision:'same'};
  const sent=[];
  const relay=new SessionRelay({send:message=>{
    assertForwardAuthorization(state,state,now); sent.push(message);
  },emit:()=>{},restart:()=>{}});
  assert.equal(relay.pause(),true);
  relay.fromHost({jsonrpc:'2.0',id:1,method:'tools/call'});
  now=Date.parse('2026-11-06T15:00:01Z');
  assert.throws(()=>relay.resume(),/expired/);
  assert.equal(sent.length,0);
});
