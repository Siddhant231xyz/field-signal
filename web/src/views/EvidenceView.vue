<script setup>
import { computed, ref } from 'vue'
import { view } from '../store'
import ClaimRow from '../components/ClaimRow.vue'

const props = defineProps({ conflictsOnly: { type: Boolean, default: false } })

const filter = ref('')

const queues = computed(() => {
  const all = view.value?.queues ?? []
  const scoped = props.conflictsOnly ? all.filter((q) => q.mode === 'assumed') : all
  const needle = filter.value.trim().toLowerCase()
  return needle ? scoped.filter((q) => q.key.toLowerCase().includes(needle)) : scoped
})

const rebuttals = computed(() => view.value?.rebuttals ?? {})
</script>

<template>
  <div v-if="view" class="evidence">
    <header class="head">
      <div>
        <p class="eyebrow">
          {{ conflictsOnly ? 'where the packet disagrees with itself' : 'every claim, grouped by what it is about' }}
        </p>
        <h1 class="head__title">
          {{ conflictsOnly ? 'Conflicts' : 'Evidence' }}
        </h1>
        <p class="head__note">
          <template v-if="conflictsOnly">
            In each queue below the latest claim outranks the others only
            because it is latest. Nothing in the packet resolves them, so
            everything derived from one is marked
            <span class="taint">premise contested</span>.
          </template>
          <template v-else>
            Latest claim on top. Nothing is ever deleted — a superseded claim
            stays readable with both citations.
          </template>
        </p>
      </div>
      <input
        v-if="!conflictsOnly"
        v-model="filter"
        class="search"
        type="search"
        placeholder="filter by subject…"
        aria-label="Filter queues by subject"
      />
    </header>

    <p v-if="!queues.length" class="empty">
      Nothing matches. Clear the filter to see every queue.
    </p>

    <article
      v-for="q in queues"
      :key="q.key"
      class="panel queue"
      :class="{ hatched: q.mode === 'assumed' }"
    >
      <div class="panel__head">
        <h2 class="panel__title">{{ q.subject }}</h2>
        <span class="queue__pred">{{ q.predicate }}</span>
        <span class="queue__mode" :class="`queue__mode--${q.mode}`">
          {{ q.mode_label || q.mode }}
        </span>
      </div>
      <div class="panel__body">
        <ClaimRow
          v-for="id in q.claims"
          :key="id"
          :id="id"
          show-value
          :head="id === q.head"
          :superseded="q.superseded.includes(id)"
          :refuted-by="rebuttals[id] ?? []"
        />
      </div>
    </article>

    <section v-if="conflictsOnly && Object.keys(rebuttals).length" class="panel">
      <div class="panel__head">
        <h2 class="panel__title">Rebuttals</h2>
        <span class="queue__pred">a direct contradiction of another party</span>
      </div>
      <div class="panel__body">
        <div v-for="(refuters, target) in rebuttals" :key="target" class="rebuttal">
          <ClaimRow :id="target" />
          <div class="rebuttal__against">
            <ClaimRow v-for="r in refuters" :key="r" :id="r" head />
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.evidence {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.head {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  gap: 24px;
  flex-wrap: wrap;
  padding-bottom: 18px;
  border-bottom: 1px solid var(--line);
  margin-bottom: 8px;
}

.head__title {
  font-size: 34px;
  margin: 4px 0 6px;
}

.head__note {
  margin: 0;
  max-width: 78ch;
  font-size: 13px;
  color: var(--chalk-faint);
}

.taint {
  color: var(--contested);
}

.search {
  font-family: var(--mono);
  font-size: 12.5px;
  padding: 7px 11px;
  background: var(--ink-1);
  border: 1px solid var(--line);
  color: var(--chalk);
  min-width: 240px;
}

.search:focus {
  border-color: var(--cyan);
  outline: none;
}

.empty {
  color: var(--chalk-faint);
  font-size: 13px;
}

.queue__pred {
  font-family: var(--mono);
  font-size: 11.5px;
  color: var(--chalk-faint);
  flex: 1;
}

.queue__mode {
  font-family: var(--display);
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}

.queue__mode--assumed {
  color: var(--contested);
}
.queue__mode--resolved {
  color: var(--met);
}
.queue__mode--single {
  color: var(--chalk-faint);
}

.rebuttal {
  padding: 6px 0 14px;
}

.rebuttal__against {
  margin-left: 26px;
  border-left: 2px solid var(--contested);
  padding-left: 14px;
}
</style>
