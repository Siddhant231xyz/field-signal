<script setup>
import { computed, onMounted, ref } from 'vue'
import { actions, store, view } from './store'
import AgentView from './views/AgentView.vue'
import BriefView from './views/BriefView.vue'
import GraphView from './views/GraphView.vue'
import EvidenceView from './views/EvidenceView.vue'
import UnknownsView from './views/UnknownsView.vue'
import ProvenanceView from './views/ProvenanceView.vue'
import RevisionsView from './views/RevisionsView.vue'
import VerifyView from './views/VerifyView.vue'

/* Nav labels are the CLI's own commands. The two front ends run the same
   engine, and saying so is more honest than inventing new names. */
const SHEETS = [
  { id: 'brief', cmd: '/brief', name: 'Decision brief', view: BriefView },
  { id: 'graph', cmd: '/graph', name: 'Evidence in space', view: GraphView },
  { id: 'evidence', cmd: '/evidence', name: 'Claim queues', view: EvidenceView },
  { id: 'conflicts', cmd: '/conflicts', name: 'Conflicts', view: EvidenceView, props: { conflictsOnly: true } },
  { id: 'unknowns', cmd: '/unknowns', name: 'Unknowns', view: UnknownsView },
  { id: 'provenance', cmd: '/people /sources', name: 'Authority', view: ProvenanceView },
  { id: 'agent', cmd: '/agent', name: 'Add evidence', view: AgentView },
  { id: 'revisions', cmd: '/load /diff', name: 'Revisions', view: RevisionsView },
  { id: 'verify', cmd: '/verify', name: 'Verify', view: VerifyView },
]

