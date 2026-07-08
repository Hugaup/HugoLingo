export default function FeedbackPanel({ result }) {
  if (!result) return null

  const bg = result.is_correct ? '#dcfce7' : '#fee2e2'
  const color = result.is_correct ? '#166534' : '#991b1b'
  const heading = result.is_correct ? 'Correct!' : 'Not quite'

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
