import assert from 'node:assert/strict'
import test from 'node:test'

const requests = []
const base = {
  current: 2,
  revisions: {
    1: { conditions: [], queues: [] },
    2: { conditions: [], queues: [] },
  },
  ledger: { people: [], sources: [], claims: [] },
  ledgers: {
    1: { people: [], sources: [], claims: [] },
    2: { people: [], sources: [], claims: [] },
  },
}

globalThis.fetch = async (path, options = {}) => {
  requests.push({ path, options })
  let body
  if (path === '/api/state') body = base
  else if (path === '/api/fixtures') body = []
  else if (path === '/api/agent/status') {
    body = { phase: 'idle', running: false, shell_calls: 0, files: 0 }
  } else if (path === '/api/select') {
    const revision = JSON.parse(options.body).revision
    body = { ...base, current: revision, ledger: base.ledgers[revision] }
  } else if (path === '/api/chat') {
    const request = JSON.parse(options.body)
    body = {
      revision: request.revision,
      answer: `Answer from v${request.revision}`,
      citations: [],
      conditions: [],
      caveat: null,
    }
  } else throw new Error(`unexpected request ${path}`)
  return { ok: true, json: async () => body }
}

const { actions, store } = await import('./store.js')

test('chat histories and requests are pinned to their revision', async () => {
  await actions.boot()
  await actions.askGraph('What is blocking?')
  await actions.select(1)
  await actions.askGraph('What was known here?')

  const calls = requests
    .filter((request) => request.path === '/api/chat')
    .map((request) => JSON.parse(request.options.body))

  assert.deepEqual(calls.map((call) => call.revision), [2, 1])
  assert.equal(store.chat.threads['2'][1].content, 'Answer from v2')
  assert.equal(store.chat.threads['1'][1].content, 'Answer from v1')
  assert.equal(store.chat.threads['1'][0].revision, 1)
})
