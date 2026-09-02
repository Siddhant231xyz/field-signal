/* The graph tooltip is the only place this app builds HTML from ledger text,
   because 3d-force-graph inserts nodeLabel as markup rather than as text.
   Ledger text is not trusted — the ingestion experiment derives claims from
   arbitrary packet documents — so it is escaped here, in one place. */

const ESCAPES = {
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&#39;',
}

export function escapeHtml(value) {
  if (value === null || value === undefined) return ''
  // & is in the character class first only for readability; String.replace
  // scans left to right, so an escaped & is never re-escaped.
  return String(value).replace(/[&<>"']/g, (c) => ESCAPES[c])
}

export function tooltip(node) {
  const type = escapeHtml(node.type) + (node.kind ? ' · ' + escapeHtml(node.kind) : '')
  const cite = node.citation
    ? `<span class="g-tip__cite">${escapeHtml(node.citation)}</span>`
    : ''
  return `<div class="g-tip">
      <span class="g-tip__type">${type}</span>
      <strong>${escapeHtml(node.label)}</strong>
      ${cite}
    </div>`
}
