import { useNavigate } from 'react-router-dom'
import { ui } from '../theme'

// End-of-session recap: the score, every mistake (accent slips marked), and
// what to do next. results: [{ label, answer, expected, result: 'correct'|'almost'|'wrong' }]
export default function SessionSummary({
  language,
  results,
  onRestart,
  restartLabel = 'Practise again',
  showReviewLink = true,
}) {
  const navigate = useNavigate()
  const correct = results.filter(r => r.result === 'correct').length
  const almost = results.filter(r => r.result === 'almost').length
  const mistakes = results.filter(r => r.result !== 'correct')
  const offerReview = showReviewLink && mistakes.length > 0

  return (
    <section style={s.card} aria-label="Session summary">
      <p style={s.score}>{correct} / {results.length} correct</p>
      {almost > 0 && (
        <p style={s.note}>
          {almost} {almost === 1 ? 'answer was' : 'answers were'} only an accent away — still counted as {almost === 1 ? 'a mistake' : 'mistakes'}.
        </p>
      )}

      {mistakes.length > 0 ? (
        <ul style={s.list} aria-label="Mistakes">
          {mistakes.map((m, i) => (
            <li key={i} style={s.item}>
              <span style={s.what}>{m.label}</span>
              <span style={s.answer}>
                {m.answer ? <del style={s.wrong}>{m.answer}</del> : <em style={s.blank}>blank</em>}
                {' → '}<strong>{m.expected}</strong>
                {m.result === 'almost' && <span style={s.badge}>accents</span>}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p style={s.perfect}>No mistakes — well done!</p>
      )}

      <div style={s.actions}>
        {offerReview && (
          <button style={s.primary} onClick={() => navigate(`/practice/${language}/review`)}>Review these now →</button>
        )}
        {onRestart && (
          <button style={offerReview ? s.secondary : s.primary} onClick={onRestart}>{restartLabel}</button>
        )}
        <button style={s.secondary} onClick={() => navigate(`/practice/${language}`)}>Back to practice</button>
      </div>
    </section>
  )
}

const s = {
  card: ui.panel,
  score: { fontSize: '1.4rem', fontWeight: 800, color: '#1e1b4b', margin: '0 0 0.4rem' },
  note: { fontSize: '0.85rem', color: '#92400e', margin: '0 0 0.75rem' },
  perfect: { color: '#15803d', margin: '0 0 1.25rem' },
  list: { listStyle: 'none', padding: 0, margin: '0.5rem 0 1.25rem' },
  // Short answers (tuvé → tuve) sit to the right of the label; long ones (whole
  // sentences) wrap onto their own line instead of running over the label
  item: { display: 'flex', flexWrap: 'wrap', alignItems: 'baseline', justifyContent: 'space-between', columnGap: '1rem', rowGap: '0.15rem', padding: '0.35rem 0', borderBottom: '1px solid #eceef1', fontSize: '0.9rem' },
  what: { color: '#4b5563', flex: '1 1 10rem', minWidth: 0 },
  answer: { minWidth: 0, overflowWrap: 'anywhere' },
  wrong: { color: '#b91c1c' },
  blank: { color: '#9ca3af' },
  badge: { marginLeft: '0.4rem', fontSize: '0.7rem', fontWeight: 600, color: '#92400e', background: '#fef3c7', borderRadius: 999, padding: '0.05rem 0.45rem' },
  actions: { display: 'flex', gap: '0.6rem', flexWrap: 'wrap' },
  primary: ui.primary,
  secondary: ui.secondary,
}
