import { useNavigate } from 'react-router-dom'

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
  card: { background: '#f8f9fa', borderRadius: 12, padding: '1.5rem' },
  score: { fontSize: '1.4rem', fontWeight: 800, color: '#1e1b4b', margin: '0 0 0.4rem' },
  note: { fontSize: '0.85rem', color: '#92400e', margin: '0 0 0.75rem' },
  perfect: { color: '#15803d', margin: '0 0 1.25rem' },
  list: { listStyle: 'none', padding: 0, margin: '0.5rem 0 1.25rem' },
  item: { display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) auto', alignItems: 'baseline', gap: '1rem', padding: '0.35rem 0', borderBottom: '1px solid #eceef1', fontSize: '0.9rem' },
  what: { color: '#4b5563', minWidth: 0 },
  answer: { whiteSpace: 'nowrap' },
  wrong: { color: '#b91c1c' },
  blank: { color: '#9ca3af' },
  badge: { marginLeft: '0.4rem', fontSize: '0.7rem', fontWeight: 600, color: '#92400e', background: '#fef3c7', borderRadius: 999, padding: '0.05rem 0.45rem' },
  actions: { display: 'flex', gap: '0.6rem', flexWrap: 'wrap' },
  primary: { background: '#4f46e5', color: '#fff', border: 'none', borderRadius: 8, padding: '0.6rem 1.1rem', fontSize: '0.95rem', fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' },
  secondary: { background: '#fff', color: '#374151', border: '1px solid #d1d5db', borderRadius: 8, padding: '0.6rem 1.1rem', fontSize: '0.95rem', cursor: 'pointer', fontFamily: 'inherit' },
}
