/* Run: node --test web/src/
 *
 * The graph tooltip is the one place this app builds HTML from ledger text.
 * Ledger text is not trusted: the ingestion experiment derives claims from
 * arbitrary packet documents, so a document can reach these strings. A source
 * that could inject markup could forge what the tool displays about it, which
 * is the exact failure this product exists to prevent.
 */

import assert from 'node:assert/strict'
import { test } from 'node:test'

import { escapeHtml, tooltip } from './escape.js'

test('escapes every character that can open a tag or attribute', () => {
  assert.equal(
    escapeHtml(`<script>alert(1)</script>`),
    '&lt;script&gt;alert(1)&lt;/script&gt;',
  )
  assert.equal(escapeHtml(`" onload="x`), '&quot; onload=&quot;x')
  assert.equal(escapeHtml(`' onerror='x`), '&#39; onerror=&#39;x')
  assert.equal(escapeHtml('a & b'), 'a &amp; b')
})

test('escapes the ampersand first, so entities are not double-decoded', () => {
  assert.equal(escapeHtml('&lt;img&gt;'), '&amp;lt;img&amp;gt;')
})

test('passes ordinary claim text through unchanged', () => {
  const real = 'I did not lay out the final head.'
  assert.equal(escapeHtml(real), real)
  assert.equal(escapeHtml('approximately 6–12 inches'), 'approximately 6–12 inches')
})

test('handles missing and non-string values without throwing', () => {
  assert.equal(escapeHtml(undefined), '')
  assert.equal(escapeHtml(null), '')
  assert.equal(escapeHtml(0), '0')
})

test('a hostile claim cannot inject markup into the tooltip', () => {
  const hostile = {
    type: 'claim',
    kind: 'assertion',
    label: '<img src=x onerror="alert(1)">',
    citation: '"><script>fetch("//evil")</script>',
  }
  const html = tooltip(hostile)
  const benign = tooltip({ type: 'claim', kind: 'assertion', label: 'x', citation: 'y' })

  assert.ok(!html.includes('<img'), 'no injected element')
  assert.ok(!html.includes('<script'), 'no injected script')

  // The real property: hostile input opens no tag and no attribute. Count the
  // structural characters — a hostile node must produce exactly as many as a
  // benign one, all of them written by the template itself.
  const count = (s, c) => s.split(c).length - 1
  assert.equal(count(html, '<'), count(benign, '<'), 'no extra tag opened')
  assert.equal(count(html, '"'), count(benign, '"'), 'no extra attribute opened')

  // The hostile text is still shown to the reader — visible, and inert.
  assert.ok(html.includes('&lt;img src=x onerror=&quot;alert(1)&quot;&gt;'))
})

test('a real node still renders its own markup', () => {
  const html = tooltip({
    type: 'claim',
    kind: 'estimate',
    label: 'CL-S01-18',
    citation: 'S-01 08:08:41',
  })
  assert.ok(html.includes('class="g-tip"'))
  assert.ok(html.includes('claim · estimate'))
  assert.ok(html.includes('CL-S01-18'))
  assert.ok(html.includes('S-01 08:08:41'))
})

test('omits the citation block when a node has none', () => {
  const html = tooltip({ type: 'person', label: 'Maya Chen' })
  assert.ok(!html.includes('g-tip__cite'))
  assert.ok(html.includes('Maya Chen'))
})
