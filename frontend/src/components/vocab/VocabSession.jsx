import { useEffect, useRef, useState } from 'react'
import { api } from '../../api'
import CharPicker from '../conjugation/CharPicker'
import SessionSummary from '../SessionSummary'
import { allTranslations, mainTranslation, orderedOptions, pickExercise } from '../../utils/vocab'

const INSTRUCTIONS = {
  flashcard: 'Do you know this one?',
  choice_to_native: 'What does it mean?',
  choice_to_target: 'Which is the right word?',
  type_to_target: 'Type it in the language you are learning',
  type_to_native: 'Type it in English',
  cloze: 'Fill the gap',
}

// One vocabulary practice session: each item gets an exercise (see
// pickExercise), answers are graded by the server, a summary ends it.
export default function VocabSession({ language, items, mode, onRestart }) {
  const [index, setIndex]     = useState(0)
  const [answer, setAnswer]   = useState('')
  const [revealed, setRevealed] = useState(false)
  const [picked, setPicked]   = useState(null)
  const [result, setResult]   = useState(null)
  const [checking, setChecking] = useState(false)
  const [error, setError]     = useState(null)
  const [log, setLog]         = useState([])
  const inputRef = useRef(null)
  const nextRef  = useRef(null)

  useEffect(() => {
    if (result) nextRef.current?.focus()
    else inputRef.current?.focus()
  }, [result, index])

  if (index >= items.length) {
    return (
      <SessionSummary
        language={language}
        results={log}
        onRestart={onRestart}
        restartLabel="Practise again"
        showReviewLink={false}
      />
    )
  }

  const item = items[index]
  const exercise = pickExercise(item, mode, index)
  const toNative = exercise.endsWith('_native')

  async function submit({ text = '', knew } = {}) {
    if (checking) return
    setChecking(true)
    setError(null)
    try {
      const res = await api.checkVocab(item.id, exercise, { answer: text, knew })
      setLog(l => [...l, {
        label: `${item.display} — ${mainTranslation(item)}`,
        answer: exercise === 'flashcard' ? (knew ? 'knew it' : "didn't know") : text,
        expected: toNative ? mainTranslation(item) : item.display,
        result: res.result,
      }])
      if (exercise === 'flashcard') next()  // self-graded: nothing more to show
      else setResult(res)
    } catch (e) {
      setError(e.message)
    } finally {
      setChecking(false)
    }
  }

  function next() {
    setIndex(i => i + 1)
    setAnswer('')
    setRevealed(false)
    setPicked(null)
    setResult(null)
  }

  function onType(e) {
    e.preventDefault()
    if (answer.trim()) submit({ text: answer.trim() })
  }

  return (
    <div style={s.card}>
      <div style={s.topRow}>
        <span style={s.progress}>{index + 1} / {items.length}</span>
        <span style={s.instruction}>{INSTRUCTIONS[exercise]}</span>
      </div>

      <Prompt item={item} exercise={exercise} />

      {exercise === 'flashcard' && (
        revealed ? (
          <div>
            <p style={s.reveal}>{allTranslations(item)}</p>
            <Example item={item} />
            <div style={s.actions}>
              <button style={s.primary} onClick={() => submit({ knew: true })} disabled={checking}>I knew it</button>
              <button style={s.secondary} onClick={() => submit({ knew: false })} disabled={checking}>I didn't know</button>
            </div>
          </div>
        ) : (
          <button ref={inputRef} style={s.primary} onClick={() => setRevealed(true)}>Show translation</button>
        )
      )}

      {exercise.startsWith('choice_') && (
        <div style={s.options} role="group" aria-label="Options">
          {orderedOptions(item).map(option => {
            const label = toNative ? mainTranslation(option) : option.display
            const state = !result ? null : option.id === item.id ? 'right' : option.id === picked ? 'wrong' : null
            return (
              <button
                key={option.id}
                style={{ ...s.option, ...(state && OPTION_STATE[state]) }}
                disabled={!!result || checking}
                onClick={() => { setPicked(option.id); submit({ text: label }) }}
              >
                {label}
              </button>
            )
          })}
        </div>
      )}

      {(exercise.startsWith('type_') || exercise === 'cloze') && (
        <>
          <form style={s.answerRow} onSubmit={onType}>
            <input
              ref={inputRef} aria-label="Your answer" style={s.input} autoComplete="off" autoCapitalize="off"
              spellCheck={false} value={answer} onChange={e => setAnswer(e.target.value)} disabled={!!result}
            />
            {!result && <button type="submit" style={s.primary} disabled={checking || !answer.trim()}>Check</button>}
          </form>
          {!result && !toNative && <CharPicker language={language} />}
        </>
      )}

      {error && <p style={s.error}>{error}</p>}

      {result && (
        <div style={s.feedback}>
          <p role="status" style={FEEDBACK[result.result]}>
            {result.result === 'correct' && '✓ Correct'}
            {result.result === 'almost' && <>≈ Almost — check the accents: <strong>{toNative ? mainTranslation(item) : item.display}</strong></>}
            {result.result === 'wrong' && <>✗ <strong>{toNative ? mainTranslation(item) : item.display}</strong></>}
          </p>
          <Example item={item} />
          <button ref={nextRef} style={s.primary} onClick={next}>
            {index + 1 === items.length ? 'See results' : 'Next →'}
          </button>
        </div>
      )}
    </div>
  )
}

