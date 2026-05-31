const LABEL_STYLE_PALETTE = [
  {
    summaryClass: 'tone-sky',
    dotClass: 'dot-sky',
    headerClass: 'header-sky',
    borderClass: 'border-sky',
    badgeClass: 'badge-sky',
    pillClass: 'pill-sky',
  },
  {
    summaryClass: 'tone-emerald',
    dotClass: 'dot-emerald',
    headerClass: 'header-emerald',
    borderClass: 'border-emerald',
    badgeClass: 'badge-emerald',
    pillClass: 'pill-emerald',
  },
  {
    summaryClass: 'tone-amber',
    dotClass: 'dot-amber',
    headerClass: 'header-amber',
    borderClass: 'border-amber',
    badgeClass: 'badge-amber',
    pillClass: 'pill-amber',
  },
  {
    summaryClass: 'tone-violet',
    dotClass: 'dot-violet',
    headerClass: 'header-violet',
    borderClass: 'border-violet',
    badgeClass: 'badge-violet',
    pillClass: 'pill-violet',
  },
  {
    summaryClass: 'tone-rose',
    dotClass: 'dot-rose',
    headerClass: 'header-rose',
    borderClass: 'border-rose',
    badgeClass: 'badge-rose',
    pillClass: 'pill-rose',
  },
  {
    summaryClass: 'tone-cyan',
    dotClass: 'dot-cyan',
    headerClass: 'header-cyan',
    borderClass: 'border-cyan',
    badgeClass: 'badge-cyan',
    pillClass: 'pill-cyan',
  },
  {
    summaryClass: 'tone-slate',
    dotClass: 'dot-slate',
    headerClass: 'header-slate',
    borderClass: 'border-slate',
    badgeClass: 'badge-slate',
    pillClass: 'pill-slate',
  },
  {
    summaryClass: 'tone-lime',
    dotClass: 'dot-lime',
    headerClass: 'header-lime',
    borderClass: 'border-lime',
    badgeClass: 'badge-lime',
    pillClass: 'pill-lime',
  },
]

function hashLabel(label) {
  const text = String(label || '').trim()
  let hash = 0
  for (let i = 0; i < text.length; i += 1) {
    hash = ((hash << 5) - hash) + text.charCodeAt(i)
    hash |= 0
  }
  return Math.abs(hash)
}

export function getClassificationLabelStyle(label) {
  const normalized = String(label || '').trim()
  if (!normalized) {
    return LABEL_STYLE_PALETTE[LABEL_STYLE_PALETTE.length - 1]
  }
  return LABEL_STYLE_PALETTE[hashLabel(normalized) % LABEL_STYLE_PALETTE.length]
}
