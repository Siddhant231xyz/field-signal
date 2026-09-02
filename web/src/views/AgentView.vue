<script setup>
import { computed, ref } from 'vue'
import { actions, store } from '../store'

/* Files in, a new revision out. The reading happens in a container on the
   server; nothing here interprets a document. */

const dropping = ref(false)
const picked = ref([])
const done = ref(null)
const input = ref(null)

const total = computed(() =>
  picked.value.reduce((sum, f) => sum + f.size, 0),
)

function add(list) {
  const incoming = Array.from(list)
  const names = new Set(picked.value.map((f) => f.name + f.size))
  picked.value.push(...incoming.filter((f) => !names.has(f.name + f.size)))
}

function drop(event) {
  dropping.value = false
  add(event.dataTransfer.files)
}

function remove(i) {
  picked.value.splice(i, 1)
}

async function run() {
  done.value = null
  const base = store.current
  if (await actions.ingest(picked.value)) {
    done.value = { base, revision: store.current }
    picked.value = []
    if (input.value) input.value.value = ''
  }
}

function size(bytes) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}
</script>

<template>
  <div class="agent">
    <header class="head">
      <p class="eyebrow">read new documents into the ledger</p>
      <h1 class="head__title">Agent</h1>
      <p class="head__note">
        Add any number of files, of any type. They are read inside a disposable
        container that identifies each format from its contents rather than its
        extension, and the claims it extracts become a
        <strong>new revision branched off v{{ store.current }}</strong> — the one
        you have selected. Nothing you can see now is edited or replaced.
      </p>
    </header>

    <section
      class="drop"
      :class="{ 'drop--over': dropping, 'drop--busy': store.busy }"
      @dragover.prevent="dropping = true"
      @dragleave.prevent="dropping = false"
      @drop.prevent="drop"
    >
      <p class="drop__lead">Drop files here</p>
      <p class="drop__or">or</p>
      <label class="btn btn--primary">
        choose files
        <input
          ref="input"
          type="file"
          multiple
          class="visually-hidden"
          @change="add($event.target.files)"
        />
      </label>
      <p class="drop__hint">
        Transcripts, messages, schedules, quotes, photographs — whatever the
        project produced.
      </p>
    </section>

    <section v-if="picked.length" class="panel block">
      <div class="panel__head">
        <h2 class="panel__title">Ready to read</h2>
        <span class="count">{{ picked.length }} file{{ picked.length === 1 ? '' : 's' }} · {{ size(total) }}</span>
      </div>
      <div class="panel__body">
        <div v-for="(f, i) in picked" :key="f.name + i" class="file">
          <span class="file__name">{{ f.name }}</span>
          <span class="file__size">{{ size(f.size) }}</span>
          <button class="file__x" :disabled="store.busy" aria-label="Remove" @click="remove(i)">×</button>
        </div>

        <div class="actions">
          <button class="btn btn--primary" :disabled="store.busy" @click="run">
            {{ store.busy ? 'reading…' : `read into a new revision off v${store.current}` }}
          </button>
          <button class="btn" :disabled="store.busy" @click="picked = []">clear</button>
        </div>

        <p v-if="store.busy" class="working">
          The container is inspecting each file, installing what it needs to
          parse it, and extracting claims. A full packet takes several minutes.
        </p>
      </div>
    </section>

    <p v-if="store.error" class="failed">
      <strong>Nothing was written.</strong> {{ store.error }}
    </p>

    <section v-if="done" class="panel block done">
      <div class="panel__head">
        <h2 class="panel__title">Revision {{ done.revision }} created from v{{ done.base }}</h2>
      </div>
      <div class="panel__body">
        <p class="reason">
          It is now the selected revision, so every sheet shows it. Open
          <strong>Revisions</strong> to see what moved, or select v{{ done.base }}
          again to go back — nothing was overwritten.
        </p>
      </div>
    </section>

    <section class="panel block">
      <div class="panel__head">
        <h2 class="panel__title">What the agent may and may not do</h2>
      </div>
      <div class="panel__body">
        <ul class="rules">
          <li>Every claim it writes carries the verbatim text it was read from and a locator, so <strong>Verify</strong> can check it against the file.</li>
          <li>Uploads are kept alongside the revision, because a claim whose source has vanished cannot be checked.</li>
          <li>Its output is a model's proposal. It lands in a new revision to be compared, never as an edit to one you have already read.</li>
          <li>Document contents are evidence, never instructions — text in a file asking the agent to change its behaviour is ignored.</li>
          <li>Re-reading the same evidence adds nothing: claims are deduplicated by source, locator and value, not only by id.</li>
        </ul>
        <p class="reason">
          Requires Docker and an <code>OPENAI_API_KEY</code> in
          <code>.env</code>. Without them this reports a failure and writes
          nothing.
        </p>
      </div>
    </section>
  </div>
