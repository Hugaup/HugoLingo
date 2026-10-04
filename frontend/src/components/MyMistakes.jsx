import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import StatusBadge from './StatusBadge'
import { PERSON_LABELS, tenseWithMood } from '../utils/conjugationUtils'
import { BLANK } from '../utils/grammar'
import { STATUS_LABELS, checkUpLabel } from '../utils/reviewStatus'
import { color, radius, ui } from '../theme'

const FILTERS = ['all', 'needs_work', 'getting_there', 'fixed']

// "My mistakes": everything ever got wrong in a language — verb+tenses, grammar
// topics and words — with where each one stands and its latest wrong answers.
export default function MyMistakes({ language }) {
  const navigate = useNavigate()
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [filter, setFilter] = useState('all')

  useEffect(() => {
    api.getMistakes(language).then(setData).catch(e => setError(e.message))
  }, [language])

  if (error) return <p style={s.error}>{error}</p>
  if (!data) return <p style={s.muted}>Loading…</p>
  const grammarGroups = data.topics ?? []
  if (!data.verbs.length && !grammarGroups.length && !data.words.length) {
    return <p style={s.muted}>No mistakes yet. Anything you get wrong will be kept here.</p>
  }

  const total = data.verbs.length + grammarGroups.length + data.words.length
  const shown = list => list.filter(g => filter === 'all' || g.status === filter)
  const verbs = shown(data.verbs)
  const topics = shown(grammarGroups)
  const words = shown(data.words)

  return (
    <>
      <div style={s.filters} role="group" aria-label="Show">
        {FILTERS.map(f => (
          <button
            key={f}
            style={f === filter ? { ...s.chip, ...s.chipOn } : s.chip}
            aria-pressed={f === filter}
            onClick={() => setFilter(f)}
          >
            {f === 'all' ? `All (${total})` : `${STATUS_LABELS[f]} (${data.counts[f]})`}
          </button>
        ))}
      </div>

      {!verbs.length && !topics.length && !words.length && <p style={s.muted}>Nothing here.</p>}

      {verbs.length > 0 && (
        <section style={s.section} aria-labelledby="mistakes-verbs">
          <h2 id="mistakes-verbs" style={s.sectionTitle}>Verbs</h2>
          <ul style={s.list}>
            {verbs.map(g => (
              <Group
                key={`${g.verb_infinitive}|${g.mood}|${g.tense}`}
                title={<><strong>{g.verb_infinitive}</strong> · {tenseWithMood(language, g.mood, g.tense)}</>}
                group={g}
                renderMistake={m => (
                  <>
                    {m.person && m.person !== '—' && <span style={s.person}>{PERSON_LABELS[language]?.[m.person] ?? m.person}</span>}
                    <del style={s.wrong}>{m.user_answer || '—'}</del> → <strong>{m.expected}</strong>
                  </>
                )}
                onPractise={() => navigate(`/practice/${language}/review?${new URLSearchParams({
                  verb: g.verb_infinitive, mood: g.mood, tense: g.tense,
                })}`)}
              />
            ))}
          </ul>
        </section>
      )}

      {topics.length > 0 && (
        <section style={s.section} aria-labelledby="mistakes-grammar">
          <h2 id="mistakes-grammar" style={s.sectionTitle}>Grammar</h2>
          <ul style={s.list}>
            {topics.map(g => (
              <Group
                key={g.topic}
                title={<strong>{g.title}</strong>}
                group={g}
                renderMistake={m => <GrammarMistake mistake={m} />}
                onPractise={() => navigate(`/practice/${language}/grammar/${g.topic}/review`)}
              />
            ))}
          </ul>
        </section>
      )}

      {words.length > 0 && (
        <section style={s.section} aria-labelledby="mistakes-words">
          <div style={s.sectionHeader}>
            <h2 id="mistakes-words" style={s.sectionTitle}>Words</h2>
            <button style={s.link} onClick={() => navigate(`/practice/${language}/vocabulary`)}>Practise words →</button>
          </div>
          <ul style={s.list}>
            {words.map(g => (
              <Group
                key={g.item_id}
                title={<><strong>{g.text}</strong> · <span style={s.translation}>{g.translation.split(';')[0]}</span></>}
                group={g}
                renderMistake={m => <del style={s.wrong}>{m.user_answer || '—'}</del>}
              />
            ))}
          </ul>
        </section>
      )}
    </>
  )
}

