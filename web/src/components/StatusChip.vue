<script setup>
import { computed } from 'vue'

const props = defineProps({
  status: { type: String, required: true },
  basis: { type: String, default: 'settled' },
})

const GLYPH = { met: '✓', unmet: '✗', unknown: '?', exposed: '!' }

const glyph = computed(() => GLYPH[props.status] ?? '·')
const contested = computed(() => props.basis === 'contested')
</script>

<template>
  <span class="chip" :class="`chip--${status}`">
    <span class="chip__glyph">{{ glyph }}<template v-if="contested">*</template></span>
    <span>{{ status }}</span>
    <span v-if="contested" class="chip__taint">— premise contested</span>
  </span>
</template>

<style scoped>
.chip__taint {
  color: var(--contested);
  font-weight: 500;
  letter-spacing: 0.04em;
}
</style>