</template>

<style scoped>
.head {
  padding-bottom: 18px;
  border-bottom: 1px solid var(--line);
  margin-bottom: 18px;
}

.head__title {
  font-size: 34px;
  margin: 4px 0 6px;
}

.head__note {
  margin: 0;
  max-width: 80ch;
  font-size: 13px;
  color: var(--chalk-faint);
}

.head__note strong {
  color: var(--cyan);
  font-weight: 500;
}

.drop {
  border: 2px dashed var(--line);
  padding: 40px 20px;
  text-align: center;
  transition: border-color 0.15s, background 0.15s;
}

.drop--over {
  border-color: var(--cyan);
  background: color-mix(in srgb, var(--cyan) 8%, transparent);
}

.drop--busy {
  opacity: 0.5;
  pointer-events: none;
}

.drop__lead {
  font-family: var(--display);
  font-size: 26px;
  letter-spacing: 0.04em;
  margin: 0 0 6px;
}

.drop__or {
  margin: 0 0 12px;
  font-size: 12px;
  color: var(--chalk-faint);
}

.drop__hint {
  margin: 16px 0 0;
  font-size: 12.5px;
  color: var(--chalk-faint);
}

.visually-hidden {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}

.block {
  margin-top: 14px;
}

.count {
  margin-left: auto;
  font-family: var(--mono);
  font-size: 11.5px;
  color: var(--chalk-faint);
}

.file {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 7px 0;
  border-top: 1px solid var(--line-soft);
}

.file:first-child {
  border-top: 0;
}

.file__name {
  font-family: var(--mono);
  font-size: 12.5px;
  flex: 1;
  overflow-wrap: anywhere;
}

.file__size {
  font-family: var(--mono);
  font-size: 11.5px;
  color: var(--chalk-faint);
}

.file__x {
  background: none;
  border: 0;
  color: var(--chalk-faint);
  font-size: 18px;
  line-height: 1;
  cursor: pointer;
  padding: 0 4px;
}

.file__x:hover {
  color: var(--unmet);
}

.actions {
  display: flex;
  gap: 10px;
  margin-top: 18px;
  flex-wrap: wrap;
}

.btn {
  font-family: var(--display);
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  padding: 8px 16px;
  background: none;
  border: 1px solid var(--line);
  color: var(--chalk-dim);
  cursor: pointer;
  display: inline-block;
}

.btn:hover:not(:disabled) {
  border-color: var(--cyan);
  color: var(--cyan);
}

.btn--primary {
  border-color: var(--cyan);
  color: var(--cyan);
  background: color-mix(in srgb, var(--cyan) 12%, transparent);
}

.btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.working {
  margin: 14px 0 0;
  font-size: 12.5px;
  color: var(--cyan);
  border-left: 2px solid var(--cyan);
  padding-left: 12px;
}

.failed {
  margin: 14px 0 0;
  padding: 12px 16px;
  border: 1px solid var(--unmet);
  color: var(--unmet);
  font-size: 13px;
}

.done {
  border-color: var(--met);
}

.done .panel__title {
  color: var(--met);
}

.reason {
  margin: 12px 0 0;
  font-size: 13px;
  color: var(--chalk-dim);
  max-width: 92ch;
}

.rules {
  margin: 0;
  padding-left: 18px;
  font-size: 13px;
  color: var(--chalk-dim);
  max-width: 92ch;
}

.rules li {
  margin-bottom: 7px;
}

.rules strong {
  color: var(--chalk);
  font-weight: 500;
}

code {
  font-family: var(--mono);
  font-size: 12px;
  color: var(--cyan);
}
</style>
