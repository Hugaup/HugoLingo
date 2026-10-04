import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import StatusBadge from './StatusBadge'
import { tenseWithMood } from '../utils/conjugationUtils'
import { checkUpLabel } from '../utils/reviewStatus'
import { color, ui } from '../theme'

// Compact "Work on this" panel: the verb+tenses that need work (worst first),
// then the ones getting there with their next check-up, and one click into
// the review drill when something is due.
export default function WorkOnThis({ language, limit = 4, onShowHistory = null }) {
  const navigate = useNavigate()
  const [data, setData] = useState(null)

  useEffect(() => {
    let cancelled = false
    api.getWeakSpots(language, limit)
      .then(d => { if (!cancelled) setData(d) })
      .catch(() => {})
    return () => { cancelled = true }
  }, [language, limit])

  if (!data) return null

  const { items, counts, due_count: due, next_check_up_at: nextCheckUp } = data
  if (!counts.needs_work && !counts.getting_there && !counts.fixed && !due) {
    return <p style={s.empty}>Mistakes you make will show up here so you can work on them.</p>
  }

  const showHistory = onShowHistory ?? (() => navigate(`/progress?view=mistakes&language=${language}`))

  return (
    <section style={s.panel} aria-labelledby="work-on-this">
      <div style={s.header}>
        <h2 id="work-on-this" style={s.title}>Work on this</h2>
        {due > 0 && <span style={s.due}>{due} due for review</span>}
      </div>

      {items.length > 0 ? (
        <ul style={s.list}>
          {items.map(i => {
            const later = i.status === 'getting_there'
            return (
              <li key={`${i.verb_infinitive}|${i.mood}|${i.tense}`} style={s.item}>
                <span style={later ? { ...s.verb, ...s.dim } : s.verb}>{i.verb_infinitive}</span>
                <span style={later ? { ...s.detail, ...s.dim } : s.detail}>{tenseWithMood(language, i.mood, i.tense)}</span>
                <span style={s.state}>
                  {later
                    ? <>{checkUpLabel(i.due_at)} <StatusBadge status={i.status} /></>
                    : <>{i.mistakes} {i.mistakes === 1 ? 'mistake' : 'mistakes'}</>}
                </span>
              </li>
            )
          })}
        </ul>
      ) : (
        <p style={s.clear}>✓ Nothing left to work on.</p>
      )}

      <div style={s.footer}>
        {due > 0 ? (
          <button style={s.button} onClick={() => navigate(`/practice/${language}/review`)}>
            Practise these →
          </button>
        ) : nextCheckUp && (
          <span style={s.caughtUp}>All caught up — next {checkUpLabel(nextCheckUp)}.</span>
        )}
        <span style={s.more}>
          {counts.fixed > 0 && <span style={s.fixed}>{counts.fixed} fixed</span>}
          <button style={s.link} onClick={showHistory}>All your mistakes →</button>
        </span>
      </div>
    </section>
  )
}

const s = {
  empty: { color: color.faint, fontSize: '0.9rem', margin: '0 0 1.5rem' },
  panel: { background: color.surface, borderRadius: 12, padding: '1rem 1.25rem', marginBottom: '1.5rem', textAlign: 'left' },
  header: { display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: '1rem', marginBottom: '0.5rem' },
  title: { fontSize: '1rem', fontWeight: 700, color: color.ink, margin: 0 },
  due: { fontSize: '0.8rem', color: color.primary, fontWeight: 600 },
  list: { listStyle: 'none', padding: 0, margin: '0 0 0.75rem' },
  item: { display: 'flex', alignItems: 'baseline', flexWrap: 'wrap', columnGap: '0.6rem', rowGap: '0.15rem', padding: '0.3rem 0', borderBottom: '1px solid #eceef1', fontSize: '0.92rem' },
  verb: { fontWeight: 700, color: color.ink },
  detail: { color: '#4b5563', flex: 1 },
  dim: { color: color.faint },
  state: { marginLeft: 'auto', color: color.muted, fontSize: '0.8rem', whiteSpace: 'nowrap' },
  clear: { color: color.success, margin: '0 0 0.75rem', fontSize: '0.92rem' },
  footer: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '0.75rem', flexWrap: 'wrap' },
  caughtUp: { color: color.muted, fontSize: '0.85rem' },
  more: { display: 'flex', alignItems: 'baseline', gap: '0.75rem', marginLeft: 'auto', fontSize: '0.85rem' },
  fixed: { color: color.success, fontWeight: 600 },
  link: ui.link,
  button: { ...ui.primary, padding: '0.5rem 1rem', fontSize: '0.9rem' },
}
