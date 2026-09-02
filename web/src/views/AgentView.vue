<script setup>
import { computed, onMounted, ref } from 'vue'
import { actions, store } from '../store'

/* Files in, a new revision out. The reading happens in a container on the
   server; nothing here interprets a document.

   All run state lives in the store, so switching sheets mid-run and coming
   back shows the same progress rather than an empty page. */

const dropping = ref(false)
const input = ref(null)

const STEPS = [
  ['staging', 'Copying your files into a clean directory'],
  ['building', 'Building the container image'],
  ['extracting', 'Reading your documents'],
  ['writing', 'Merging into a new revision'],
]

const phase = computed(() => store.progress.phase)
const failed = computed(() => phase.value === 'failed')

const reached = computed(() => {
  const order = STEPS.map(([k]) => k)
  if (phase.value === 'done') return order.length
  const i = order.indexOf(phase.value)
  return i === -1 ? 0 : i
})

const total = computed(() => store.picked.reduce((sum, f) => sum + f.size, 0))

function stepState(i) {
  if (failed.value) return i < reached.value ? 'done' : i === reached.value ? 'failed' : 'todo'
  if (i < reached.value) return 'done'
  if (i === reached.value && store.busy) return 'active'
  if (phase.value === 'done') return 'done'
  return 'todo'
}

function drop(event) {
  dropping.value = false
  actions.pick(Array.from(event.dataTransfer.files))
}

async function run() {
  await actions.ingest()
  if (input.value) input.value.value = ''
}

function size(bytes) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

// A run may have been started from this sheet, then left. Ask the server.
onMounted(actions.refreshProgress)
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

    <!-- Progress first: if a run is going, that is the only thing that matters. -->
    <section v-if="store.busy || phase === 'done' || failed" class="panel block run">
      <div class="panel__head">
        <h2 class="panel__title">
          {{ store.busy ? 'Reading' : failed ? 'Stopped' : 'Finished' }}
        </h2>
        <span v-if="store.busy" class="spinner" aria-hidden="true" />
        <span class="count">
          {{ store.progress.files }} file{{ store.progress.files === 1 ? '' : 's' }}
          <template v-if="store.progress.base"> · off v{{ store.progress.base }}</template>
        </span>
      </div>
      <div class="panel__body">
        <ol class="steps">
          <li v-for="(s, i) in STEPS" :key="s[0]" class="step" :class="`step--${stepState(i)}`">
            <span class="step__mark" aria-hidden="true">
              {{ stepState(i) === 'done' ? '✓' : stepState(i) === 'failed' ? '✗' : stepState(i) === 'active' ? '▶' : '·' }}
            </span>
            <span class="step__label">{{ s[1] }}</span>
            <span v-if="s[0] === 'extracting' && store.progress.shell_calls" class="step__meta">
              {{ store.progress.shell_calls }} shell command{{ store.progress.shell_calls === 1 ? '' : 's' }} run
            </span>
          </li>
        </ol>

        <p v-if="store.busy" class="working">
          This takes minutes. You can move to another sheet — the run keeps
          going and this page will show where it got to.
        </p>

        <p v-if="failed" class="failed">
          <strong>Nothing was written.</strong>
          {{ store.progress.error || store.error }}
        </p>

        <template v-if="!store.busy && !failed && store.lastRun?.ok">
          <p class="reason">
            <strong>Revision {{ store.lastRun.revision }}</strong> created from
            v{{ store.lastRun.base }}, and now selected — every sheet shows it.
            Open <strong>Revisions</strong> to see what moved, or select
            v{{ store.lastRun.base }} again to go back.
          </p>
          <p
            v-if="Object.keys(store.progress.merged_people || {}).length"
            class="merged"
          >
            The agent named people it had already met. Matched to the existing
            record so authority is not split in two:
            <span class="mono">
              {{ Object.entries(store.progress.merged_people).map(([a, b]) => `${a} → ${b}`).join(', ') }}
            </span>
            Capabilities came from the packet, not from the agent.
          </p>
        </template>
      </div>
    </section>

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
          :disabled="store.busy"
          @change="actions.pick(Array.from($event.target.files))"
        />
      </label>
      <p class="drop__hint">
        Transcripts, messages, schedules, quotes, photographs — whatever the
        project produced.
      </p>
    </section>

    <section v-if="store.picked.length" class="panel block">
      <div class="panel__head">
        <h2 class="panel__title">Ready to read</h2>
        <span class="count">
          {{ store.picked.length }} file{{ store.picked.length === 1 ? '' : 's' }} · {{ size(total) }}
        </span>
      </div>
      <div class="panel__body">
        <div v-for="(f, i) in store.picked" :key="f.name + i" class="file">
          <span class="file__name">{{ f.name }}</span>
          <span class="file__size">{{ size(f.size) }}</span>
          <button class="file__x" :disabled="store.busy" aria-label="Remove" @click="actions.unpick(i)">×</button>
        </div>

        <div class="actions">
          <button class="btn btn--primary" :disabled="store.busy" @click="run">
            {{ store.busy ? 'reading…' : `read into a new revision off v${store.current}` }}
          </button>
          <button class="btn" :disabled="store.busy" @click="actions.clearPicked">clear</button>
        </div>
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
          <li>A person it has already met keeps the capabilities the packet gave them. It cannot grant anyone authority by naming them again.</li>
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

