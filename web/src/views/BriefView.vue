<script setup>
import { ref } from 'vue'
import { view } from '../store'
import StatusChip from '../components/StatusChip.vue'
import VerdictStamp from '../components/VerdictStamp.vue'
import ClaimRow from '../components/ClaimRow.vue'

const open = ref(null)

function toggle(id) {
  open.value = open.value === id ? null : id
}
</script>

<template>
  <div v-if="view" class="brief">
    <header class="verdict">
      <div class="verdict__text">
        <p class="eyebrow">the decision in front of you</p>
        <h1 class="verdict__title">{{ view.decision.label }}</h1>
        <p class="verdict__q">{{ view.decision.question }}</p>
        <p v-if="view.decision.contested_by.length" class="verdict__taint">
          Contested because the evidence beneath it disagrees with itself:
          <span class="mono">{{ view.decision.contested_by.join(' · ') }}</span>
        </p>
      </div>
      <VerdictStamp :decision="view.decision" />
    </header>

    <section class="block">
      <div class="block__head">
        <h2 class="block__title">Already true</h2>
        <p class="block__note">
          Behind you. These are not conditions — you cannot prevent them.
        </p>
      </div>
      <div class="exposures">
        <article
          v-for="(e, i) in view.exposures"
          :key="e.id"
          class="panel exposure rise"
          :style="{ animationDelay: `${i * 60}ms` }"
        >
          <div class="panel__head">
            <StatusChip status="exposed" />
            <h3 class="panel__title">{{ e.label }}</h3>
          </div>
          <div class="panel__body">
            <p class="exposure__detail">{{ e.detail }}</p>
          </div>
        </article>
      </div>
    </section>

    <section class="block">
      <div class="block__head">
        <h2 class="block__title">Ahead of you</h2>
        <p class="block__note">
          What has to be true before you can direct. Select a row for the full
          derivation.
        </p>
      </div>

      <div class="conditions">
        <article
          v-for="(c, i) in view.conditions"
          :key="c.id"
          class="panel condition rise"
          :class="{ hatched: c.basis === 'contested', 'condition--open': open === c.id }"
          :style="{ animationDelay: `${i * 45}ms` }"
        >
          <button class="condition__head" :aria-expanded="open === c.id" @click="toggle(c.id)">
            <StatusChip :status="c.status" :basis="c.basis" />
            <span class="condition__label">{{ c.label }}</span>
            <span class="condition__id">{{ c.id }}</span>
          </button>

          <div class="condition__body">
            <p class="condition__reason">{{ c.reason }}</p>

            <div v-if="open === c.id" class="derivation">
              <p class="condition__question">{{ c.question }}</p>

              <div v-if="c.depends_on.length" class="derivation__deps">
                <p class="eyebrow">blocked behind</p>
                <ul>
                  <li v-for="d in c.depends_on" :key="d">{{ d }}</li>
                </ul>
              </div>

              <p class="eyebrow">read by this rule — these gate</p>
              <ClaimRow v-for="id in c.support" :key="id" :id="id" />

              <template v-if="c.notes.length">
                <p class="eyebrow spaced">shown, but never allowed to gate</p>
                <ClaimRow v-for="id in c.notes" :key="id" :id="id" />
              </template>
            </div>
          </div>
        </article>
      </div>
    </section>
  </div>
</template>

<style scoped>
.brief {
  display: flex;
  flex-direction: column;
  gap: 44px;
}

.verdict {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 40px;
  flex-wrap: wrap;
  padding-bottom: 26px;
  border-bottom: 1px solid var(--line);
}

.verdict__text {
  max-width: 62ch;
}

.verdict__title {
  font-size: 40px;
  line-height: 1.04;
  margin: 6px 0 8px;
  text-wrap: balance;
}

.verdict__q {
  margin: 0;
  color: var(--chalk-dim);
  font-size: 15px;
}

.verdict__taint {
  margin: 14px 0 0;
  font-size: 13px;
  color: var(--contested);
  border-left: 2px solid var(--contested);
  padding-left: 12px;
}

.mono {
  font-family: var(--mono);
  font-size: 12px;
}

.block__head {
  margin-bottom: 16px;
}

.block__title {
  font-size: 24px;
  letter-spacing: 0.05em;
  text-transform: uppercase;
}

.block__note {
  margin: 2px 0 0;
  color: var(--chalk-faint);
  font-size: 13px;
}

.exposures {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(360px, 1fr));
  gap: 14px;
}

.exposure__detail {
  margin: 0;
  color: var(--chalk-dim);
  font-size: 13.5px;
}

.conditions {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.condition__head {
  display: flex;
  align-items: center;
  gap: 16px;
  width: 100%;
  padding: 12px 16px;
  background: none;
  border: 0;
  border-bottom: 1px solid var(--line);
  cursor: pointer;
  text-align: left;
}

.condition__head:hover {
  background: color-mix(in srgb, var(--cyan) 7%, transparent);
}

.condition__label {
  font-family: var(--display);
  font-size: 18px;
  letter-spacing: 0.03em;
  flex: 1;
}

.condition__id {
  font-family: var(--mono);
  font-size: 11px;
  color: var(--chalk-faint);
}

.condition__body {
  padding: 14px 16px 16px;
}

.condition__reason {
  margin: 0;
  color: var(--chalk-dim);
  font-size: 13.5px;
  max-width: 96ch;
}

.condition__question {
  font-family: var(--display);
  font-size: 17px;
  color: var(--cyan);
  margin: 0 0 14px;
}

.derivation {
  margin-top: 20px;
  border-top: 1px dashed var(--line);
  padding-top: 16px;
}

.derivation__deps {
  margin-bottom: 16px;
}

.derivation__deps ul {
  margin: 4px 0 0;
  padding-left: 18px;
  font-family: var(--mono);
  font-size: 12px;
  color: var(--unknown);
}

.eyebrow.spaced {
  display: block;
  margin-top: 22px;
}
</style>
