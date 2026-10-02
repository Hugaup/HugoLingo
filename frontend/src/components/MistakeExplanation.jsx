import { useState } from 'react'
import { PERSON_LABELS } from '../utils/conjugationUtils'

// Compact feedback after a mistake: one line, with the whole tense behind a
// toggle so the screen doesn't get crowded.
export default function MistakeExplanation({ explanation, language, person }) {
  const [open, setOpen] = useState(false)
  if (!explanation) return null
  const labels = PERSON_LABELS[language] || {}

  return (
    <div style={s.wrap}>
      <p style={s.summary}>{explanation.summary}</p>
      {explanation.forms.length > 0 && (
        <>
          <button type="button" style={s.toggle} aria-expanded={open} onClick={() => setOpen(o => !o)}>
            {open ? 'Hide forms ▴' : 'Show all forms ▾'}
          </button>
          {open && (
            <dl style={s.forms} aria-label="All forms in this tense">
              {explanation.forms.map(f => (
                <div key={f.person} style={f.person === person ? { ...s.row, ...s.rowActive } : s.row}>
                  <dt style={s.person}>{f.person === '—' ? '' : (labels[f.person] ?? f.person)}</dt>
                  <dd style={s.form}>{f.form}</dd>
                </div>
              ))}
            </dl>
          )}
        </>
      )}
    </div>
  )
}

const s = {
  wrap: { marginTop: '0.5rem' },
  summary: { margin: 0, fontSize: '0.9rem', color: '#374151', lineHeight: 1.45 },
  toggle: { background: 'none', border: 'none', padding: 0, marginTop: '0.3rem', color: '#4f46e5', fontSize: '0.82rem', cursor: 'pointer', fontFamily: 'inherit' },
  forms: { display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: '0.15rem 1rem', margin: '0.4rem 0 0', fontSize: '0.88rem' },
  row: { display: 'flex', gap: '0.5rem', padding: '0.1rem 0.35rem', borderRadius: 6 },
  rowActive: { background: '#e0e7ff' },
  person: { color: '#6b7280', minWidth: '5.5rem' },
  form: { margin: 0, fontWeight: 600, color: '#1e1b4b' },
}
