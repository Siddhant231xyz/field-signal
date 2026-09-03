<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { actions, store } from '../store'

/* A floating assistant, not a sheet: a question about the evidence is
   something you ask *while* looking at something else, so it has to be
   reachable from every view without navigating away from what prompted it.

   It answers from the selected revision only. That is the whole point — the
   same question against v1 and v4 should give different answers, and the
   header says which one you are asking. */

const open = ref(false)
const draft = ref('')
const box = ref(null)
const log = ref(null)

const key = computed(() => String(store.current))
const messages = computed(() => store.chat.threads[key.value] ?? [])
const pending = computed(() => Boolean(store.chat.pending[key.value]))
const error = computed(() => store.chat.errors[key.value] ?? null)

async function toggle() {
  open.value = !open.value
  if (open.value) {
    await nextTick()
    box.value?.focus()
    scrollDown()
  }
}

function scrollDown() {
  nextTick(() => {
    if (log.value) log.value.scrollTop = log.value.scrollHeight
  })
}

async function send() {
  const question = draft.value.trim()
  if (!question || pending.value) return
  draft.value = ''
  scrollDown()
  await actions.askGraph(question)
  scrollDown()
}

function onKey(event) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    send()
  }
}

watch(messages, scrollDown, { deep: true })
</script>

<template>
  <div class="chat">
    <section
      v-show="open"
      class="chat__panel"
      role="dialog"
      aria-label="Ask the evidence"
    >
      <header class="chat__head">
        <div>
          <p class="chat__title">Ask the evidence</p>
          <p class="chat__sub">
            answering from <strong>v{{ store.current }}</strong> ·
            {{ store.ledger.claims.length }} claims
          </p>
        </div>
        <button
          v-if="messages.length"
          class="chat__icon"
          title="Clear this thread"
          @click="actions.clearChat()"
        >clear</button>
        <button class="chat__icon" aria-label="Close" @click="open = false">×</button>
      </header>

      <div ref="log" class="chat__log">
        <div v-if="!messages.length" class="chat__empty">
          <p>
            Every answer is read out of revision <strong>v{{ store.current }}</strong>
            and cited back to the claim it came from. Select another revision and
            the same question may get a different answer.
          </p>
          <ul>
            <li>Has anyone with authority approved the $2,850?</li>
            <li>How far west did the duct actually move?</li>
            <li>What is still unknown before Thursday?</li>
          </ul>
        </div>

        <article
          v-for="(m, i) in messages"
          :key="i"
          class="msg"
          :class="`msg--${m.role}`"
        >
          <p class="msg__text">{{ m.content }}</p>

          <p v-if="m.caveat" class="msg__caveat">{{ m.caveat }}</p>

          <details v-if="m.citations?.length" class="msg__cites">
            <summary>{{ m.citations.length }} citation{{ m.citations.length === 1 ? '' : 's' }}</summary>
            <div v-for="c in m.citations" :key="c.claim" class="cite-row">
              <span class="cite-row__id">{{ c.claim }}</span>
              <span class="cite">{{ c.citation }}</span>
              <span class="cite-row__who">{{ c.author }}</span>
              <p class="verbatim cite-row__text">{{ c.support }}</p>
            </div>
          </details>
        </article>

        <p v-if="pending" class="chat__pending">
          <span class="chat__spin" aria-hidden="true" />
          reading v{{ store.current }}…
        </p>

        <p v-if="error" class="chat__error">{{ error }}</p>
      </div>

      <form class="chat__form" @submit.prevent="send">
        <textarea
          ref="box"
          v-model="draft"
          class="chat__box"
          rows="2"
          :placeholder="`Ask about the evidence in v${store.current}`"
          :disabled="pending"
          @keydown="onKey"
        />
        <button class="chat__send" type="submit" :disabled="pending || !draft.trim()">
          ask
        </button>
      </form>
    </section>

    <button
      class="chat__fab"
      :class="{ 'chat__fab--open': open, 'chat__fab--busy': pending }"
      :aria-expanded="open"
      aria-label="Ask the evidence"
      @click="toggle"
    >
      <svg v-if="!open" viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">
        <!-- three nodes and two edges: this asks the graph, not a search box -->
        <path d="M6 7 L12 12 L18 7" fill="none" stroke="currentColor" stroke-width="1.6" />
        <path d="M12 12 L12 18" fill="none" stroke="currentColor" stroke-width="1.6" />
        <circle cx="6" cy="6" r="2.4" fill="currentColor" />
        <circle cx="18" cy="6" r="2.4" fill="currentColor" />
        <circle cx="12" cy="12" r="2.4" fill="currentColor" />
        <circle cx="12" cy="19" r="2.4" fill="currentColor" />
      </svg>
      <span v-else class="chat__fab-x" aria-hidden="true">×</span>
      <span v-if="!open" class="chat__fab-rev">v{{ store.current }}</span>
    </button>
  </div>
</template>

<style scoped>
.chat {
  position: fixed;
  right: 22px;
  bottom: 22px;
  z-index: 60;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 12px;
}

/* --- the button -------------------------------------------------------- */

.chat__fab {
  position: relative;
  width: 54px;
  height: 54px;
  border-radius: 50%;
  border: 1px solid var(--cyan);
  background: var(--ink-1);
  color: var(--cyan);
  cursor: pointer;
  display: grid;
  place-items: center;
  box-shadow: 0 6px 20px rgb(0 0 0 / 0.45);
  transition: transform 0.15s, background 0.15s;
}

