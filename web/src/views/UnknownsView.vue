<script setup>
import { computed } from 'vue'
import { sources, view } from '../store'
import StatusChip from '../components/StatusChip.vue'
import ClaimRow from '../components/ClaimRow.vue'

const unknowns = computed(() =>
  (view.value?.conditions ?? []).filter((c) => c.status === 'unknown'),
)
const absent = computed(() => view.value?.absent_bases ?? {})
</script>

<template>
  <div v-if="view" class="unknowns">
    <header class="head">
      <p class="eyebrow">what the packet does not say</p>
      <h1 class="head__title">Unknowns</h1>
      <p class="head__note">
        Unknown means the record is silent. It never means no. A meeting with no
        minutes is not a meeting that did not happen, and a missing approval is
        not a refusal.
      </p>
    </header>

    <article v-for="c in unknowns" :key="c.id" class="panel gap" :class="{ hatched: c.basis === 'contested' }">
      <div class="panel__head">
        <StatusChip :status="c.status" :basis="c.basis" />
        <h2 class="panel__title">{{ c.label }}</h2>
      </div>
      <div class="panel__body">
        <p class="question">{{ c.question }}</p>
        <p class="reason">{{ c.reason }}</p>
      </div>
    </article>

    <section v-if="Object.keys(absent).length" class="panel gap">
      <div class="panel__head">
        <h2 class="panel__title">Cited, but not supplied</h2>
      </div>
      <div class="panel__body">
        <p class="reason spaced">
          These documents are leaned on by claims in the packet. Neither is in
          it, so nothing that rests on them can be checked.
        </p>
        <div v-for="(claimIds, sid) in absent" :key="sid" class="absent">
          <div class="absent__head">
            <span class="absent__id">{{ sid }}</span>
            <span class="chip chip--unmet">
              <span class="chip__glyph">✗</span>
              not supplied
            </span>
          </div>
          <p class="reason">{{ sources[sid]?.limitations?.[0] }}</p>
          <ClaimRow v-for="id in claimIds" :key="id" :id="id" />
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
  max-width: 74ch;
  font-size: 13px;
  color: var(--chalk-faint);
}

.gap {
  margin-bottom: 12px;
}

.question {
  font-family: var(--display);
  font-size: 19px;
  color: var(--cyan);
  margin: 0 0 10px;
}

.reason {
  margin: 0;
  font-size: 13.5px;
  color: var(--chalk-dim);
  max-width: 96ch;
}

.reason.spaced {
  margin-bottom: 18px;
}

.absent {
  padding: 14px 0;
  border-top: 1px solid var(--line-soft);
}

.absent__head {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 6px;
}

.absent__id {
  font-family: var(--mono);
  font-size: 14px;
  color: var(--chalk);
}
</style>
