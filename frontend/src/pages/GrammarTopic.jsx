import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import StatusBadge from '../components/StatusBadge'
import { LEVEL_SHORT, sheetsDone } from '../utils/grammar'
import { checkUpLabel } from '../utils/reviewStatus'
import { color, radius, ui } from '../theme'

// One grammar topic: the rule in a few lines, then its sheets (like Lingua's
// "Exercise 1, 2, 3") with how far you got in each.
export default function GrammarTopic() {
  const { language, topic: topicId } = useParams()
  const navigate = useNavigate()
  const [topic, setTopic] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.getGrammarTopic(language, topicId).then(setTopic).catch(e => setError(e.message))
  }, [language, topicId])

  const go = sheet => navigate(`/practice/${language}/grammar/${topicId}/${sheet}`)

  return (
    <div style={s.page}>
      <button style={s.back} onClick={() => navigate(`/practice/${language}/grammar`)}>← Grammar</button>
      {error && <p style={s.error}>{error}</p>}
      {!topic && !error && <p style={s.muted}>Loading…</p>}
      {topic && (
        <>
          <h1 style={s.title}>{topic.title}</h1>
          <p style={s.subtitle}>
            <span lang="es">{topic.spanish}</span>
            {topic.level && <span style={s.level}>{LEVEL_SHORT[topic.level]}</span>}
            <StatusBadge status={topic.status} />
          </p>

          <section style={s.rule} aria-labelledby="rule">
            <h2 id="rule" style={s.ruleTitle}>The rule</h2>
            <ul style={s.ruleList}>
              {topic.rule.map(line => <li key={line} style={s.ruleLine}>{line}</li>)}
            </ul>
          </section>

          {(topic.status === 'needs_work' || topic.status === 'getting_there') && (
            <div style={s.reviewBox}>
              <span style={s.reviewText}>
                {topic.status === 'needs_work'
                  ? 'You made mistakes here: a review sheet starts with them.'
                  : `Getting there — ${checkUpLabel(topic.due_at)}.`}
              </span>
              <button style={s.primary} onClick={() => go('review')}>Review your mistakes →</button>
            </div>
          )}

          <h2 style={s.h2}>Exercises <span style={s.count}>{sheetsDone(topic)} of {topic.sheets.length} done</span></h2>
          <ul style={s.sheets}>
            {topic.sheets.map(sheet => {
              const done = sheet.answered === sheet.questions
              const started = sheet.answered > 0
              const action = done ? 'Do again' : started ? 'Continue' : 'Start'
              return (
                <li key={sheet.number} style={s.sheet}>
                  <span style={s.sheetName}>
                    <span style={s.sheetTitle}>Exercise {sheet.number}</span>
                    {sheet.title && <span style={s.sheetSub}>{sheet.title}</span>}
                  </span>
                  <span style={done ? s.done : s.progress}>
                    {done ? `✓ ${sheet.correct} of ${sheet.questions} right`
                      : started ? `${sheet.answered} of ${sheet.questions} answered`
                        : `${sheet.questions} questions`}
                  </span>
                  <button
                    style={started ? s.secondary : s.primary}
                    aria-label={`${action}: exercise ${sheet.number}`}
                    onClick={() => go(sheet.number)}
                  >
                    {action}
                  </button>
                </li>
              )
            })}
          </ul>
        </>
      )}
    </div>
  )
}

const s = {
  page: { ...ui.page, maxWidth: 680 },
  back: ui.back,
  title: { ...ui.h1, marginBottom: '0.3rem' },
  subtitle: { display: 'flex', alignItems: 'center', gap: '0.6rem', flexWrap: 'wrap', color: color.muted, margin: '0 0 1.25rem' },
  level: { fontSize: '0.75rem', fontWeight: 700, color: color.primary, background: color.primarySoft, borderRadius: radius.pill, padding: '0.1rem 0.55rem' },
  muted: { color: color.muted },
  error: ui.error,
  rule: { ...ui.panel, padding: '1rem 1.25rem', marginBottom: '1.25rem' },
  ruleTitle: { ...ui.h2, fontSize: '0.95rem', margin: '0 0 0.4rem' },
  ruleList: { margin: 0, paddingLeft: '1.1rem' },
  ruleLine: { fontSize: '0.92rem', color: color.body, lineHeight: 1.5, marginBottom: '0.25rem' },
  reviewBox: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.6rem 1rem', background: color.warningSoft, borderRadius: radius.md, padding: '0.8rem 1rem', marginBottom: '1.25rem' },
  reviewText: { color: color.warning, fontSize: '0.9rem', flex: '1 1 14rem' },
  h2: { ...ui.h2, display: 'flex', alignItems: 'baseline', gap: '0.6rem' },
  count: { fontSize: '0.82rem', fontWeight: 500, color: color.muted },
  sheets: { listStyle: 'none', padding: 0, margin: 0, display: 'grid', gap: '0.5rem' },
  sheet: { display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem 1rem', borderWidth: 1, borderStyle: 'solid', borderColor: color.border, borderRadius: radius.md, padding: '0.75rem 1rem' },
  sheetName: { display: 'flex', flexDirection: 'column', flex: '1 1 10rem', minWidth: 0 },
  sheetTitle: { fontWeight: 700, color: color.ink },
  sheetSub: { fontSize: '0.82rem', color: color.muted },
  progress: { fontSize: '0.85rem', color: color.muted },
  done: { fontSize: '0.85rem', color: color.success, fontWeight: 600 },
  primary: { ...ui.primary, padding: '0.45rem 1rem', fontSize: '0.9rem' },
  secondary: { ...ui.secondary, padding: '0.45rem 1rem', fontSize: '0.9rem' },
}
