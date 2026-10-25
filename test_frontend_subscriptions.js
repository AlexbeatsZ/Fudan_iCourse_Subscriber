// node test_frontend_subscriptions.js
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

async function main() {
  const calls = [];
  const responses = [];
  const context = {
    window: {}, location: { hostname: 'friend.github.io', pathname: '/repo/' },
    atob, btoa,
    fetch: async (url, options) => {
      calls.push({ url, options });
      const result = responses.shift();
      assert.ok(result, 'unexpected fetch');
      return result;
    },
  };
  vm.runInNewContext(fs.readFileSync('frontend/js/github.js', 'utf8'), context);
  const github = context.window.ICS.github;

  const current = JSON.stringify({ course_ids: ['123', '456'] });
  responses.push({
    ok: true, status: 200,
    json: async () => ({ encoding: 'base64', content: btoa(current), sha: 'oldsha' }),
  });
  const list = await github.getSubscriptions('Friend', 'Repo', 'test-token');
  assert.equal(JSON.stringify(list), JSON.stringify({ ids: ['123', '456'], sha: 'oldsha' }));
  assert.match(calls[0].url, /repos\/Friend\/Repo\/contents\/data\/subscriptions\.json\?ref=data/);

  responses.push({
    ok: true, status: 200,
    json: async () => ({ content: { sha: 'newsha' } }),
  });
  const saved = await github.saveSubscriptions('Friend', 'Repo', 'test-token', ['123', '789'], 'oldsha');
  assert.equal(JSON.stringify(saved), JSON.stringify({ ids: ['123', '789'], sha: 'newsha' }));
  const payload = JSON.parse(calls[1].options.body);
  assert.equal(payload.branch, 'data');
  assert.equal(payload.sha, 'oldsha');
  assert.deepEqual(JSON.parse(atob(payload.content)), { course_ids: ['123', '789'] });

  responses.push({ ok: false, status: 409 });
  await assert.rejects(github.saveSubscriptions('Friend', 'Repo', 'test-token', ['123'], 'stale'),
                       /刷新页面/);
  console.log('Frontend subscription API tests passed.');
}

main().catch((error) => { console.error(error); process.exitCode = 1; });