/* Hash routing so a sheet can be linked, reloaded and shared. */
const known = (id) => SHEETS.some((s) => s.id === id)
const fromHash = () => {
  const id = window.location.hash.replace(/^#\/?/, '')
  return known(id) ? id : 'brief'
}

const active = ref(fromHash())
const sheet = computed(() => SHEETS.find((s) => s.id === active.value))
const bleed = computed(() => sheet.value.id === 'graph')

function go(id) {
  active.value = id
  window.location.hash = `#/${id}`
}

window.addEventListener('hashchange', () => (active.value = fromHash()))

const RUN_LABEL = {
  staging: 'staging files',
  building: 'building image',
  extracting: 'reading documents',
  writing: 'writing revision',
}

const counts = computed(() => {
  const v = view.value
  if (!v) return null
  return {
    unknowns: v.conditions.filter((c) => c.status === 'unknown').length,
    conflicts: v.queues.filter((q) => q.mode === 'assumed').length,
  }
})

onMounted(actions.boot)
</script>

<template>
  <div class="shell">
    <!-- The title block on a drawing sheet: what this is, and its state. -->
    <header class="titleblock">
      <div class="titleblock__mark">
        <span class="titleblock__name">Field Signal</span>
        <span class="titleblock__proj">Hawthorne Commons Café · HC-17</span>
      </div>

      <div class="titleblock__field">
        <span class="titleblock__k">sheet</span>
        <span class="titleblock__v">{{ sheet.name }}</span>
      </div>

      <div class="titleblock__field">
        <span class="titleblock__k">revision</span>
        <span class="titleblock__v titleblock__v--rev">
          v{{ store.current }}
          <span class="titleblock__of">of {{ Object.keys(store.revisions).length }}</span>
        </span>
      </div>

      <button
        v-if="store.busy"
        class="titleblock__field titleblock__running"
        @click="go('agent')"
      >
        <span class="titleblock__k">agent</span>
        <span class="titleblock__v titleblock__v--run">
          <span class="rail__spin" aria-hidden="true" />
          {{ RUN_LABEL[store.progress.phase] ?? 'running' }}
          <span v-if="store.progress.shell_calls" class="titleblock__of">
            {{ store.progress.shell_calls }} cmds
          </span>
        </span>
      </button>

      <div v-if="view" class="titleblock__field titleblock__field--verdict">
        <span class="titleblock__k">direction on CA-118</span>
        <span class="titleblock__v" :class="`verdict--${view.decision.recommendation.toLowerCase()}`">
          {{ view.decision.recommendation }}
          <span v-if="view.decision.basis === 'contested'" class="titleblock__taint">
            basis contested
          </span>
        </span>
      </div>
    </header>

    <nav class="rail" aria-label="Views">
      <button
        v-for="s in SHEETS"
        :key="s.id"
        class="rail__item"
        :class="{ 'rail__item--on': active === s.id }"
        :aria-current="active === s.id ? 'page' : undefined"
        @click="go(s.id)"
      >
        <span class="rail__name">{{ s.name }}</span>
        <span class="rail__cmd">{{ s.cmd }}</span>
        <span
          v-if="counts && s.id === 'unknowns' && counts.unknowns"
          class="rail__count rail__count--unknown"
        >{{ counts.unknowns }}</span>
        <span
          v-if="counts && s.id === 'conflicts' && counts.conflicts"
          class="rail__count rail__count--conflict"
        >{{ counts.conflicts }}</span>
        <span
          v-if="s.id === 'agent' && store.busy"
          class="rail__spin"
          role="status"
          aria-label="The agent is running"
        />
      </button>

      <p class="rail__foot">
        Every conclusion is derived at run time from the packet. Nothing on
        these sheets is written by hand.
      </p>
    </nav>

    <main class="sheet" :class="{ 'sheet--bleed': bleed }">
      <p v-if="store.loading" class="state">Reading the packet…</p>
      <p v-else-if="store.error" class="state state--error">
        {{ store.error }}
      </p>
      <component v-else :is="sheet.view" v-bind="sheet.props ?? {}" :key="sheet.id" />
    </main>
  </div>
</template>

<style scoped>
.shell {
  display: grid;
  grid-template-columns: var(--rail) 1fr;
  grid-template-rows: var(--bar) 1fr;
  height: 100%;
  position: relative;
  z-index: 1;
}

/* --- title block ------------------------------------------------------- */

.titleblock {
  grid-column: 1 / -1;
  display: flex;
  align-items: stretch;
  border-bottom: 1px solid var(--line);
  background: var(--ink-1);
}

.titleblock__mark {
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 0 18px;
  width: var(--rail);
  border-right: 1px solid var(--line);
}

.titleblock__name {
  font-family: var(--display);
  font-size: 19px;
  font-weight: 700;
  letter-spacing: 0.13em;
  text-transform: uppercase;
}

.titleblock__proj {
  font-family: var(--mono);
  font-size: 10.5px;
  color: var(--chalk-faint);
}

.titleblock__field {
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 0 20px;
  border-right: 1px solid var(--line);
  min-width: 130px;
}

.titleblock__field--verdict {
  margin-left: auto;
  border-right: 0;
  border-left: 1px solid var(--line);
  align-items: flex-end;
  text-align: right;
}

.titleblock__k {
  font-family: var(--display);
  font-size: 10.5px;
  font-weight: 600;
  letter-spacing: 0.19em;
  text-transform: uppercase;
  color: var(--chalk-faint);
}

.titleblock__v {
  font-family: var(--display);
  font-size: 17px;
  letter-spacing: 0.04em;
}

.titleblock__v--rev {
  color: var(--cyan);
}

.titleblock__of {
  font-family: var(--mono);
  font-size: 10px;
  color: var(--chalk-faint);
  margin-left: 4px;
}

.verdict--hold {
  color: var(--unmet);
  font-weight: 700;
}
.verdict--proceed {
  color: var(--met);
  font-weight: 700;
}

.titleblock__taint {
  font-family: var(--mono);
  font-size: 10px;
  letter-spacing: 0;
  color: var(--contested);
  margin-left: 8px;
}

/* --- rail -------------------------------------------------------------- */

.rail {
  display: flex;
  flex-direction: column;
  border-right: 1px solid var(--line);
  background: color-mix(in srgb, var(--ink-1) 60%, transparent);
  overflow-y: auto;
}

.rail__item {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 1px 8px;
  text-align: left;
  padding: 11px 18px;
  background: none;
  border: 0;
  border-bottom: 1px solid var(--line-soft);
  border-left: 2px solid transparent;
  cursor: pointer;
  color: var(--chalk-dim);
}

.rail__item:hover {
  background: color-mix(in srgb, var(--cyan) 8%, transparent);
  color: var(--chalk);
}

.rail__item--on {
  border-left-color: var(--cyan);
  background: color-mix(in srgb, var(--cyan) 12%, transparent);
  color: var(--chalk);
}

.rail__name {
  grid-column: 1;
  grid-row: 1;
  font-family: var(--display);
  font-size: 16px;
  letter-spacing: 0.04em;
}

.rail__cmd {
  grid-column: 1;
  grid-row: 2;
  font-family: var(--mono);
  font-size: 10.5px;
  color: var(--chalk-faint);
}

.rail__count {
  grid-column: 2;
  grid-row: 1 / span 2;
  justify-self: end;
  align-self: center;
  font-family: var(--mono);
  font-size: 11px;
  line-height: 1.4;
  padding: 1px 7px;
  border: 1px solid currentColor;
}

.rail__count--unknown {
  color: var(--unknown);
}
.rail__count--conflict {
  color: var(--contested);
}

.rail__spin {
  grid-column: 2;
  grid-row: 1 / span 2;
  align-self: center;
  justify-self: end;
  width: 11px;
  height: 11px;
  border: 2px solid color-mix(in srgb, var(--cyan) 30%, transparent);
  border-top-color: var(--cyan);
  border-radius: 50%;
  animation: spin 0.85s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.titleblock__running {
  background: none;
  border: 0;
  border-right: 1px solid var(--line);
  cursor: pointer;
  text-align: left;
  color: var(--cyan);
}

.titleblock__running:hover {
  background: color-mix(in srgb, var(--cyan) 10%, transparent);
}

.titleblock__v--run {
  display: flex;
  align-items: center;
  gap: 7px;
  color: var(--cyan);
  font-size: 15px;
}

.rail__foot {
  margin: auto 18px 18px;
  padding-top: 18px;
  font-size: 11.5px;
  line-height: 1.5;
  color: var(--chalk-faint);
  border-top: 1px solid var(--line-soft);
}

/* --- sheet ------------------------------------------------------------- */

.sheet {
  overflow-y: auto;
  padding: 32px 38px 70px;
  position: relative;
}

.sheet--bleed {
  padding: 0;
  overflow: hidden;
}

.state {
  font-family: var(--display);
  font-size: 18px;
  letter-spacing: 0.06em;
  color: var(--chalk-faint);
}

.state--error {
  color: var(--unmet);
  font-family: var(--mono);
  font-size: 13px;
}

@media (max-width: 900px) {
  .shell {
    grid-template-columns: 1fr;
    grid-template-rows: auto auto 1fr;
  }
  .titleblock {
    flex-wrap: wrap;
  }
  .titleblock__mark {
    width: auto;
    flex: 1;
  }
  .rail {
    flex-direction: row;
    overflow-x: auto;
    border-right: 0;
    border-bottom: 1px solid var(--line);
  }
  .rail__item {
    border-bottom: 0;
    border-left: 0;
    border-top: 2px solid transparent;
    white-space: nowrap;
  }
  .rail__item--on {
    border-left-color: transparent;
    border-top-color: var(--cyan);
  }
  .rail__foot {
    display: none;
  }
  .sheet {
    padding: 22px 18px 60px;
  }
}
</style>
