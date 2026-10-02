import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { tenseWithMood } from '../utils/conjugationUtils'
import { ui } from '../theme'

// Compact "Work on this" panel: the user's weakest verb+tenses for a language,
// with one click into the focused review drill.
export default function WorkOnThis({ language, limit = 4 }) {
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

  // Verb+tense pairs first, then verbs only known from the older free-text
  // exercise flow (which has no DB tense to drill)
  const comboVerbs = new Set(data.combos.map(c => c.verb_infinitive))
  const items = [
    ...data.combos.map(c => ({
      key: `${c.verb_infinitive}|${c.mood}|${c.tense}`,
      verb: c.verb_infinitive,
      detail: tenseWithMood(language, c.mood, c.tense),
      mistakes: c.mistakes,
    })),
    ...data.verbs
      .filter(v => !comboVerbs.has(v.verb_infinitive))
      .map(v => ({ key: v.verb_infinitive, verb: v.verb_infinitive, detail: null, mistakes: v.mistakes })),
  ].slice(0, limit)

  if (!items.length && !data.due_count) {
    return <p style={s.empty}>Mistakes you make will show up here so you can work on them.</p>
  }

  const canDrill = data.combos.length > 0 || data.due_count > 0

  return (
    <section style={s.panel} aria-labelledby="work-on-this">
      <div style={s.header}>
        <h2 id="work-on-this" style={s.title}>Work on this</h2>
        {data.due_count > 0 && <span style={s.due}>{data.due_count} due for review</span>}
      </div>
      <ul style={s.list}>
        {items.map(i => (
          <li key={i.key} style={s.item}>
            <span style={s.verb}>{i.verb}</span>
            {i.detail && <span style={s.detail}>{i.detail}</span>}
            <span style={s.mistakes}>{i.mistakes} {i.mistakes === 1 ? 'mistake' : 'mistakes'}</span>
          </li>
        ))}
      </ul>
      {canDrill && (
        <button style={s.button} onClick={() => navigate(`/practice/${language}/review`)}>
          Practise these →
        </button>
      )}
    </section>
  )
}

const s = {
  empty: { color: '#9ca3af', fontSize: '0.9rem', margin: '0 0 1.5rem' },
  panel: { background: '#f8f9fa', borderRadius: 12, padding: '1rem 1.25rem', marginBottom: '1.5rem', textAlign: 'left' },
  header: { display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: '1rem', marginBottom: '0.5rem' },
  title: { fontSize: '1rem', fontWeight: 700, color: '#1e1b4b', margin: 0 },
  due: { fontSize: '0.8rem', color: '#4f46e5', fontWeight: 600 },
  list: { listStyle: 'none', padding: 0, margin: '0 0 0.75rem' },
  item: { display: 'flex', alignItems: 'baseline', gap: '0.6rem', padding: '0.3rem 0', borderBottom: '1px solid #eceef1', fontSize: '0.92rem' },
  verb: { fontWeight: 700, color: '#1e1b4b' },
  detail: { color: '#4b5563', flex: 1 },
  mistakes: { marginLeft: 'auto', color: '#6b7280', fontSize: '0.8rem', whiteSpace: 'nowrap' },
  button: { ...ui.primary, padding: '0.5rem 1rem', fontSize: '0.9rem' },
}
