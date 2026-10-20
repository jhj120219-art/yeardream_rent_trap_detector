import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRentClient } from '../frontend_api_example.mjs';

test('lost save response retries the same key; failed report does not save or analyze again', async () => {
  const calls = [];
  let lostSave = true, lostReport = true;
  const fetchImpl = async (url, options) => {
    const path = url.pathname;
    calls.push({ path, ...options });
    if (path === '/listings' && lostSave) { lostSave = false; throw new Error('network'); }
    if (path.endsWith('/report') && lostReport) { lostReport = false; throw new Error('network'); }
    const body = path === '/sessions' ? {token:'test-session'} : path === '/listings' ? {id:'listing1'} : path.endsWith('/analyses') ? {id:'analysis1'} : path.endsWith('/report') ? {rent:{result:{status:'INSUFFICIENT_DATA'}}} : {};
    return new Response(JSON.stringify(body), {status:200});
  };
  const client = createRentClient({baseUrl:'https://example.com',teamKey:'test-key',fetchImpl});
  await client.start();
  const input = {listing:{rent_10k_krw:70},confirmation:{user_confirmed:true}};
  const task = client.createComparison(input);
  input.listing.rent_10k_krw = 700;
  await assert.rejects(task.run(), /network/);
  await assert.rejects(task.run(), /network/);
  const report = await task.run();
  assert.equal(report.rent.result.status, 'INSUFFICIENT_DATA');
  const saves = calls.filter(x => x.path === '/listings');
  assert.equal(saves.length, 2);
  assert.equal(saves[0].headers['Idempotency-Key'], saves[1].headers['Idempotency-Key']);
  assert.equal(JSON.parse(saves[1].body).listing.rent_10k_krw, 70);
  assert.equal(calls.filter(x => x.path.endsWith('/analyses')).length, 1);
  assert.equal(saves[1].headers.Authorization, 'Bearer test-session');
  assert.equal(saves[1].headers['X-Team-Key'], 'test-key');
});

test('reject unconfirmed input and preserve session on unauthorized error', async () => {
  let sessions = 0;
  const client = createRentClient({baseUrl:'https://example.com',teamKey:'test-key',fetchImpl:async url => {
    if (url.pathname === '/sessions') { sessions++; return Response.json({token:'test-session'}); }
    return Response.json({detail:'denied'}, {status:401});
  }});
  await assert.rejects(client.start(), error => error.status === 401);
  await assert.rejects(client.start(), error => error.status === 401);
  assert.equal(sessions, 1);
  assert.throws(() => client.createComparison({confirmation:{user_confirmed:false}}));
  assert.throws(() => createRentClient({baseUrl:'http://public.example',teamKey:'test-key'}));
});
