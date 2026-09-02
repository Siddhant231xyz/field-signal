<script setup>
import { computed, onMounted, ref } from 'vue'
import { actions, revisionNumbers, store } from '../store'

/* The brief's requirement: evidence changed → here is what moved. Every row
   below is computed by diff() in Python, never authored. */

const busy = ref(false)
const a = ref(0)
const b = ref(0)

const MOVE_COPY = {
  condition_status: 'a conclusion changed',
  condition_basis: 'the basis under it changed',
  condition_added: 'a question that did not exist',
  condition_removed: 'a question no longer asked',
  support_added: 'new evidence, same conclusion',
  unknown_opened: 'an unknown opened',
  unknown_closed: 'an unknown closed',
  queue_mode: 'a queue resolved differently',
  queue_head: 'a different claim now leads',
  queue_added: 'a new subject appeared',
  superseded: 'a claim was superseded',
  recommendation: 'the recommendation changed',
  blocking_changed: 'still holding, for different reasons',
  decision_basis: 'the decision’s basis changed',
}

const TONE = {
  unknown_opened: 'warn',
  condition_added: 'warn',
  unknown_closed: 'good',
  condition_status: 'good',
  superseded: 'info',
  recommendation: 'alert',
  blocking_changed: 'alert',
  condition_basis: 'taint',
  decision_basis: 'taint',
}

const canDiff = computed(() => revisionNumbers.value.length > 1)

async function load(path) {
  busy.value = true
  a.value = store.current
  await actions.loadFixture(path)
  b.value = store.current
  busy.value = false
}

async function reset() {
  busy.value = true
  await actions.reset()
  a.value = 0
  b.value = 0
  busy.value = false
}

/* Land on the most recent pair — the comparison someone arriving here wants. */
onMounted(() => {
  const revs = revisionNumbers.value
  if (revs.length > 1) {
    a.value = revs.at(-2)
    b.value = revs.at(-1)
    if (!store.moves) actions.diff(a.value, b.value)
  }
})
</script>

<template>
  <div class="rev">
    <header class="head">
      <p class="eyebrow">the evidence changed — here is what moved</p>
      <h1 class="head__title">Revisions</h1>
      <p class="head__note">
        A correction never edits a claim. It arrives as a new source that
        supersedes one, so every earlier revision stays computable and the
        superseded claim stays readable. The movement below is computed by
        comparing two derivations, not written down anywhere.
      </p>
    </header>

    <section class="panel block">
      <div class="panel__head">
        <h2 class="panel__title">Add a source</h2>
      </div>
      <div class="panel__body">
        <div class="fixtures">
          <button
            v-for="f in store.fixtures"
            :key="f"
            class="fixture"
            :disabled="busy || store.loaded.some((p) => p.endsWith(f.split('/').pop()))"
            @click="load(f)"
          >
            <span class="fixture__path">{{ f }}</span>
            <span class="fixture__go">load →</span>
          </button>
        </div>
        <p class="caution">
          Demo fixture, not packet evidence. It is labelled as such in its own
          header and in every source listing it produces.
        </p>
        <button v-if="store.current > 0" class="btn" :disabled="busy" @click="reset">
          back to the supplied packet
        </button>
      </div>
    </section>

    <section v-if="canDiff" class="panel block">
      <div class="panel__head">
        <h2 class="panel__title">Compare</h2>
        <div class="compare">
          <label>
            from
            <select v-model.number="a"><option v-for="n in revisionNumbers" :key="n" :value="n">rev {{ n }}</option></select>
          </label>
          <label>
            to
            <select v-model.number="b"><option v-for="n in revisionNumbers" :key="n" :value="n">rev {{ n }}</option></select>
          </label>
          <button class="btn" @click="actions.diff(a, b)">compare</button>
        </div>
      </div>
      <div class="panel__body">
        <p v-if="!store.moves" class="caution">
          Pick two revisions and compare.
        </p>
        <p v-else-if="!store.moves.length" class="caution">
          Nothing moved between these revisions.
        </p>
        <ol v-else class="moves">
          <li
            v-for="(m, i) in store.moves"
            :key="i"
            class="move"
            :class="`move--${TONE[m.kind] ?? 'info'}`"
          >
            <span class="move__kind">{{ MOVE_COPY[m.kind] ?? m.kind }}</span>
            <span class="move__id">{{ m.id }}</span>
            <span class="move__before">{{ m.before || '—' }}</span>
            <span class="move__arrow" aria-hidden="true">→</span>
            <span class="move__after">{{ m.after }}</span>
          </li>
        </ol>
      </div>
    </section>

    <section class="panel block">
      <div class="panel__head">
        <h2 class="panel__title">Showing</h2>
      </div>
      <div class="panel__body">
        <div class="revs">
          <button
            v-for="n in revisionNumbers"
            :key="n"
            class="revbtn"
            :class="{ 'revbtn--on': store.current === n }"
            @click="actions.showRevision(n)"
          >
            revision {{ n }}
            <span class="revbtn__verdict">
              {{ store.revisions[String(n)].decision.recommendation }}
            </span>
          </button>
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
  margin: 0;
  max-width: 80ch;
  font-size: 13px;
  color: var(--chalk-faint);
}

