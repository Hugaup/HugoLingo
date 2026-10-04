import { STATUS_LABELS } from '../utils/reviewStatus'
import { color, radius } from '../theme'

// A small pill saying where a weak spot stands: needs work / getting there / fixed
export default function StatusBadge({ status }) {
  if (!status) return null
  return (
    <span style={{ ...s.badge, ...STATUS_STYLE[status] }}>
      {status !== 'needs_work' && '✓ '}{STATUS_LABELS[status]}
    </span>
  )
}

const s = {
  badge: { display: 'inline-block', fontSize: '0.72rem', fontWeight: 600, borderRadius: radius.pill, padding: '0.1rem 0.5rem', whiteSpace: 'nowrap' },
}

const STATUS_STYLE = {
  needs_work: { color: color.danger, background: color.dangerSoft },
  getting_there: { color: color.warning, background: color.warningSoft },
  fixed: { color: color.success, background: color.successSoft },
}