function Prompt({ item, exercise }) {
  if (exercise === 'cloze') {
    return (
      <div>
        <p style={s.sentence}>{item.cloze}</p>
        <p style={s.hint}>{item.example_translation}</p>
      </div>
    )
  }
  if (exercise === 'choice_to_target' || exercise === 'type_to_target') {
    return <p style={s.big}>{allTranslations(item)}</p>
  }
  return (
    <p style={s.big}>
      {item.display}
      {item.pos && <span style={s.pos}> {item.pos}</span>}
    </p>
  )
}

function Example({ item }) {
  return (
    <p style={s.example}>
      {item.example} <span style={s.exampleEn}>— {item.example_translation}</span>
    </p>
  )
}

const OPTION_STATE = {
  right: { borderColor: '#15803d', background: '#dcfce7' },
  wrong: { borderColor: '#b91c1c', background: '#fee2e2' },
}

const FEEDBACK = {
  correct: { color: '#15803d', fontWeight: 600, margin: 0 },
  almost: { color: '#92400e', margin: 0 },
  wrong: { color: '#b91c1c', margin: 0 },
}

const s = {
  card: { background: '#f8f9fa', borderRadius: 12, padding: '1.5rem' },
  topRow: { display: 'flex', justifyContent: 'space-between', gap: '1rem', marginBottom: '0.75rem' },
  progress: { fontSize: '0.8rem', color: '#9ca3af' },
  instruction: { fontSize: '0.8rem', color: '#6b7280' },
  big: { fontSize: '1.7rem', fontWeight: 800, color: '#1e1b4b', margin: '0 0 1.25rem' },
  pos: { fontSize: '0.85rem', fontWeight: 400, color: '#9ca3af' },
  sentence: { fontSize: '1.2rem', color: '#1e1b4b', margin: '0 0 0.3rem' },
  hint: { fontSize: '0.9rem', color: '#6b7280', margin: '0 0 1rem' },
  reveal: { fontSize: '1.15rem', fontWeight: 600, color: '#4f46e5', margin: '0 0 0.5rem' },
  example: { fontSize: '0.88rem', color: '#374151', margin: '0.5rem 0 1rem' },
  exampleEn: { color: '#6b7280' },
  options: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '0.5rem', marginBottom: '0.75rem' },
  option: { padding: '0.7rem 0.9rem', border: '1px solid #d1d5db', borderRadius: 8, background: '#fff', cursor: 'pointer', fontSize: '0.98rem', textAlign: 'left', fontFamily: 'inherit', color: '#1f2937' },
  answerRow: { display: 'flex', gap: '0.6rem', marginBottom: '0.75rem' },
  input: { flex: 1, minWidth: 0, padding: '0.6rem 0.75rem', border: '1px solid #d1d5db', borderRadius: 8, fontSize: '1.05rem', fontFamily: 'inherit' },
  feedback: { marginTop: '0.25rem' },
  actions: { display: 'flex', gap: '0.6rem', flexWrap: 'wrap' },
  primary: { background: '#4f46e5', color: '#fff', border: 'none', borderRadius: 8, padding: '0.6rem 1.1rem', fontSize: '0.95rem', fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit', whiteSpace: 'nowrap' },
  secondary: { background: '#fff', color: '#374151', border: '1px solid #d1d5db', borderRadius: 8, padding: '0.6rem 1.1rem', fontSize: '0.95rem', cursor: 'pointer', fontFamily: 'inherit' },
  error: { color: '#b91c1c' },
}
