import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import FeedbackPanel from '../components/FeedbackPanel'
import StatusBadge from '../components/StatusBadge'
import CharPicker from '../components/conjugation/CharPicker'
import { BLANK } from '../utils/grammar'
import { checkUpLabel } from '../utils/reviewStatus'
import { color, radius, ui } from '../theme'

// One sheet of a grammar topic, like a lingua.com exercise page: every
// question on one page, each marked as soon as it's answered, a running
// "answered X of N" count, and a restart. :sheet is a number or "review".
export default function GrammarSheet() {
  const { language, topic, sheet } = useParams()
  // Bumping the round remounts the sheet: answers cleared (a review sheet is fetched afresh)
  const [round, setRound] = useState(0)
  return (
    <SheetRun
      key={`${topic}-${sheet}-${round}`}
      language={language}
      topicId={topic}
      sheetParam={sheet}
      onRestart={() => setRound(r => r + 1)}
    />
  )
}

function SheetRun({ language, topicId, sheetParam, onRestart }) {
  const navigate = useNavigate()
  const [sheet, setSheet] = useState(null)
  const [error, setError] = useState(null)
  const [answers, setAnswers] = useState({})   // question id → the server's grading
  const [pending, setPending] = useState(null) // question id being checked
  const [standing, setStanding] = useState(null) // the topic's status after the latest answer

  useEffect(() => {
    api.getGrammarSheet(language, topicId, sheetParam)
      .then(setSheet)
      .catch(e => setError(e.message))
  }, [language, topicId, sheetParam])

  const topicPath = `/practice/${language}/grammar/${topicId}`

  if (!sheet) return <Page>{error ? <p style={s.error}>{error}</p> : <p style={s.muted}>Loading…</p>}</Page>

  const total = sheet.questions.length
  const answered = Object.keys(answers).length
  const right = Object.values(answers).filter(a => a.is_correct).length
  const typing = sheet.questions.some(q => q.kind === 'correct')
  const next = sheet.number && sheet.number < sheet.sheet_count ? sheet.number + 1 : null

  async function submit(question, given) {
    if (answers[question.id] || pending) return
    setPending(question.id)
    setError(null)
    try {
      const res = await api.answerGrammar(language, topicId, question.id, given)
      setAnswers(a => ({ ...a, [question.id]: { ...res, given } }))
      setStanding({ status: res.status, due_at: res.due_at })
    } catch (e) {
      setError(e.message)
    } finally {
      setPending(null)
    }
  }

  return (
    <Page>
      <button style={s.back} onClick={() => navigate(topicPath)}>← {sheet.topic_title}</button>
      <h1 style={s.title}>
        {sheet.topic_title}
        <span style={s.which}>
          {sheet.number ? `Exercise ${sheet.number}` : 'Review'}
          {sheet.number && sheet.title ? ` · ${sheet.title}` : ''}
        </span>
      </h1>
      <p style={s.instruct}>
        {typing ? 'Each sentence has one mistake: type the whole sentence again, corrected.'
          : 'Choose the right option for each gap.'}
      </p>

      <div style={s.bar}>
        <span>
          You have answered <strong>{answered}</strong> of <strong>{total}</strong> questions
          {answered > 0 && <span style={s.right}> · {right} right</span>}
        </span>
        <button style={s.restart} onClick={onRestart}>Restart this exercise</button>
        {typing && <CharPicker language={language} style={s.picker} />}
      </div>
      {error && <p style={s.error}>{error}</p>}

      <ol style={s.questions}>
        {sheet.questions.map((q, i) => (
          q.kind === 'choice'
            ? <ChoiceQuestion key={q.id} number={i + 1} question={q} result={answers[q.id]} busy={!!pending} onAnswer={submit} />
            : <CorrectionQuestion key={q.id} number={i + 1} question={q} result={answers[q.id]} busy={pending === q.id} onAnswer={submit} />
        ))}
      </ol>

      {answered === total && (
        <section style={s.results} aria-label="Sheet results">
          <p style={s.score}>{right} / {total} correct</p>
          {standing?.status && (
            <p style={s.standing}>
              {sheet.topic_title}: <StatusBadge status={standing.status} />
              {standing.status === 'getting_there' && <span style={s.checkUp}>{checkUpLabel(standing.due_at)}</span>}
            </p>
          )}
          <div style={s.actions}>
            {next && (
              <button style={s.primary} onClick={() => navigate(`${topicPath}/${next}`)}>Next exercise →</button>
            )}
            <button style={next ? s.secondary : s.primary} onClick={onRestart}>Do it again</button>
            <button style={s.secondary} onClick={() => navigate(topicPath)}>Back to the topic</button>
          </div>
        </section>
      )}
    </Page>
  )
}

function Page({ children }) {
  return <div style={s.page}>{children}</div>
}

// A gap sentence with four options; the gap fills in once it's answered
function ChoiceQuestion({ number, question, result, busy, onAnswer }) {
  const [before, after] = question.text.split(BLANK)
  return (
    <li style={s.card}>
      <p style={s.sentence}>
        <span style={s.number}>{number}.</span>
        {before}
        <span style={result ? s.gapFilled : s.gap}>{result ? result.answer : '?'}</span>
        {after}
      </p>
      <div role="group" aria-label={`Options for question ${number}`} style={s.options}>
        {question.options.map(option => {
          const isAnswer = result && option === result.answer
          const isMistake = result && option === result.given && !result.is_correct
          const look = isAnswer ? s.optionRight : isMistake ? s.optionWrong : result ? s.optionDone : null
          return (
            <button
              key={option}
              style={look ? { ...s.option, ...look } : s.option}
              disabled={!!result || busy}
              onClick={() => onAnswer(question, option)}
            >
              {isAnswer && '✓ '}{isMistake && '✗ '}{option}
            </button>
          )
        })}
      </div>
      {result && <p style={result.is_correct ? s.whyRight : s.whyWrong}>{result.explanation}</p>}
    </li>
  )
}

