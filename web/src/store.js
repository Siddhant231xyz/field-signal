import { computed, reactive, readonly } from 'vue'

/* All derivation happens in Python. This holds what the API returned and
   indexes it for lookup — it never decides anything. */

const state = reactive({
  loading: true,
  error: null,
  current: 0,
  ledger: { people: [], sources: [], claims: [] },
  revisions: {},
  created: null,
  busy: false,
  /* Ingestion state lives here, not in AgentView. The view is destroyed when
     you switch sheets, and a run takes minutes — losing the file list and the
     progress on navigation is the bug this fixes. */
  picked: [],
  progress: { phase: 'idle', running: false, shell_calls: 0, files: 0 },
  lastRun: null,
  fixtures: [],
  verify: null,
  moves: null,
  chat: {
    threads: {},
    pending: {},
    errors: {},
  },
})

async function call(path, options) {
  const res = await fetch(path, options)
  const body = await res.json()
  if (!res.ok) throw new Error(body.error || `request failed: ${res.status}`)
  return body
}

function apply(payload) {
  state.current = payload.current
  state.ledger = payload.ledger
  state.revisions = payload.revisions
  state.ledgers = payload.ledgers
  state.created = payload.created ?? null
}

function chatThread(revision) {
  const key = String(revision)
  if (!state.chat.threads[key]) state.chat.threads[key] = []
  return state.chat.threads[key]
}

async function pollProgress() {
  try {
    const p = await call('/api/agent/status')
    state.progress = p
    if (p.running) state.busy = true
    return p
  } catch {
    return null // a poll failure must never take down the page
  }
}

export const store = readonly(state)

export const view = computed(() => state.revisions[String(state.current)] ?? null)

export const claims = computed(() =>
  Object.fromEntries(state.ledger.claims.map((c) => [c.id, c])),
)
export const sources = computed(() =>
  Object.fromEntries(state.ledger.sources.map((s) => [s.id, s])),
)
export const conditions = computed(() =>
  Object.fromEntries((view.value?.conditions ?? []).map((c) => [c.id, c])),
)

export const revisionNumbers = computed(() =>
  Object.keys(state.revisions)
    .map(Number)
    .sort((a, b) => a - b),
)

export const actions = {
  async boot() {
    state.loading = true
    state.error = null
    try {
      apply(await call('/api/state'))
      state.fixtures = await call('/api/fixtures')
      await pollProgress() // a run may already be going when the page loads
    } catch (e) {
      state.error = e.message
    } finally {
      state.loading = false
    }
  },

  async loadFixture(path) {
    state.error = null
    state.busy = true
    const before = state.current
    try {
      apply(await call('/api/load', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path }),
      }))
      state.moves = await call(`/api/diff?a=${before}&b=${state.current}`)
    } catch (e) {
      state.error = e.message
    } finally {
      state.busy = false
    }
  },

  pick(files) {
    const seen = new Set(state.picked.map((f) => f.name + f.size))
    for (const f of files) if (!seen.has(f.name + f.size)) state.picked.push(f)
  },

  unpick(i) {
    state.picked.splice(i, 1)
  },

  clearPicked() {
    state.picked = []
  },

  /* Uploads go to the agent, which reads them inside a container and writes a
     new revision branched off whichever one is selected. */
  async ingest() {
    if (!state.picked.length || state.busy) return false
    state.error = null
    state.busy = true
    state.lastRun = null
    const before = state.current
    const form = new FormData()
    for (const file of state.picked) form.append('files', file, file.name)

    const poll = setInterval(pollProgress, 1200)
    try {
      apply(await call('/api/agent', { method: 'POST', body: form }))
      state.moves = await call(`/api/diff?a=${before}&b=${state.current}`)
      state.lastRun = { base: before, revision: state.current, ok: true }
      state.picked = []
      return true
    } catch (e) {
      state.error = e.message
      state.lastRun = { base: before, ok: false, error: e.message }
      return false
    } finally {
      clearInterval(poll)
      state.busy = false
      await pollProgress()
    }
  },

  /* Called on boot and whenever the agent sheet mounts, so a run started in
     another tab — or before a reload — is still visible. */
  refreshProgress: pollProgress,

  async select(n) {
    state.error = null
    try {
      apply(await call('/api/select', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ revision: n }),
      }))
    } catch (e) {
      state.error = e.message
    }
  },

  async diff(a, b) {
    state.error = null
    try {
      state.moves = await call(`/api/diff?a=${a}&b=${b}`)
    } catch (e) {
      state.error = e.message
    }
  },

  async runVerify() {
    state.error = null
    try {
      state.verify = await call('/api/verify')
    } catch (e) {
      state.error = e.message
    }
  },

  async askGraph(question) {
    const content = String(question ?? '').trim()
    const revision = state.current
    const key = String(revision)
    if (!content || state.chat.pending[key]) return false
    const thread = chatThread(revision)
    const history = thread.slice(-12).map((message) => ({
      role: message.role,
      content: message.content,
    }))
    thread.push({ role: 'user', content, revision })
    state.chat.pending[key] = true
    state.chat.errors[key] = null
    try {
      const result = await call('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ revision, question: content, history }),
      })
      thread.push({
        role: 'assistant',
        content: result.answer,
        revision: result.revision,
        citations: result.citations ?? [],
        conditions: result.conditions ?? [],
        caveat: result.caveat ?? null,
      })
      return true
    } catch (e) {
      state.chat.errors[key] = e.message
      return false
    } finally {
      state.chat.pending[key] = false
    }
  },

  clearChat(revision = state.current) {
    const key = String(revision)
    state.chat.threads[key] = []
    state.chat.errors[key] = null
  },


}
