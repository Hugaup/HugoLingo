const TONES = {
  correct: { bg: '#dcfce7', color: '#166534', heading: 'Correct!' },
  almost:  { bg: '#fef3c7', color: '#92400e', heading: 'Almost — check the accents' },
  wrong:   { bg: '#fee2e2', color: '#991b1b', heading: 'Not quite' },
}

export default function FeedbackPanel({ result }) {
  if (!result) return null

  // "almost" = only the accents are off; still a mistake, but said kindly
  const tone = result.is_correct ? 'correct' : result.almost ? 'almost' : 'wrong'
  const { bg, color, heading } = TONES[tone]

  return (
    <div style={{ background: bg, borderRadius: 10, padding: '1rem 1.25rem', marginTop: '1rem' }}>
      <p style={{ fontWeight: 700, color, marginBottom: '0.5rem', fontSize: '1.1rem' }}>{heading}</p>
      {!result.is_correct && (
        <p style={{ marginBottom: '0.5rem' }}>
          <strong>Correct answer:</strong> {result.correct_answer}
        </p>
      )}
      <p style={{ color: '#374151', fontSize: '0.95rem' }}>{result.explanation}</p>
    </div>
  )
}