// Find the mistake: retype the sentence corrected
function CorrectionQuestion({ number, question, result, busy, onAnswer }) {
  const [text, setText] = useState('')
  const id = `correction-${question.id}`
  function check(e) {
    e.preventDefault()
    if (text.trim()) onAnswer(question, text.trim())
  }
  return (
    <li style={s.card}>
      <p style={s.sentence}><span style={s.number}>{number}.</span>{question.text}</p>
      {result ? (
        <FeedbackPanel result={{
          is_correct: result.is_correct, almost: result.result === 'almost',
          explanation: result.explanation, correct_answer: result.sentence, fix: result.fix,
        }} />
      ) : (
        <form style={s.correctRow} onSubmit={check}>
          <label htmlFor={id} style={s.srOnly}>Corrected sentence {number}</label>
          <input
            id={id} style={s.input} value={text} onChange={e => setText(e.target.value)}
            autoComplete="off" autoCapitalize="off" spellCheck={false} placeholder="Type the corrected sentence…"
          />
          <button type="submit" style={s.check} disabled={busy || !text.trim()}>Check</button>
        </form>
      )}
    </li>
  )
}

const gapBase = { display: 'inline-block', minWidth: '3.5rem', textAlign: 'center', margin: '0 0.25rem', padding: '0 0.4rem', fontWeight: 700 }

const s = {
  page: { ...ui.page, maxWidth: 680 },
  back: ui.back,
  title: { ...ui.h1, display: 'flex', flexDirection: 'column', gap: '0.2rem', marginBottom: '0.4rem' },
  which: { fontSize: '1rem', fontWeight: 600, color: color.primary },
  instruct: { color: color.muted, margin: '0 0 1rem', fontSize: '0.92rem' },
  muted: { color: color.muted },
  error: ui.error,
  bar: { position: 'sticky', top: 0, zIndex: 1, display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.5rem 1rem', background: color.bg, borderBottom: `1px solid ${color.border}`, padding: '0.6rem 0', marginBottom: '1rem', fontSize: '0.92rem', color: color.body },
  right: { color: color.success, fontWeight: 600 },
  restart: { ...ui.link, fontSize: '0.85rem' },
  picker: { flexBasis: '100%', margin: 0 },
  questions: { listStyle: 'none', padding: 0, margin: 0, display: 'grid', gap: '0.75rem' },
  card: { ...ui.panel, padding: '1rem 1.1rem' },
  sentence: { fontSize: '1.08rem', lineHeight: 1.7, color: color.text, margin: '0 0 0.6rem' },
  number: { fontWeight: 700, color: color.faint, marginRight: '0.45rem' },
  gap: { ...gapBase, color: color.faint, borderBottom: `2px solid ${color.borderStrong}` },
  gapFilled: { ...gapBase, color: color.success, background: color.successSoft, borderRadius: 6 },
  options: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(9rem, 1fr))', gap: '0.4rem' },
  option: { ...ui.secondary, whiteSpace: 'normal', textAlign: 'left', padding: '0.5rem 0.8rem' },
  optionRight: { borderColor: color.success, background: color.successSoft, color: color.success, fontWeight: 700, opacity: 1 },
  optionWrong: { borderColor: color.danger, background: color.dangerSoft, color: color.danger, opacity: 1 },
  optionDone: { opacity: 0.55 },
  whyRight: { margin: '0.5rem 0 0', fontSize: '0.88rem', color: color.success },
  whyWrong: { margin: '0.5rem 0 0', fontSize: '0.88rem', color: color.danger },
  correctRow: { display: 'flex', gap: '0.5rem', flexWrap: 'wrap' },
  input: { flex: '1 1 14rem', minWidth: 0, padding: '0.55rem 0.75rem', borderWidth: 1, borderStyle: 'solid', borderColor: color.borderStrong, borderRadius: radius.sm, fontSize: '1rem', fontFamily: 'inherit' },
  check: { ...ui.primary, padding: '0.5rem 1rem' },
  srOnly: { position: 'absolute', width: 1, height: 1, overflow: 'hidden', clip: 'rect(0 0 0 0)', whiteSpace: 'nowrap' },
  results: { ...ui.panel, marginTop: '1.25rem', borderWidth: 2, borderStyle: 'solid', borderColor: color.primaryBorder },
  score: { fontSize: '1.4rem', fontWeight: 800, color: color.ink, margin: '0 0 0.4rem' },
  standing: { display: 'flex', alignItems: 'center', gap: '0.4rem', flexWrap: 'wrap', margin: '0 0 1rem', color: color.body, fontSize: '0.92rem' },
  checkUp: { color: color.muted, fontSize: '0.85rem' },
  actions: { display: 'flex', gap: '0.6rem', flexWrap: 'wrap' },
  primary: ui.primary,
  secondary: ui.secondary,
}