.chat__fab:hover {
  transform: translateY(-2px);
  background: color-mix(in srgb, var(--cyan) 16%, var(--ink-1));
}

.chat__fab--open {
  border-color: var(--line);
  color: var(--chalk-dim);
}

.chat__fab-x {
  font-size: 26px;
  line-height: 1;
}

.chat__fab-rev {
  position: absolute;
  bottom: -3px;
  right: -3px;
  font-family: var(--mono);
  font-size: 9.5px;
  padding: 1px 4px;
  border: 1px solid var(--cyan);
  background: var(--ink);
  color: var(--cyan);
}

.chat__fab--busy::after {
  content: '';
  position: absolute;
  inset: -5px;
  border-radius: 50%;
  border: 1.5px solid transparent;
  border-top-color: var(--cyan);
  animation: spin 0.9s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* --- the panel --------------------------------------------------------- */

.chat__panel {
  width: min(400px, calc(100vw - 44px));
  height: min(560px, calc(100vh - 130px));
  display: flex;
  flex-direction: column;
  border: 1px solid var(--line);
  background: color-mix(in srgb, var(--ink-1) 96%, transparent);
  backdrop-filter: blur(10px);
  box-shadow: 0 14px 44px rgb(0 0 0 / 0.55);
}

.chat__head {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 11px 13px;
  border-bottom: 1px solid var(--line);
  background: color-mix(in srgb, var(--ink-2) 60%, transparent);
}

.chat__title {
  font-family: var(--display);
  font-size: 16px;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  margin: 0;
}

.chat__sub {
  margin: 1px 0 0;
  font-size: 11.5px;
  color: var(--chalk-faint);
}

.chat__sub strong {
  color: var(--cyan);
  font-weight: 500;
}

.chat__icon {
  background: none;
  border: 0;
  color: var(--chalk-faint);
  cursor: pointer;
  font-family: var(--display);
  font-size: 13px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  padding: 2px 4px;
}

.chat__icon:last-child {
  font-size: 20px;
  line-height: 1;
  margin-left: auto;
}

.chat__icon:hover { color: var(--chalk); }

.chat__log {
  flex: 1;
  overflow-y: auto;
  padding: 13px;
  display: flex;
  flex-direction: column;
  gap: 11px;
}

.chat__empty {
  font-size: 12.5px;
  color: var(--chalk-faint);
  line-height: 1.55;
}

.chat__empty strong { color: var(--cyan); font-weight: 500; }

.chat__empty ul {
  margin: 12px 0 0;
  padding-left: 16px;
}

.chat__empty li {
  margin-bottom: 5px;
  font-style: italic;
}

.msg {
  font-size: 13px;
  line-height: 1.5;
}

.msg--user {
  align-self: flex-end;
  max-width: 88%;
  background: color-mix(in srgb, var(--cyan) 14%, transparent);
  border: 1px solid color-mix(in srgb, var(--cyan) 35%, transparent);
  padding: 7px 11px;
}

.msg--assistant {
  border-left: 2px solid var(--line);
  padding-left: 11px;
}

.msg__text {
  margin: 0;
  white-space: pre-wrap;
}

.msg__caveat {
  margin: 8px 0 0;
  padding-left: 9px;
  border-left: 2px solid var(--unknown);
  font-size: 12px;
  color: var(--unknown);
}

.msg__cites {
  margin-top: 9px;
}

.msg__cites summary {
  cursor: pointer;
  font-family: var(--display);
  font-size: 12px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--cyan);
}

.cite-row {
  padding: 7px 0;
  border-top: 1px solid var(--line-soft);
  display: flex;
  flex-wrap: wrap;
  gap: 3px 9px;
}

.cite-row__id {
  font-family: var(--mono);
  font-size: 11px;
  color: var(--chalk);
}

.cite-row__who {
  font-size: 11.5px;
  color: var(--chalk-faint);
}

.cite-row__text {
  flex-basis: 100%;
  margin: 2px 0 0;
  font-size: 11.5px;
}

.chat__pending {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  font-size: 12.5px;
  color: var(--cyan);
}

.chat__spin {
  width: 10px;
  height: 10px;
  border: 2px solid color-mix(in srgb, var(--cyan) 30%, transparent);
  border-top-color: var(--cyan);
  border-radius: 50%;
  animation: spin 0.85s linear infinite;
}

.chat__error {
  margin: 0;
  padding: 8px 10px;
  border: 1px solid var(--unmet);
  color: var(--unmet);
  font-size: 12px;
}

.chat__form {
  display: flex;
  gap: 8px;
  padding: 10px;
  border-top: 1px solid var(--line);
  align-items: flex-end;
}

.chat__box {
  flex: 1;
  resize: none;
  font-family: var(--body);
  font-size: 13px;
  padding: 7px 9px;
  background: var(--ink);
  border: 1px solid var(--line);
  color: var(--chalk);
}

.chat__box:focus {
  outline: none;
  border-color: var(--cyan);
}

.chat__send {
  font-family: var(--display);
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  padding: 8px 14px;
  background: color-mix(in srgb, var(--cyan) 14%, transparent);
  border: 1px solid var(--cyan);
  color: var(--cyan);
  cursor: pointer;
}

.chat__send:disabled {
  opacity: 0.4;
  cursor: not-allowed;
  border-color: var(--line);
  color: var(--chalk-faint);
  background: none;
}

@media (max-width: 600px) {
  .chat { right: 12px; bottom: 12px; }
}
</style>
