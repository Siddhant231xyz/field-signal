<script setup>
import { computed } from 'vue'
import { claims } from '../store'

const props = defineProps({
  id: { type: String, required: true },
  head: { type: Boolean, default: false },
  superseded: { type: Boolean, default: false },
  refutedBy: { type: Array, default: () => [] },
  showValue: { type: Boolean, default: false },
})

const claim = computed(() => claims.value[props.id])
</script>

<template>
  <div
    v-if="claim"
    class="claim"
    :class="{ 'claim--head': head, 'claim--dead': superseded, 'claim--barred': !claim.gating_allowed }"
  >
    <div class="claim__marker" :aria-hidden="true">{{ head ? '▶' : '' }}</div>

    <div class="claim__meta">
      <span class="claim__id">{{ claim.id }}</span>
      <span class="claim__kind">{{ claim.kind }}</span>
    </div>

    <div class="claim__content">
      <div v-if="showValue" class="claim__value">{{ claim.value }}</div>
      <p class="verbatim claim__support">{{ claim.support }}</p>
      <div class="claim__tags">
        <span class="claim__author">{{ claim.author }}</span>
        <span class="cite">{{ claim.citation }}</span>
        <span v-if="superseded" class="tag tag--dead">superseded</span>
        <span v-if="refutedBy.length" class="tag tag--refuted">
          refuted by {{ refutedBy.join(', ') }}
        </span>
        <span v-if="!claim.gating_allowed" class="tag tag--barred">
          may never gate a decision
        </span>
        <span v-if="claim.cites_basis" class="tag tag--basis">
          leans on {{ claim.cites_basis }}
        </span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.claim {
  display: grid;
  grid-template-columns: 16px 96px 1fr;
  gap: 12px;
  padding: 11px 0;
  border-top: 1px solid var(--line-soft);
  align-items: start;
}

.claim--head {
  background: linear-gradient(90deg, color-mix(in srgb, var(--cyan) 8%, transparent), transparent 60%);
}

.claim--dead {
  opacity: 0.5;
}
.claim--dead .claim__support {
  text-decoration: line-through;
  text-decoration-color: var(--chalk-faint);
}

.claim--barred {
  border-left: 2px solid var(--unknown);
  padding-left: 10px;
  margin-left: -12px;
}

.claim__marker {
  color: var(--cyan);
  font-family: var(--mono);
  font-size: 11px;
  line-height: 1.9;
}

.claim__meta {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.claim__id {
  font-family: var(--mono);
  font-size: 11.5px;
  color: var(--chalk);
}

.claim__kind {
  font-family: var(--display);
  font-size: 11px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--chalk-faint);
}

.claim__value {
  font-family: var(--display);
  font-size: 16px;
  letter-spacing: 0.02em;
  color: var(--chalk);
  margin-bottom: 2px;
}

.claim__support {
  margin: 0;
}

.claim__tags {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px 14px;
  margin-top: 6px;
}

.claim__author {
  font-size: 12px;
  color: var(--chalk-dim);
}

.tag {
  font-family: var(--display);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  padding: 1px 7px;
  border: 1px solid currentColor;
}

.tag--dead {
  color: var(--chalk-faint);
}
.tag--refuted {
  color: var(--contested);
}
.tag--barred {
  color: var(--unknown);
}
.tag--basis {
  color: var(--cyan);
}
</style>
