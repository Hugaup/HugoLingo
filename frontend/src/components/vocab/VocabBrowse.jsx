import { useEffect, useState } from 'react'
import { api } from '../../api'
import SpeakButton from '../SpeakButton'
import { allTranslations, byTopicOrder, topicLabel } from '../../utils/vocab'
import { color, radius, ui } from '../../theme'

// Mirrors MAX_BOX / LEARNED_BOX in the backend (services/history.py, services/vocabulary.py)
const LAST_STEP = 5
const LEARNED_STEP = 3

// Read-only list of a topic's words (or all everyday phrases), with how far
// along the user is with each one.
export default function VocabBrowse({ language, kind, topic, onBack, onPractise }) {
  const [rows, setRows] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.getVocabItems(language, { kind, topic })
      .then(setRows)
      .catch(e => setError(e.message))
  }, [language, kind, topic])

  const title = kind === 'phrase' ? 'Everyday phrases' : kind === 'personal' ? 'My words' : topicLabel(topic)

  async function remove(id) {
    try {
      await api.removeMyWord(id)
      setRows(rs => rs.filter(r => r.id !== id))
    } catch (e) {
      setError(e.message)
    }
  }
  const grouped = Object.entries(groupBy(rows ?? [])).sort(([a], [b]) => byTopicOrder(a, b))
  const practised = rows?.some(r => r.box !== null)

  return (
    <div>
      <div style={s.header}>
        <button style={s.back} onClick={onBack}>← All topics</button>
        <button style={s.primary} onClick={onPractise}>Practise these</button>
      </div>
      <h2 style={s.title}>{title}</h2>
      {error && <p style={s.error}>{error}</p>}
      {!rows && !error && <p style={s.muted}>Loading…</p>}
      {practised && <StepsExplained />}
      {grouped.map(([group, items]) => (
        <section key={group} style={s.section}>
          {kind === 'phrase' && <h3 style={s.group}>{topicLabel(group)}</h3>}
          <ul style={s.list}>
            {items.map(r => (
              <li key={r.id} style={s.row}>
                <div style={s.main}>
                  <span style={s.word}>{r.display}<SpeakButton text={r.text} language={language} /></span>
                  <span style={s.translation}>{allTranslations(r)}</span>
                </div>
                <p style={s.example}>{r.example}</p>
                <span style={s.meta}>
                  {r.box !== null && (
                    <span style={r.box >= LEARNED_STEP ? s.learned : s.step}>
                      Step {r.box} of {LAST_STEP}{r.box >= LEARNED_STEP && ' · learned'}
                    </span>
                  )}
                  {kind === 'personal' && (
                    <button style={s.remove} onClick={() => remove(r.id)} aria-label={`Remove ${r.text}`}>Remove</button>
                  )}
                </span>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  )
}

// Always on screen (not a tooltip, which phones can't show): what "Step N of 5" means
function StepsExplained() {
  return (
    <p style={s.explain}>
      <strong>Steps</strong> show how well a word is sticking. Each time you get it right on its
      review day it goes up a step and comes back later: step 1 tomorrow, step 2 in 3 days,
      step 3 in a week, step 4 in 2 weeks, step 5 in a month. From step {LEARNED_STEP} it counts
      as learned. A wrong answer sends it back to step 0, to practise again straight away.
    </p>
  )
}

function groupBy(rows) {
  return rows.reduce((acc, r) => ({ ...acc, [r.topic]: [...(acc[r.topic] ?? []), r] }), {})
}

const s = {
  header: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '1rem' },
  back: ui.back,
  primary: { ...ui.primary, padding: '0.5rem 1rem', fontSize: '0.9rem' },
  title: { fontSize: '1.3rem', fontWeight: 800, color: '#1e1b4b', margin: '1rem 0' },
  section: { marginBottom: '1.25rem' },
  group: { fontSize: '0.95rem', fontWeight: 700, color: '#4f46e5', margin: '0 0 0.4rem' },
  list: { listStyle: 'none', padding: 0, margin: 0 },
  row: { display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) auto', columnGap: '1rem', padding: '0.55rem 0', borderBottom: '1px solid #eceef1' },
  main: { display: 'flex', flexWrap: 'wrap', gap: '0.25rem 0.75rem', alignItems: 'baseline' },
  word: { fontWeight: 700, color: '#1e1b4b' },
  translation: { color: '#4b5563' },
  example: { gridColumn: '1 / 2', margin: '0.15rem 0 0', fontSize: '0.82rem', color: '#6b7280' },
  meta: { gridColumn: '2', gridRow: '1', fontSize: '0.75rem', color: '#9ca3af', whiteSpace: 'nowrap' },
  step: { color: color.primary },
  learned: { color: color.success, fontWeight: 600 },
  explain: { margin: '0 0 1rem', padding: '0.6rem 0.8rem', background: color.surface, borderRadius: radius.sm, fontSize: '0.82rem', lineHeight: 1.5, color: color.body },
  remove: { marginLeft: '0.5rem', background: 'none', border: 'none', color: '#b91c1c', cursor: 'pointer', fontSize: '0.75rem', padding: 0, fontFamily: 'inherit' },
  muted: { color: '#6b7280' },
  error: { color: '#b91c1c' },
}
