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
  } else if (path === '/api/chat/stream') {
    // Server-sent events, delivered in two reads so the split-frame handling
    // in the store is exercised rather than assumed.
    const request = JSON.parse(options.body)
    const answer = `Answer from v${request.revision}`
    const done = JSON.stringify({
      revision: request.revision, answer, citations: [], caveat: null,
    })
    const frames = [
      `event: delta\ndata: ${JSON.stringify({ text: answer.slice(0, 6) })}\n\nevent: del`,
      `ta\ndata: ${JSON.stringify({ text: answer.slice(6) })}\n\nevent: done\ndata: ${done}\n\n`,
    ]
    const encoder = new TextEncoder()
    let i = 0
    return {
      ok: true,
      body: {
        getReader: () => ({
          read: async () =>
            i < frames.length
              ? { done: false, value: encoder.encode(frames[i++]) }
              : { done: true, value: undefined },
        }),
      },
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
    .filter((request) => request.path === '/api/chat/stream')
    .map((request) => JSON.parse(request.options.body))

  assert.deepEqual(calls.map((call) => call.revision), [2, 1])
  assert.equal(store.chat.threads['2'][1].content, 'Answer from v2')
  assert.equal(store.chat.threads['1'][1].content, 'Answer from v1')
  assert.equal(store.chat.threads['1'][0].revision, 1)
})

test('an unreachable server keeps the question instead of losing it', async () => {
  const realFetch = globalThis.fetch
  globalThis.fetch = async (path, options) => {
    if (path === '/api/chat/stream') throw new TypeError('Failed to fetch')
    return realFetch(path, options)
  }
  try {
    const before = store.chat.threads['1'].length
    const ok = await actions.askGraph('will this survive?')
    assert.equal(ok, false)
    assert.match(store.chat.errors['1'], /Cannot reach the Field Signal server/)
    assert.equal(store.chat.retry, 'will this survive?')
    // the question stays, the empty reply does not
    assert.equal(store.chat.threads['1'].length, before + 1)
    assert.equal(store.chat.threads['1'].at(-1).role, 'user')
  } finally {
    globalThis.fetch = realFetch
  }
})

test('a stalled model gives up and keeps the question', async () => {
  const realFetch = globalThis.fetch
  globalThis.fetch = async () => {
    const err = new Error('aborted')
    err.name = 'AbortError'
    throw err
  }
  try {
    const ok = await actions.askGraph('does this stall?')
    assert.equal(ok, false)
    assert.match(store.chat.errors['1'], /did not answer within two minutes/)
    assert.equal(store.chat.retry, 'does this stall?')
  } finally {
    globalThis.fetch = realFetch
  }
})