.block {
  margin-bottom: 14px;
}

.fixtures {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.fixture {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 10px 14px;
  background: none;
  border: 1px solid var(--line);
  cursor: pointer;
}

.fixture:hover:not(:disabled) {
  border-color: var(--cyan);
}

.fixture:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.fixture__path {
  font-family: var(--mono);
  font-size: 12.5px;
  color: var(--chalk);
}

.fixture__go {
  font-family: var(--display);
  font-size: 12px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--cyan);
}

.caution {
  margin: 14px 0;
  font-size: 12.5px;
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

.compare {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-left: auto;
  font-size: 12px;
  color: var(--chalk-faint);
}

.compare select {
  font-family: var(--mono);
  font-size: 12px;
  background: var(--ink-1);
  color: var(--chalk);
  border: 1px solid var(--line);
  padding: 3px 6px;
  margin-left: 4px;
}

.moves {
  list-style: none;
  margin: 0;
  padding: 0;
  counter-reset: move;
}

.move {
  display: grid;
  grid-template-columns: 250px 260px 1fr auto 1fr;
  gap: 14px;
  align-items: baseline;
  padding: 9px 0 9px 12px;
  border-top: 1px solid var(--line-soft);
  border-left: 2px solid var(--line);
  font-size: 12.5px;
}

.move--good {
  border-left-color: var(--met);
}
.move--warn {
  border-left-color: var(--unknown);
}
.move--alert {
  border-left-color: var(--unmet);
}
.move--taint {
  border-left-color: var(--contested);
}
.move--info {
  border-left-color: var(--cyan);
}

.move__kind {
  font-family: var(--display);
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--chalk);
}

.move__id,
.move__before,
.move__after {
  font-family: var(--mono);
  font-size: 11.5px;
}

.move__id {
  color: var(--cyan);
}
.move__before {
  color: var(--chalk-faint);
}
.move__after {
  color: var(--chalk);
}
.move__arrow {
  color: var(--chalk-faint);
}

.revs {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.revbtn {
  display: flex;
  flex-direction: column;
  gap: 3px;
  align-items: flex-start;
  padding: 9px 16px;
  background: none;
  border: 1px solid var(--line);
  color: var(--chalk-dim);
  cursor: pointer;
  font-family: var(--display);
  font-size: 14px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.revbtn--on {
  border-color: var(--cyan);
  color: var(--chalk);
  background: color-mix(in srgb, var(--cyan) 10%, transparent);
}

.revbtn__verdict {
  font-family: var(--mono);
  font-size: 11px;
  letter-spacing: 0;
  text-transform: none;
  color: var(--unmet);
}

@media (max-width: 1000px) {
  .move {
    grid-template-columns: 1fr;
    gap: 3px;
  }
  .move__arrow {
    display: none;
  }
}
</style>
