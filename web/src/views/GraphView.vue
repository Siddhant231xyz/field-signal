<script setup>
import { onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import ForceGraph3D from '3d-force-graph'
import * as THREE from 'three'
import { tooltip } from '../escape'
import { view } from '../store'

/* The same edges the CLI reasons over, in space. Nothing here decides
   anything — Python already did. */

const host = ref(null)
const graph = shallowRef(null)
const selected = ref(null)
const focus = ref('all')
const layered = ref(true)
let fitted = false

const NODE_COLOUR = {
  decision: '#e6f2fb',
  condition: { met: '#3ddc97', unmet: '#ff6b63', unknown: '#ffb020' },
  exposure: '#ff8a5c',
  claim: '#4cc9f0',
  source: '#7aa8c9',
  person: '#c77dff',
}

const LINK_COLOUR = {
  gates: '#ffb020',
  depends_on: '#ff6b63',
  supports: '#4cc9f0',
  supports_exposure: '#ff8a5c',
  noted: '#ffb020',
  exposes: '#ff8a5c',
  from_source: '#2f5b7d',
  stated_by: '#6b4a8a',
  cites_basis: '#c77dff',
  supersedes: '#3ddc97',
  refutes: '#c77dff',
}

const LEGEND = [
  { key: 'decision', label: 'the decision', colour: '#e6f2fb' },
  { key: 'condition', label: 'conditions ahead of her', colour: '#ffb020' },
  { key: 'exposure', label: 'already true', colour: '#ff8a5c' },
  { key: 'claim', label: 'claims', colour: '#4cc9f0' },
  { key: 'source', label: 'sources', colour: '#7aa8c9' },
  { key: 'person', label: 'people', colour: '#c77dff' },
]

function colourOf(node) {
  const c = NODE_COLOUR[node.type]
  if (node.type === 'condition') return c[node.status] ?? '#ffb020'
  if (node.type === 'source' && node.present === false) return '#ff6b63'
  if (node.type === 'claim' && node.gating_allowed === false) return '#ffb020'
  return c ?? '#9fbdd4'
}

function sizeOf(node) {
  return { decision: 11, condition: 7, exposure: 6, source: 5, person: 5 }[node.type] ?? 3
}

/* A canvas sprite label. Written by hand rather than pulling in a text
   package — the graph is unreadable without labels, and this is 20 lines. */
const LABELLED = new Set(['decision', 'condition', 'exposure', 'person', 'source'])

function labelFor(node) {
  if (!LABELLED.has(node.type)) return null
  const text = node.label.length > 34 ? node.label.slice(0, 33) + '…' : node.label
  const pad = 8
  const size = node.type === 'decision' ? 34 : 26

  const canvas = document.createElement('canvas')
  const ctx = canvas.getContext('2d')
  ctx.font = `600 ${size}px "Barlow Condensed", sans-serif`
  canvas.width = ctx.measureText(text).width + pad * 2
  canvas.height = size + pad * 2

  const c = ctx // re-fetching context after a resize clears it
  c.font = `600 ${size}px "Barlow Condensed", sans-serif`
  c.fillStyle = 'rgba(7, 23, 38, 0.78)'
  c.fillRect(0, 0, canvas.width, canvas.height)
  c.fillStyle = colourOf(node)
  c.textBaseline = 'middle'
  c.fillText(text, pad, canvas.height / 2)

  const sprite = new THREE.Sprite(
    new THREE.SpriteMaterial({
      map: new THREE.CanvasTexture(canvas),
      depthWrite: false,
      transparent: true,
    }),
  )
  const scale = node.type === 'decision' ? 0.34 : 0.26
  sprite.scale.set(canvas.width * scale, canvas.height * scale, 1)
  sprite.position.set(0, sizeOf(node) + 6, 0)
  return sprite
}

function build() {
  if (!host.value || !view.value) return
  const data = {
    nodes: view.value.graph.nodes.map((n) => ({ ...n })),
    links: view.value.graph.links.map((l) => ({ ...l })),
  }

  if (!graph.value) {
    graph.value = ForceGraph3D()(host.value)
      .backgroundColor('#071726')
      .showNavInfo(false)
      .nodeColor(colourOf)
      .nodeVal(sizeOf)
      .nodeOpacity(0.92)
      .nodeResolution(16)
      // nodeLabel is inserted as markup, so ledger text is escaped first.
      .nodeLabel(tooltip)
      .linkColor((l) => LINK_COLOUR[l.kind] ?? '#2f5b7d')
      .linkWidth((l) => (['gates', 'depends_on'].includes(l.kind) ? 1.4 : 0.5))
      .linkOpacity(0.42)
      .linkDirectionalParticles((l) => (l.kind === 'gates' ? 3 : 0))
      .linkDirectionalParticleWidth(1.8)
      .linkDirectionalParticleSpeed(0.006)
      .linkDirectionalArrowLength(3.2)
      .linkDirectionalArrowRelPos(1)
      .onNodeClick((node) => {
        selected.value = node
        const d = 130
        const r = 1 + d / Math.hypot(node.x || 1, node.y || 1, node.z || 1)
        graph.value.cameraPosition(
          { x: (node.x || 0) * r, y: (node.y || 0) * r, z: (node.z || 0) * r },
          node,
          900,
        )
      })
      .onBackgroundClick(() => (selected.value = null))
      .nodeThreeObjectExtend(true)
      .nodeThreeObject(labelFor)
      // The evidence really is a DAG — person → claim → condition → decision.
      // cites_basis points back at a source, so cycles exist; skip them
      // rather than refusing to lay the graph out at all.
      .onDagError(() => {})
      .onEngineStop(() => {
        if (fitted) return
        fitted = true
        graph.value.zoomToFit(700, 70)
      })

    graph.value.d3Force('charge').strength(-300)
    graph.value.d3Force('link').distance(42)
  }

  applyLayout()
  graph.value.graphData(data)
  resize()
}

function applyLayout() {
  if (!graph.value) return
  fitted = false
  graph.value
    .dagMode(layered.value ? 'bu' : null)
    .dagLevelDistance(layered.value ? 105 : undefined)
  graph.value.d3ReheatSimulation()
}

function applyFocus() {
  if (!graph.value) return
  const f = focus.value
  graph.value
    .nodeVisibility((n) => f === 'all' || n.type === f || n.type === 'decision')
    .linkVisibility((l) => {
      if (f === 'all') return true
      const ends = [l.source, l.target].map((e) => (typeof e === 'object' ? e : { type: '' }))
      return ends.every((e) => e.type === f || e.type === 'decision')
    })
}

function resize() {
  if (!graph.value || !host.value) return
  graph.value.width(host.value.clientWidth).height(host.value.clientHeight)
}

function fit() {
  graph.value?.zoomToFit(700, 70)
}

onMounted(() => {
  build()
  window.addEventListener('resize', resize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', resize)
  graph.value?._destructor?.()
  graph.value = null
})

watch(view, build)
watch(focus, applyFocus)
watch(layered, applyLayout)
</script>

<template>
  <div class="graph">
    <div ref="host" class="graph__canvas" />

    <div class="graph__legend panel">
      <div class="panel__head">
        <h3 class="panel__title">The evidence, in space</h3>
      </div>
      <div class="panel__body">
        <p class="graph__hint">
          Drag to orbit, scroll to zoom, click a node to fly to it. Arrows point
          the way support flows — from a person, through a claim, into a
          condition, up to the decision.
        </p>
        <ul class="legend">
          <li v-for="l in LEGEND" :key="l.key">
            <button
              class="legend__item"
              :class="{ 'legend__item--off': focus !== 'all' && focus !== l.key }"
              @click="focus = focus === l.key ? 'all' : l.key"
            >
              <span class="legend__dot" :style="{ background: l.colour }" />
              {{ l.label }}
            </button>
          </li>
        </ul>
        <div class="graph__actions">
          <button class="btn" :class="{ 'btn--on': layered }" @click="layered = !layered">
            {{ layered ? 'layered' : 'free float' }}
          </button>
          <button class="btn" @click="focus = 'all'">show all</button>
          <button class="btn" @click="fit">fit</button>
        </div>
        <p class="graph__hint graph__hint--last">
          Layered stacks the decision on top of everything holding it up, with
          the people who spoke at the base. Free float lets the clusters find
          their own shape.
        </p>
      </div>
    </div>

    <aside v-if="selected" class="graph__detail panel">
      <div class="panel__head">
        <span class="eyebrow">{{ selected.type }}</span>
        <button class="close" aria-label="Close" @click="selected = null">×</button>
      </div>
      <div class="panel__body">
        <h3 class="detail__label">{{ selected.label }}</h3>
        <p v-if="selected.citation" class="cite">{{ selected.citation }}</p>
        <p class="detail__text" :class="{ verbatim: selected.type === 'claim' }">
          {{ selected.detail }}
        </p>
        <p v-if="selected.gating_allowed === false" class="detail__warn">
          This claim may never gate a decision.
        </p>
        <p v-if="selected.present === false" class="detail__warn">
          Cited by a claim, but not supplied in the packet.
        </p>
      </div>
    </aside>
  </div>
</template>

<style scoped>
.graph {
  position: absolute;
  inset: 0;
}

.graph__canvas {
  position: absolute;
  inset: 0;
}

.graph__legend {
  position: absolute;
  top: 20px;
  left: 20px;
  width: 274px;
  backdrop-filter: blur(8px);
  background: color-mix(in srgb, var(--ink-1) 82%, transparent);
}

.graph__hint {
  margin: 0 0 14px;
  font-size: 12.5px;
  color: var(--chalk-faint);
  line-height: 1.5;
}

.legend {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.legend__item {
  display: flex;
  align-items: center;
  gap: 9px;
  width: 100%;
  padding: 4px 6px;
  background: none;
  border: 0;
  cursor: pointer;
  font-size: 12.5px;
  color: var(--chalk-dim);
  text-align: left;
}

.legend__item:hover {
  background: color-mix(in srgb, var(--cyan) 10%, transparent);
  color: var(--chalk);
}

.legend__item--off {
  opacity: 0.35;
}

.legend__dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  flex: none;
}

.graph__actions {
  display: flex;
  gap: 8px;
  margin-top: 14px;
}

.btn {
  font-family: var(--display);
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  padding: 5px 11px;
  background: none;
  border: 1px solid var(--line);
  color: var(--chalk-dim);
  cursor: pointer;
}

.btn:hover {
  border-color: var(--cyan);
  color: var(--cyan);
}

.btn--on {
  border-color: var(--cyan);
  color: var(--cyan);
  background: color-mix(in srgb, var(--cyan) 12%, transparent);
}

.graph__hint--last {
  margin: 12px 0 0;
}

.graph__detail {
  position: absolute;
  bottom: 20px;
  right: 20px;
  width: 330px;
  max-height: 46%;
  overflow: auto;
  backdrop-filter: blur(8px);
  background: color-mix(in srgb, var(--ink-1) 88%, transparent);
}

.graph__detail .panel__head {
  justify-content: space-between;
  align-items: center;
}

.close {
  background: none;
  border: 0;
  color: var(--chalk-faint);
  font-size: 20px;
  line-height: 1;
  cursor: pointer;
  padding: 0 4px;
}
.close:hover {
  color: var(--chalk);
}

.detail__label {
  font-size: 19px;
  margin-bottom: 4px;
}

.detail__text {
  font-size: 13px;
  color: var(--chalk-dim);
  margin: 10px 0 0;
}

.detail__warn {
  margin: 12px 0 0;
  padding: 7px 10px;
  border-left: 2px solid var(--unknown);
  font-size: 12px;
  color: var(--unknown);
}

@media (max-width: 860px) {
  .graph__legend,
  .graph__detail {
    position: static;
    width: auto;
    margin: 12px;
  }
}
</style>

<style>
/* 3d-force-graph injects the tooltip outside the scoped tree. */
.g-tip {
  font-family: 'IBM Plex Sans', sans-serif;
  background: #0b2337;
  border: 1px solid #1c4462;
  padding: 7px 11px;
  color: #e6f2fb;
  font-size: 13px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  max-width: 300px;
}

.g-tip__type {
  font-family: 'Barlow Condensed', sans-serif;
  font-size: 11px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: #6b8ca8;
}

.g-tip__cite {
  font-family: 'IBM Plex Mono', monospace;
  font-size: 11px;
  color: #4cc9f0;
}
</style>
