<script setup>
import { store } from '../store'

const CAN_SPEND = 'authorise_added_cost'
</script>

<template>
  <div class="prov">
    <header class="head">
      <p class="eyebrow">who can actually decide, and what the record rests on</p>
      <h1 class="head__title">Authority &amp; provenance</h1>
      <p class="head__note">
        Every capability below is quoted from the project primer. Support from
        someone without the capability is sentiment, not authorisation.
      </p>
    </header>

    <section class="panel block">
      <div class="panel__head">
        <h2 class="panel__title">People</h2>
      </div>
      <div class="panel__body">
        <article
          v-for="p in store.ledger.people"
          :key="p.id"
          class="person"
          :class="{ 'person--spender': p.capabilities.includes(CAN_SPEND) }"
        >
          <div class="person__who">
            <h3 class="person__name">{{ p.name }}</h3>
            <p class="person__role">{{ p.role }} · {{ p.org }}</p>
          </div>
          <div class="person__caps">
            <span v-for="c in p.capabilities" :key="c" class="cap" :class="{ 'cap--spend': c === CAN_SPEND }">
              {{ c.replace(/_/g, ' ') }}
            </span>
          </div>
          <p class="person__basis verbatim">{{ p.capability_basis }}</p>
        </article>
      </div>
    </section>

    <section class="panel block">
      <div class="panel__head">
        <h2 class="panel__title">Sources</h2>
      </div>
      <div class="panel__body">
        <article
          v-for="s in store.ledger.sources"
          :key="s.id"
          class="source"
          :class="{ 'source--absent': !s.present }"
        >
          <div class="source__id">
            <span class="mono">{{ s.id }}</span>
            <span v-if="!s.present" class="chip chip--unmet">
              <span class="chip__glyph">✗</span> not supplied
            </span>
          </div>
          <div class="source__meta">
            <h3 class="source__type">{{ s.type }}</h3>
            <p class="source__line">
              {{ s.author }} · {{ s.logical_time }} · cited by {{ s.locator_model }}
            </p>
            <ul class="source__limits">
              <li v-for="(l, i) in s.limitations" :key="i">{{ l }}</li>
            </ul>
          </div>
        </article>
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

.block {
  margin-bottom: 16px;
}

.person,
.source {
  display: grid;
  gap: 6px 20px;
  padding: 14px 0;
  border-top: 1px solid var(--line-soft);
}

.person {
  grid-template-columns: 220px 1fr;
}

.person:first-child,
.source:first-child {
  border-top: 0;
  padding-top: 0;
}

.person--spender {
  border-left: 2px solid var(--met);
  padding-left: 14px;
  margin-left: -16px;
}

.person__name {
  font-size: 20px;
}

.person__role {
  margin: 0;
  font-size: 12.5px;
  color: var(--chalk-faint);
}

.person__caps {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-content: start;
}

.cap {
  font-family: var(--display);
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  padding: 2px 8px;
  border: 1px solid var(--line);
  color: var(--chalk-dim);
}

.cap--spend {
  border-color: var(--met);
  color: var(--met);
}

.person__basis {
  grid-column: 2;
  margin: 0;
  max-width: 90ch;
}

.source {
  grid-template-columns: 160px 1fr;
}

.source--absent .source__type {
  color: var(--unmet);
}

.source__id {
  display: flex;
  flex-direction: column;
  gap: 6px;
  align-items: flex-start;
}

.mono {
  font-family: var(--mono);
  font-size: 14px;
}

.source__type {
  font-size: 18px;
  text-transform: capitalize;
}

.source__line {
  margin: 2px 0 0;
  font-size: 12.5px;
  color: var(--chalk-faint);
}

.source__limits {
  margin: 8px 0 0;
  padding-left: 16px;
  font-size: 12.5px;
  color: var(--chalk-dim);
  max-width: 92ch;
}

.source__limits li {
  margin-bottom: 3px;
}

@media (max-width: 760px) {
  .person,
  .source {
    grid-template-columns: 1fr;
  }
  .person__basis {
    grid-column: 1;
  }
}
</style>
