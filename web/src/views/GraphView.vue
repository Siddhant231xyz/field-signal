<script setup>
import { onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import ForceGraph2D from 'force-graph'
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
const mode = ref('2d')
let graphMode = null
let graphData = { nodes: [], links: [] }
let hovered = null
let neighbours = new Set()
let fitted = false
let palette = {}

const NODE_TOKEN = {
  decision: 'chalk',
  exposure: 'exposed',
  queue: 'met',
  claim: 'cyan',
  source: 'chalk-dim',
  person: 'contested',
}

const LINK_TOKEN = {
  gates: 'unknown',
  depends_on: 'unmet',
  supports: 'cyan',
  supports_exposure: 'exposed',
  noted: 'unknown',
  exposes: 'exposed',
  from_source: 'line',
  stated_by: 'contested',
  cites_basis: 'contested',
  supersedes: 'met',
  refutes: 'contested',
  in_queue: 'met',
}

const LEGEND = [
  { key: 'decision', label: 'the decision', token: 'chalk' },
  { key: 'condition', label: 'conditions ahead of her', token: 'unknown' },
  { key: 'exposure', label: 'already true', token: 'exposed' },
  { key: 'queue', label: 'claims about one thing', token: 'met' },
  { key: 'claim', label: 'claims', token: 'cyan' },
  { key: 'source', label: 'sources', token: 'chalk-dim' },
  { key: 'person', label: 'people', token: 'contested' },
]

const RELATIONSHIPS = Object.keys(LINK_TOKEN)

function readTokens() {
  const style = getComputedStyle(document.documentElement)
  const token = (name) => style.getPropertyValue(`--${name}`).trim()
  palette = {
    ink: token('ink'),
    ink1: token('ink-1'),
    line: token('line'),
    chalk: token('chalk'),
    chalkDim: token('chalk-dim'),
    chalkFaint: token('chalk-faint'),
    cyan: token('cyan'),
    unmet: token('unmet'),
    unknown: token('unknown'),
    met: token('met'),
    contested: token('contested'),
    exposed: token('exposed'),
    display: token('display'),
  }
}

function tokenColour(name) {
  const key = name.replace(/-([a-z0-9])/g, (_, c) => c.toUpperCase())
  return palette[key] || palette.chalkDim
}

function colourOf(node) {
  if (node.type === 'condition') return tokenColour(node.status || 'unknown')
  if (node.type === 'source' && node.present === false) return palette.unmet
  if (node.type === 'queue') return tokenColour(node.status === 'assumed' ? 'contested' : 'met')
  if (node.type === 'claim' && node.gating_allowed === false) return palette.unknown
  return tokenColour(NODE_TOKEN[node.type] || 'chalk-dim')
}

function linkColour(link) {
  if (hovered && !linkTouches(link, hovered.id)) return palette.line
  return tokenColour(LINK_TOKEN[link.kind] || 'line')
}

function sizeOf(node) {
  return { decision: 11, condition: 7, exposure: 6, queue: 5, source: 5, person: 5 }[node.type] ?? 3
}

function renderRadius(node, globalScale) {
  const minimumPixels = node.type === 'decision' ? 9 : 6
  return Math.max(sizeOf(node), minimumPixels / globalScale)
}

function endpointId(endpoint) {
  return typeof endpoint === 'object' ? endpoint.id : endpoint
}

function linkTouches(link, id) {
  return endpointId(link.source) === id || endpointId(link.target) === id
}

function statusTag(node) {
  if (node.type === 'condition' && node.status) return `[${node.status.toUpperCase()}] `
  if (node.type === 'source' && node.present === false) return '[MISSING] '
  if (node.type === 'queue' && node.status === 'assumed') return '[CONTESTED] '
  if (node.type === 'claim' && node.gating_allowed === false) return '[NON-GATING] '
  return ''
}

function shortLabel(node) {
  const text = `${statusTag(node)}${node.label}`
  return text.length > 38 ? `${text.slice(0, 37)}…` : text
}

function relationshipLabel(kind) {
  return kind.replaceAll('_', ' ')
}

function motionDuration(ms) {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : ms
}

function setHover(node) {
  hovered = node
  neighbours = new Set(node ? [node.id] : [])
  if (node) {
    graphData.links.forEach((link) => {
      if (linkTouches(link, node.id)) {
        neighbours.add(endpointId(link.source))
        neighbours.add(endpointId(link.target))
      }
    })
  }
  if (host.value) host.value.style.cursor = node ? 'pointer' : 'grab'
  graph.value?.refresh?.()
}

/* Claims are 115 of the 166 nodes. Labelling every one at rest buries the
   structure the graph exists to show, so a claim earns its label by being
   hovered, selected, part of what you are hovering, or zoomed into. Everything
   structural — the decision, conditions, exposures, queues, sources, people —
   stays labelled always. */
const ALWAYS_LABELLED = new Set(['decision', 'condition', 'exposure', 'queue', 'person'])

function labelVisible(node, globalScale) {
  if (ALWAYS_LABELLED.has(node.type)) return true
  if (selected.value?.id === node.id || hovered?.id === node.id) return true
  if (hovered && neighbours.has(node.id)) return true
  return globalScale >= 1.6
}

function paintNode(node, ctx, globalScale) {
  const dimmed = hovered && !neighbours.has(node.id)
  const radius = renderRadius(node, globalScale)
  const fontPx = node.type === 'decision' ? 14 : 12
  const fontSize = Math.max(3.5, fontPx / globalScale)
  const label = shortLabel(node)
  const gap = 5 / globalScale

  ctx.save()
  ctx.globalAlpha = dimmed ? 0.13 : 0.96
  ctx.beginPath()
  ctx.arc(node.x, node.y, radius, 0, 2 * Math.PI)
  ctx.fillStyle = colourOf(node)
  ctx.fill()

  if (selected.value?.id === node.id || hovered?.id === node.id) {
    ctx.lineWidth = 2 / globalScale
    ctx.strokeStyle = palette.chalk
    ctx.stroke()
  }

  if (!labelVisible(node, globalScale)) {
    ctx.restore()
    return
  }

  ctx.font = `600 ${fontSize}px ${palette.display}`
  const textWidth = ctx.measureText(label).width
  const textX = node.x + radius + gap
  const textY = node.y
  const padX = 4 / globalScale
  const padY = 3 / globalScale
  ctx.fillStyle = palette.ink1
  ctx.fillRect(
    textX - padX,
    textY - fontSize / 2 - padY,
    textWidth + padX * 2,
    fontSize + padY * 2,
  )
  ctx.fillStyle = dimmed ? palette.chalkFaint : palette.chalk
  ctx.textAlign = 'left'
  ctx.textBaseline = 'middle'
  ctx.fillText(label, textX, textY)
  ctx.restore()
}

function paintLinkLabel(link, ctx, globalScale) {
  if (hovered && !linkTouches(link, hovered.id)) return
  // All kinds stay visible in the key; canvas labels appear when there is
  // enough room, or immediately for the relationships under the pointer.
  if (!hovered && globalScale < 1.15) return
  const source = link.source
  const target = link.target
  if (!source || !target || !Number.isFinite(source.x) || !Number.isFinite(target.x)) return

  const label = relationshipLabel(link.kind)
  const fontSize = Math.max(3, 9.5 / globalScale)
  const x = (source.x + target.x) / 2
  const y = (source.y + target.y) / 2
  let angle = Math.atan2(target.y - source.y, target.x - source.x)
  if (angle > Math.PI / 2 || angle < -Math.PI / 2) angle += Math.PI

  ctx.save()
  ctx.translate(x, y)
  ctx.rotate(angle)
  ctx.font = `600 ${fontSize}px ${palette.display}`
  const width = ctx.measureText(label).width
  const padX = 3 / globalScale
  const padY = 2 / globalScale
  ctx.globalAlpha = hovered ? 0.98 : 0.78
  ctx.fillStyle = palette.ink
  ctx.fillRect(-width / 2 - padX, -fontSize / 2 - padY, width + padX * 2, fontSize + padY * 2)
  ctx.fillStyle = linkColour(link)
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.fillText(label, 0, 0)
  ctx.restore()
}

/* Canvas sprite labels keep 3D useful without making it the default. */
function labelFor(node) {
  const text = shortLabel(node)
  const pad = 8
  const size = node.type === 'decision' ? 34 : 26
  const canvas = document.createElement('canvas')
  const ctx = canvas.getContext('2d')
  ctx.font = `600 ${size}px ${palette.display}`
  canvas.width = ctx.measureText(text).width + pad * 2
  canvas.height = size + pad * 2

  const c = canvas.getContext('2d')
  c.font = `600 ${size}px ${palette.display}`
  c.fillStyle = palette.ink1
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

function create2D() {
  return ForceGraph2D()(host.value)
    .backgroundColor(palette.ink)
    .nodeVal(sizeOf)
    .nodeLabel(tooltip)
    .nodeCanvasObject(paintNode)
    .nodePointerAreaPaint((node, colour, ctx, globalScale) => {
      ctx.fillStyle = colour
      ctx.beginPath()
      ctx.arc(node.x, node.y, renderRadius(node, globalScale) + 5 / globalScale, 0, 2 * Math.PI)
      ctx.fill()
    })
    .linkColor(linkColour)
    .linkWidth((link) => (hovered && linkTouches(link, hovered.id) ? 2.2 : 1.15))
    .linkDirectionalArrowLength(5)
    .linkDirectionalArrowRelPos(0.94)
    .linkCanvasObjectMode(() => 'after')
    .linkCanvasObject(paintLinkLabel)
    .minZoom(0.35)
    .maxZoom(8)
    .enableZoomPanInteraction(true)
    .onNodeHover(setHover)
    .onNodeClick((node) => {
      selected.value = node
      graph.value.centerAt(node.x, node.y, motionDuration(450))
      graph.value.zoom(Math.max(graph.value.zoom(), 1.6), motionDuration(450))
    })
    .onBackgroundClick(() => {
      selected.value = null
      setHover(null)
    })
    .onDagError(() => {})
    .onEngineStop(fitOnce)
}

function create3D() {
  return ForceGraph3D()(host.value)
    .backgroundColor(palette.ink)
    .showNavInfo(false)
    .nodeColor((node) => (hovered && !neighbours.has(node.id) ? palette.line : colourOf(node)))
    .nodeVal(sizeOf)
    .nodeOpacity(0.92)
    .nodeResolution(16)
    .nodeLabel(tooltip)
    .linkColor(linkColour)
    .linkWidth((link) => (['gates', 'depends_on'].includes(link.kind) ? 1.4 : 0.5))
    .linkOpacity(0.42)
    .linkDirectionalParticles((link) => (link.kind === 'gates' ? 3 : 0))
    .linkDirectionalParticleWidth(1.8)
    .linkDirectionalParticleSpeed(0.006)
    .linkDirectionalArrowLength(3.2)
    .linkDirectionalArrowRelPos(1)
    .onNodeHover(setHover)
    .onNodeClick((node) => {
      selected.value = node
      const distance = 130
      const ratio = 1 + distance / Math.hypot(node.x || 1, node.y || 1, node.z || 1)
      graph.value.cameraPosition(
        { x: (node.x || 0) * ratio, y: (node.y || 0) * ratio, z: (node.z || 0) * ratio },
        node,
        motionDuration(900),
      )
    })
    .onBackgroundClick(() => {
      selected.value = null
      setHover(null)
    })
    .nodeThreeObjectExtend(true)
    .nodeThreeObject(labelFor)
    // cites_basis creates cycles; keep laying out the rest of the graph.
    .onDagError(() => {})
    .onEngineStop(fitOnce)
}

function destroyGraph() {
  graph.value?._destructor?.()
  graph.value = null
  graphMode = null
  hovered = null
  neighbours = new Set()
  if (host.value) host.value.replaceChildren()
}

function build() {
  if (!host.value || !view.value) return
  readTokens()
  graphData = {
    nodes: view.value.graph.nodes.map((node) => ({ ...node })),
    links: view.value.graph.links.map((link) => ({ ...link })),
  }
  selected.value = graphData.nodes.find((node) => node.id === selected.value?.id) ?? null

  if (!graph.value || graphMode !== mode.value) {
    destroyGraph()
    graphMode = mode.value
    fitted = false
    graph.value = mode.value === '2d' ? create2D() : create3D()
    graph.value.d3Force('charge').strength(mode.value === '2d' ? -520 : -300)
    graph.value.d3Force('link').distance(mode.value === '2d' ? 84 : 42)
  }

  graph.value.graphData(graphData)
  applyLayout()
  applyFocus()
  resize()
}

function fitOnce() {
  if (fitted) return
  fitted = true
  fit()
}

function applyLayout() {
  if (!graph.value) return
  fitted = false
  graph.value
    .dagMode(layered.value ? 'bu' : null)
    .dagLevelDistance(layered.value ? (mode.value === '2d' ? 130 : 105) : undefined)
  graph.value.d3ReheatSimulation()
}

function applyFocus() {
  if (!graph.value) return
  const wanted = focus.value
  const nodesById = new Map(graphData.nodes.map((node) => [node.id, node]))
  const endpoint = (value) => (typeof value === 'object' ? value : nodesById.get(value))
  graph.value
    .nodeVisibility((node) => wanted === 'all' || node.type === wanted || node.type === 'decision')
    .linkVisibility((link) => {
      if (wanted === 'all') return true
      return [endpoint(link.source), endpoint(link.target)].every(
        (node) => node && (node.type === wanted || node.type === 'decision'),
      )
    })
}

function resize() {
  if (!graph.value || !host.value) return
  graph.value.width(host.value.clientWidth).height(host.value.clientHeight)
}

function fit() {
  graph.value?.zoomToFit(
    motionDuration(mode.value === '2d' ? 450 : 700),
    mode.value === '2d' ? 110 : 70,
  )
}

function zoomBy(factor) {
  if (!graph.value || mode.value !== '2d') return
  graph.value.zoom(graph.value.zoom() * factor, motionDuration(180))
}

onMounted(() => {
  build()
  window.addEventListener('resize', resize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', resize)
  destroyGraph()
})

watch(view, build)
watch(mode, build)
watch(focus, applyFocus)
watch(layered, applyLayout)
watch(selected, () => graph.value?.refresh?.())
</script>

<template>
  <div class="graph">
    <div ref="host" class="graph__canvas" />

    <nav v-if="mode === '2d'" class="graph__zoom" aria-label="Graph zoom controls">
      <button type="button" aria-label="Zoom in" title="Zoom in" @click="zoomBy(1.35)">+</button>
      <button type="button" aria-label="Zoom out" title="Zoom out" @click="zoomBy(0.74)">−</button>
      <button type="button" class="graph__zoom-fit" aria-label="Fit graph to view" title="Fit to view" @click="fit">
        fit
      </button>
    </nav>

    <div class="graph__legend panel">
      <div class="panel__head">
        <h3 class="panel__title">The evidence map</h3>
      </div>
      <div class="panel__body">
        <p class="graph__hint">
          {{
            mode === '2d'
              ? 'Drag nodes to untangle them, drag the background to pan, and scroll to zoom. Hover isolates immediate evidence.'
              : 'Drag to orbit, scroll to zoom, and click a node to fly to it.'
          }}
        </p>
        <ul class="legend">
          <li v-for="item in LEGEND" :key="item.key">
            <button
              class="legend__item"
              :class="{ 'legend__item--off': focus !== 'all' && focus !== item.key }"
              @click="focus = focus === item.key ? 'all' : item.key"
            >
              <span class="legend__dot" :style="{ background: `var(--${item.token})` }" />
              {{ item.label }}
            </button>
          </li>
        </ul>

        <p class="graph__key-title">Relationships</p>
        <ul class="relationship-key">
          <li v-for="kind in RELATIONSHIPS" :key="kind">
            <span :style="{ background: `var(--${LINK_TOKEN[kind]})` }" />
            {{ relationshipLabel(kind) }}
          </li>
        </ul>

        <div class="graph__actions">
          <button class="btn" :class="{ 'btn--on': layered }" @click="layered = !layered">
            {{ layered ? 'layered' : 'free float' }}
          </button>
          <button class="btn" @click="focus = 'all'">show all</button>
          <button class="btn" @click="mode = mode === '2d' ? '3d' : '2d'">
            {{ mode === '2d' ? '3D view' : '2D view' }}
          </button>
        </div>
        <p class="graph__hint graph__hint--last">
          Claim labels appear on hover or when you zoom in; the structure
          stays labelled. Status is printed in labels as [MET], [UNMET], [UNKNOWN], [MISSING], or [NON-GATING] — never by colour alone.
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
  cursor: grab;
}

.graph__canvas:active {
  cursor: grabbing;
}

.graph__legend {
  position: absolute;
  top: 20px;
  left: 20px;
  width: 310px;
  max-height: calc(100% - 40px);
  overflow: auto;
  backdrop-filter: blur(8px);
  background: color-mix(in srgb, var(--ink-1) 88%, transparent);
}

.graph__hint {
  margin: 0 0 12px;
  font-size: 12px;
  color: var(--chalk-faint);
  line-height: 1.45;
}

.legend {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 2px;
}

.legend__item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 4px 5px;
  background: none;
  border: 0;
  cursor: pointer;
  font-size: 12px;
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

.graph__key-title {
  margin: 14px 0 6px;
  font-family: var(--display);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--chalk-faint);
}

.relationship-key {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 5px 10px;
  list-style: none;
  margin: 0;
  padding: 0;
  font-family: var(--mono);
  font-size: 9.5px;
  color: var(--chalk-dim);
}

.relationship-key li {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.relationship-key span {
  width: 16px;
  height: 2px;
  flex: none;
}

.graph__actions {
  display: flex;
  gap: 7px;
  margin-top: 14px;
}

.btn {
  font-family: var(--display);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  padding: 5px 9px;
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
  margin: 11px 0 0;
}

.graph__zoom {
  position: absolute;
  top: 20px;
  right: 20px;
  z-index: 2;
  display: flex;
  flex-direction: column;
  border: 1px solid var(--line);
  background: color-mix(in srgb, var(--ink-1) 92%, transparent);
  box-shadow: 0 8px 24px color-mix(in srgb, var(--ink) 55%, transparent);
}

.graph__zoom button {
  width: 42px;
  height: 40px;
  padding: 0;
  border: 0;
  border-bottom: 1px solid var(--line);
  background: none;
  color: var(--chalk);
  font-family: var(--display);
  font-size: 25px;
  cursor: pointer;
}

.graph__zoom button:hover {
  color: var(--cyan);
  background: color-mix(in srgb, var(--cyan) 10%, transparent);
}

.graph__zoom button:last-child {
  border-bottom: 0;
}

.graph__zoom .graph__zoom-fit {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.graph__detail {
  position: absolute;
  bottom: 20px;
  right: 20px;
  width: 330px;
  max-height: 46%;
  overflow: auto;
  backdrop-filter: blur(8px);
  background: color-mix(in srgb, var(--ink-1) 90%, transparent);
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
    width: min(310px, calc(100% - 24px));
    max-height: 45%;
    margin: 0;
  }

  .graph__legend {
    top: 12px;
    left: 12px;
  }

  .graph__detail {
    right: 12px;
    bottom: 12px;
  }

  .graph__zoom {
    top: 12px;
    right: 12px;
  }
}
</style>

<style>
/* Both force-graph renderers inject the tooltip outside the scoped tree. */
.g-tip {
  font-family: var(--body);
  background: var(--ink-1);
  border: 1px solid var(--line);
  padding: 7px 11px;
  color: var(--chalk);
  font-size: 13px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  max-width: 300px;
}

.g-tip__type {
  font-family: var(--display);
  font-size: 11px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--chalk-faint);
}

.g-tip__cite {
  font-family: var(--mono);
  font-size: 11px;
  color: var(--cyan);
}
</style>
