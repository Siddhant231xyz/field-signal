<script setup>
import { computed, onMounted, ref } from 'vue'
import { actions, store } from '../store'

const running = ref(false)

const rows = computed(() => store.verify ?? [])
const failed = computed(() => rows.value.filter((r) => r.result === 'NOT FOUND'))
const skipped = computed(() => rows.value.filter((r) => r.result.startsWith('skipped')))
const found = computed(() => rows.value.filter((r) => r.result === 'found'))

async function run() {
  running.value = true
  await actions.runVerify()
  running.value = false
}

onMounted(() => {
  if (!store.verify) run()
})
</script>

<template>
  <div class="verify">
    <header class="head">
      <p class="eyebrow">the ledger, checked against the real documents</p>
      <h1 class="head__title">Verify</h1>
      <p class="head__note">
        Every claim stores the text it was read from. This reads each source
        document again and looks for that text. It proves the claims present are
        real; it cannot prove a claim missing from the ledger should have been
        in it. That gap is the failure worth worrying about.
      </p>
      <button class="btn" :disabled="running" @click="run">
        {{ running ? 'checking…' : 'run again' }}
      </button>
    </header>

    <div v-if="rows.length" class="tally">
      <div class="tally__item tally__item--good">
        <span class="tally__n">{{ found.length }}</span>
        <span class="tally__l">found in source</span>
      </div>
      <div class="tally__item" :class="failed.length ? 'tally__item--bad' : 'tally__item--muted'">
        <span class="tally__n">{{ failed.length }}</span>
        <span class="tally__l">not found</span>
      </div>
      <div class="tally__item tally__item--muted">
        <span class="tally__n">{{ skipped.length }}</span>
        <span class="tally__l">images — no text to check</span>
      </div>
    </div>

    <section v-if="failed.length" class="panel block">
      <div class="panel__head">
        <h2 class="panel__title">Not found</h2>
      </div>
      <div class="panel__body">
        <div v-for="r in failed" :key="r.claim" class="row row--bad">
          <span class="row__claim">{{ r.claim }}</span>
          <span class="row__source">{{ r.source }}</span>
          <span class="row__detail">{{ r.detail }}</span>
        </div>
      </div>
    </section>

    <section class="panel block">
      <div class="panel__head">
        <h2 class="panel__title">All claims</h2>
      </div>
      <div class="panel__body scroll">
        <div v-for="r in rows" :key="r.claim" class="row">
          <span class="row__claim">{{ r.claim }}</span>
          <span class="row__source">{{ r.source }}</span>
          <span class="row__result" :class="`row__result--${r.result === 'found' ? 'ok' : r.result === 'NOT FOUND' ? 'bad' : 'skip'}`">
            {{ r.result }}
          </span>
          <span class="row__detail">{{ r.detail }}</span>
        </div>
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
  margin: 0 0 14px;
  max-width: 78ch;
  font-size: 13px;
  color: var(--chalk-faint);
}

.btn {
  font-family: var(--display);
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  padding: 6px 12px;
  background: none;
  border: 1px solid var(--line);
  color: var(--chalk-dim);
  cursor: pointer;
}

.btn:hover:not(:disabled) {
  border-color: var(--cyan);
  color: var(--cyan);
}

.tally {
  display: flex;
  gap: 14px;
  flex-wrap: wrap;
  margin-bottom: 18px;
}

.tally__item {
  display: flex;
  flex-direction: column;
  padding: 12px 22px;
  border: 1px solid var(--line);
  min-width: 170px;
}

.tally__item--good {
  border-color: var(--met);
  color: var(--met);
}
.tally__item--bad {
  border-color: var(--unmet);
  color: var(--unmet);
}
.tally__item--muted {
  color: var(--chalk-faint);
}

.tally__n {
  font-family: var(--display);
  font-size: 40px;
  font-weight: 700;
  line-height: 1;
}

.tally__l {
  font-family: var(--display);
  font-size: 12px;
  letter-spacing: 0.13em;
  text-transform: uppercase;
  margin-top: 4px;
}

.block {
  margin-bottom: 14px;
}

.scroll {
  max-height: 60vh;
  overflow: auto;
}

.row {
  display: grid;
  grid-template-columns: 110px 80px 130px 1fr;
  gap: 12px;
  padding: 6px 0;
  border-top: 1px solid var(--line-soft);
  font-family: var(--mono);
  font-size: 11.5px;
  align-items: baseline;
}

.row--bad {
  grid-template-columns: 110px 80px 1fr;
}

.row__claim {
  color: var(--chalk);
}
.row__source {
  color: var(--cyan);
}
.row__detail {
  color: var(--chalk-faint);
  overflow-wrap: anywhere;
}

.row__result--ok {
  color: var(--met);
}
.row__result--bad {
  color: var(--unmet);
}
.row__result--skip {
  color: var(--chalk-faint);
}
</style>
