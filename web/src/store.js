import { computed, reactive, readonly } from 'vue'

/* All derivation happens in Python. This holds what the API returned and
   indexes it for lookup — it never decides anything. */

const state = reactive({
  loading: true,
  error: null,
  current: 0,
  loaded: [],
  ledger: { people: [], sources: [], claims: [] },
  revisions: {},
  fixtures: [],
  verify: null,
  moves: null,
})

async function call(path, options) {
  const res = await fetch(path, options)
  const body = await res.json()
  if (!res.ok) throw new Error(body.error || `request failed: ${res.status}`)
  return body
}

function apply(payload) {
  state.current = payload.current
  state.loaded = payload.loaded
  state.ledger = payload.ledger
  state.revisions = payload.revisions
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
    } catch (e) {
      state.error = e.message
    } finally {
      state.loading = false
    }
  },

  async loadFixture(path) {
    state.error = null
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
    }
  },

  async reset() {
    state.error = null
    try {
      apply(await call('/api/reset', { method: 'POST' }))
      state.moves = null
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

  showRevision(n) {
    state.current = n
  },
}