.run {
  margin-bottom: 14px;
  border-color: var(--cyan);
}

.spinner {
  width: 11px;
  height: 11px;
  border: 2px solid color-mix(in srgb, var(--cyan) 35%, transparent);
  border-top-color: var(--cyan);
  border-radius: 50%;
  animation: spin 0.85s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.steps {
  list-style: none;
  margin: 0;
  padding: 0;
}

.step {
  display: flex;
  align-items: baseline;
  gap: 12px;
  padding: 6px 0;
  font-size: 13px;
}

.step__mark {
  font-family: var(--mono);
  width: 14px;
  flex: none;
}

.step--todo { color: var(--chalk-faint); opacity: 0.55; }
.step--done { color: var(--met); }
.step--active { color: var(--cyan); font-weight: 500; }
.step--failed { color: var(--unmet); }

.step__meta {
  font-family: var(--mono);
  font-size: 11.5px;
  color: var(--chalk-faint);
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

.drop--busy { opacity: 0.4; pointer-events: none; }

.drop__lead {
  font-family: var(--display);
  font-size: 26px;
  letter-spacing: 0.04em;
  margin: 0 0 6px;
}

.drop__or { margin: 0 0 12px; font-size: 12px; color: var(--chalk-faint); }

.drop__hint { margin: 16px 0 0; font-size: 12.5px; color: var(--chalk-faint); }

.visually-hidden {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}

.block { margin-top: 14px; }

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

.file:first-child { border-top: 0; }

.file__name {
  font-family: var(--mono);
  font-size: 12.5px;
  flex: 1;
  overflow-wrap: anywhere;
}

.file__size { font-family: var(--mono); font-size: 11.5px; color: var(--chalk-faint); }

.file__x {
  background: none;
  border: 0;
  color: var(--chalk-faint);
  font-size: 18px;
  line-height: 1;
  cursor: pointer;
  padding: 0 4px;
}

.file__x:hover { color: var(--unmet); }

.actions { display: flex; gap: 10px; margin-top: 18px; flex-wrap: wrap; }

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

.btn:hover:not(:disabled) { border-color: var(--cyan); color: var(--cyan); }

.btn--primary {
  border-color: var(--cyan);
  color: var(--cyan);
  background: color-mix(in srgb, var(--cyan) 12%, transparent);
}

.btn:disabled { opacity: 0.45; cursor: not-allowed; }

.working {
  margin: 14px 0 0;
  font-size: 12.5px;
  color: var(--cyan);
  border-left: 2px solid var(--cyan);
  padding-left: 12px;
}

.failed {
  margin: 14px 0 0;
  padding: 10px 14px;
  border: 1px solid var(--unmet);
  color: var(--unmet);
  font-size: 13px;
}

.merged {
  margin: 12px 0 0;
  padding-left: 12px;
  border-left: 2px solid var(--contested);
  font-size: 12.5px;
  color: var(--chalk-dim);
}

.mono { font-family: var(--mono); font-size: 11.5px; color: var(--contested); }

.reason {
  margin: 12px 0 0;
  font-size: 13px;
  color: var(--chalk-dim);
  max-width: 92ch;
}

.reason strong { color: var(--chalk); font-weight: 500; }

.rules {
  margin: 0;
  padding-left: 18px;
  font-size: 13px;
  color: var(--chalk-dim);
  max-width: 92ch;
}

.rules li { margin-bottom: 7px; }
.rules strong { color: var(--chalk); font-weight: 500; }

code { font-family: var(--mono); font-size: 12px; color: var(--cyan); }
</style>