function Group({ title, group, renderMistake, onPractise }) {
  const [open, setOpen] = useState(false)
  const n = group.total_mistakes
  return (
    <li style={s.item}>
      <div style={s.row}>
        <span style={s.what}>{title}</span>
        <span style={s.state}>
          {group.status === 'getting_there' && <span style={s.note}>{checkUpLabel(group.due_at)}</span>}
          <StatusBadge status={group.status} />
        </span>
      </div>
      <div style={s.row}>
        <button type="button" style={s.toggle} aria-expanded={open} onClick={() => setOpen(o => !o)}>
          {n} {n === 1 ? 'mistake' : 'mistakes'} {open ? '▴' : '▾'}
        </button>
        {onPractise && <button style={s.practise} onClick={onPractise}>Practise</button>}
      </div>
      {open && (
        <ul style={s.answers} aria-label="Wrong answers">
          {group.mistakes.map((m, i) => (
            <li key={i} style={s.answer}>
              <span>
                {renderMistake(m)}
                {m.is_almost && <span style={s.badge}>accents</span>}
              </span>
              <span style={s.date}>{formatDay(m.created_at)}</span>
            </li>
          ))}
          {n > group.mistakes.length && <li style={s.more}>…and {n - group.mistakes.length} earlier</li>}
        </ul>
      )}
    </li>
  )
}

// The sentence with the wrong option struck through and the right one after it
// (find-the-mistake answers are whole sentences: wrong → right)
function GrammarMistake({ mistake }) {
  const { question, user_answer: given, expected } = mistake
  if (!question.includes(BLANK)) {
    return <><del style={s.wrong}>{given}</del> → <strong>{expected}</strong></>
  }
  const [before, after] = question.split(BLANK)
  return <>{before}<del style={s.wrong}>{given}</del> <strong>{expected}</strong>{after}</>
}

function formatDay(iso) {
  return new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short' })
}

const s = {
  muted: { color: color.muted, margin: 0 },
  error: ui.error,
  filters: { display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginBottom: '1.25rem' },
  chip: ui.chip,
  chipOn: ui.chipSoftOn,
  section: { background: color.surface, borderRadius: radius.md, padding: '1rem 1.25rem', marginBottom: '1.25rem' },
  sectionHeader: { display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: '1rem' },
  sectionTitle: { ...ui.h2, margin: '0 0 0.5rem' },
  link: ui.link,
  list: { listStyle: 'none', padding: 0, margin: 0 },
  item: { padding: '0.6rem 0', borderBottom: '1px solid #eceef1' },
  row: { display: 'flex', alignItems: 'baseline', flexWrap: 'wrap', gap: '0.25rem 0.75rem' },
  what: { color: color.body, flex: '1 1 12rem', minWidth: 0, fontSize: '0.95rem' },
  translation: { color: color.muted },
  state: { display: 'flex', alignItems: 'baseline', gap: '0.5rem', marginLeft: 'auto' },
  note: { color: color.muted, fontSize: '0.8rem' },
  toggle: { background: 'none', border: 'none', padding: 0, marginTop: '0.2rem', color: color.primary, fontSize: '0.82rem', cursor: 'pointer', fontFamily: 'inherit' },
  practise: { ...ui.secondary, marginLeft: 'auto', padding: '0.3rem 0.8rem', fontSize: '0.82rem' },
  answers: { listStyle: 'none', padding: 0, margin: '0.4rem 0 0', fontSize: '0.88rem' },
  answer: { display: 'flex', justifyContent: 'space-between', gap: '0.75rem', padding: '0.15rem 0' },
  person: { color: color.muted, marginRight: '0.5rem' },
  wrong: { color: color.danger },
  badge: { marginLeft: '0.4rem', fontSize: '0.7rem', fontWeight: 600, color: color.warning, background: color.warningSoft, borderRadius: radius.pill, padding: '0.05rem 0.45rem' },
  date: { color: color.faint, whiteSpace: 'nowrap' },
  more: { color: color.faint, fontSize: '0.82rem', padding: '0.15rem 0' },
}
