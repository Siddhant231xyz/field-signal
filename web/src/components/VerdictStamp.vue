<script setup>
import { computed } from 'vue'

/* The quote arrives stamped "PRICING SUBMITTED — NOT AUTHORISED". This is the
   stamp Maya Chen has not applied, rendered as the thing it actually is. */

const props = defineProps({ decision: { type: Object, required: true } })

const contested = computed(() => props.decision.basis === 'contested')
const proceed = computed(() => props.decision.recommendation === 'PROCEED')
</script>

<template>
  <div class="stamp" :class="{ 'stamp--go': proceed, hatched: contested }">
    <div class="stamp__rule" />
    <div class="stamp__word">{{ decision.recommendation }}</div>
    <div class="stamp__sub">
      {{ contested ? 'basis contested' : 'basis settled' }}
    </div>
    <div class="stamp__rule" />
    <div class="stamp__count">
      {{ decision.blocking.length }} condition{{ decision.blocking.length === 1 ? '' : 's' }} not met
    </div>
  </div>
</template>

<style scoped>
.stamp {
  --stamp: var(--unmet);
  transform: rotate(-3.2deg);
  border: 3px solid var(--stamp);
  outline: 1px solid var(--stamp);
  outline-offset: 3px;
  color: var(--stamp);
  padding: 12px 26px 10px;
  text-align: center;
  min-width: 232px;
  background: color-mix(in srgb, var(--unmet) 7%, transparent);
  animation: press 0.5s cubic-bezier(0.2, 1.4, 0.4, 1) both;
}

.stamp--go {
  --stamp: var(--met);
  background: color-mix(in srgb, var(--met) 7%, transparent);
}

.stamp__word {
  font-family: var(--display);
  font-size: 54px;
  font-weight: 700;
  line-height: 0.92;
  letter-spacing: 0.06em;
}

.stamp__sub {
  font-family: var(--display);
  font-size: 14px;
  font-weight: 600;
  letter-spacing: 0.3em;
  text-transform: uppercase;
  margin-bottom: 6px;
}

.stamp__rule {
  height: 2px;
  background: currentColor;
  margin: 5px 0;
}

.stamp__count {
  font-family: var(--mono);
  font-size: 11px;
  letter-spacing: 0.04em;
  padding-top: 5px;
}

@keyframes press {
  from {
    opacity: 0;
    transform: rotate(-3.2deg) scale(1.5);
  }
  to {
    opacity: 1;
    transform: rotate(-3.2deg) scale(1);
  }
}
</style>
