import { useEffect, useRef, useState } from 'react'
import { api } from '../../api'
import CharPicker from '../conjugation/CharPicker'
import ClickableText from '../reading/ClickableText'
import SessionSummary from '../SessionSummary'
import SpeakButton from '../SpeakButton'
import { canSpeak, speak } from '../../utils/speech'
import { markChanges } from '../../utils/conversation'

// One role-play. The AI opens; each learner message is checked by the server
// (the correction appears under it) while the AI's reply streams in.
// Finish shows a recap of the corrections.
export default function ConversationChat({ language, scenario, onRestart }) {
  // { id, role, content, failed?, check?: { status: 'checking'|'done'|'failed', ...checkResponse } }
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [streamingId, setStreamingId] = useState(null)  // the AI message being written
  const [finished, setFinished] = useState(false)
  const [readAloud, setReadAloud] = useState(false)
  const nextId = useRef(0)
  const opened = useRef(false)
  const readAloudRef = useRef(readAloud)  // read when a reply finishes
  const bottomRef = useRef(null)
  const inputRef = useRef(null)
  const replying = streamingId !== null

  useEffect(() => { readAloudRef.current = readAloud }, [readAloud])
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }) }, [messages])

  function add(message) {
    const id = nextId.current++
    setMessages(ms => [...ms, { id, ...message }])
    return id
  }
  const patch = (id, change) => setMessages(ms => ms.map(m => (m.id === id ? { ...m, ...change } : m)))

  async function reply(history) {
    const id = add({ role: 'assistant', content: '' })
    setStreamingId(id)
    try {
      const text = await api.conversationReply(
        language, scenario.id, history.map(({ role, content }) => ({ role, content })),
        soFar => patch(id, { content: soFar }),
      )
      if (readAloudRef.current) speak(text, language)
    } catch (e) {
      patch(id, { content: e.message, failed: true })
    } finally {
      setStreamingId(null)
      inputRef.current?.focus()
    }
  }

  useEffect(() => {
    if (opened.current) return
    opened.current = true
    reply([])
    // The AI opens once, when the conversation starts
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function send() {
    const text = input.trim()
    if (!text || replying) return
    setInput('')
    const said = messages.filter(m => !m.failed && m.content)
    const previous = said.findLast(m => m.role === 'assistant')?.content ?? null
    const id = add({ role: 'user', content: text, check: { status: 'checking' } })
    api.checkMessage(language, scenario.id, previous, text)
      .then(res => patch(id, { check: { status: 'done', ...res } }))
      .catch(() => patch(id, { check: { status: 'failed' } }))
    reply([...said, { role: 'user', content: text }])
  }

  if (finished) {
    const checked = messages.filter(m => m.role === 'user' && m.check.status === 'done')
    return (
      <SessionSummary
        language={language}
        results={checked.map((m, i) => ({
          label: m.check.explanation || `Message ${i + 1}`,
          answer: m.content,
          expected: m.check.corrected ?? m.content,
          result: m.check.result,
        }))}
        onRestart={onRestart}
        restartLabel="New conversation"
        // Verb mistakes were added to the review queue
        showReviewLink={checked.some(m => m.check.verb_mistakes.length > 0)}
      />
    )
  }

  const userTurns = messages.filter(m => m.role === 'user').length

  return (
    <div>
      <p style={s.goal}><strong>Your goal:</strong> {scenario.goal}</p>

      <div style={s.log} role="log" aria-label="Conversation">
        {messages.map(m => (m.role === 'assistant'
          ? <AiLine key={m.id} message={m} language={language} streaming={m.id === streamingId} />
          : <UserLine key={m.id} message={m} />
        ))}
        <div ref={bottomRef} />
      </div>

      <form style={s.inputRow} onSubmit={e => { e.preventDefault(); send() }}>
        <textarea
          ref={inputRef}
          aria-label="Your message"
          style={s.textarea}
          rows={2}
          value={input}
          placeholder="Write your reply…"
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
        />
        <button type="submit" style={s.send} disabled={replying || !input.trim()}>Send</button>
      </form>
      <CharPicker language={language} style={s.picker} />

      <div style={s.footer}>
        {canSpeak() ? (
          <label style={s.toggle}>
            <input type="checkbox" checked={readAloud} onChange={e => setReadAloud(e.target.checked)} /> Read replies aloud
          </label>
        ) : <span />}
        <button style={s.finish} onClick={() => setFinished(true)} disabled={userTurns === 0 || replying}>
          Finish
        </button>
      </div>
    </div>
  )
}

function AiLine({ message, language, streaming }) {
  if (!message.content) {
    return <div style={s.aiRow}><span style={{ ...s.aiBubble, ...s.typing }} aria-label="The AI is typing">…</span></div>
  }
  if (message.failed) {
    return <div style={s.aiRow}><span style={{ ...s.aiBubble, ...s.failed }}>{message.content}</span></div>
  }
  return (
    <div style={s.aiRow}>
      <div style={s.aiBubble}>
        {/* Words become clickable (meaning, add to my words) once the reply is complete */}
        {streaming ? <p style={s.text}>{message.content}</p> : <ClickableText text={message.content} language={language} style={s.text} />}
        {!streaming && (
          <div style={s.tools}>
            <SpeakButton text={message.content} language={language} label="Listen to this message" />
            <Translate text={message.content} />
          </div>
        )}
      </div>
    </div>
  )
}

function Translate({ text }) {
  const [translation, setTranslation] = useState(null)
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)

  async function toggle() {
    if (translation) { setOpen(o => !o); return }
    setLoading(true)
    try {
      const res = await api.chat([
        { role: 'system', content: 'Translate the text into natural English. Reply with the translation only.' },
        { role: 'user', content: text },
      ])
      setTranslation(res.content.trim())
    } catch {
      setTranslation("Couldn't translate this right now.")
    } finally {
      setOpen(true)
      setLoading(false)
    }
  }

  return (
    <>
      <button type="button" style={s.toolBtn} onClick={toggle} disabled={loading}>
        {loading ? 'Translating…' : open ? 'Hide translation' : 'Translate'}
      </button>
      {open && <p style={s.translation}>{translation}</p>}
    </>
  )
}

function UserLine({ message }) {
  return (
    <div style={s.userRow}>
      <span style={s.userBubble}>{message.content}</span>
      <Correction message={message} />
    </div>
  )
}

// Compact, under the learner's message: a tick, or the fixed sentence + one line why
function Correction({ message }) {
  const { check } = message
  if (check.status === 'checking') return <span style={s.checking}>Checking…</span>
  if (check.status === 'failed') return <span style={s.checking}>Couldn't check this one</span>
  if (check.result === 'correct') return <span style={s.correct} aria-label="Correct">✓</span>
  return (
    <div style={s.correction} aria-label="Correction">
      <span style={check.result === 'almost' ? s.almost : s.wrong}>
        {check.result === 'almost' ? '≈ Accents: ' : '✗ '}
      </span>
      {markChanges(message.content, check.corrected).map((w, i) => (
        <span key={i} style={w.changed ? s.changed : undefined}>{w.word} </span>
      ))}
      {check.explanation && <span style={s.why}>{check.explanation}</span>}
    </div>
  )
}

const s = {
  goal: { background: '#eef2ff', color: '#1e1b4b', borderRadius: 10, padding: '0.7rem 1rem', fontSize: '0.9rem', margin: '0 0 1rem' },
  log: { display: 'flex', flexDirection: 'column', gap: '0.75rem', marginBottom: '1rem' },
  aiRow: { display: 'flex', justifyContent: 'flex-start' },
  aiBubble: { maxWidth: '80%', background: '#f3f4f6', color: '#111827', borderRadius: '14px 14px 14px 4px', padding: '0.6rem 0.9rem' },
  text: { margin: 0, fontSize: '1rem', lineHeight: 1.5 },
  typing: { color: '#9ca3af' },
  failed: { color: '#b91c1c' },
  tools: { display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '0.4rem', marginTop: '0.3rem' },
  toolBtn: { background: 'none', border: 'none', color: '#4f46e5', cursor: 'pointer', padding: 0, fontSize: '0.78rem', fontFamily: 'inherit' },
  translation: { flexBasis: '100%', margin: '0.2rem 0 0', fontSize: '0.85rem', color: '#6b7280' },
  userRow: { display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '0.25rem' },
  userBubble: { maxWidth: '80%', background: '#4f46e5', color: '#fff', borderRadius: '14px 14px 4px 14px', padding: '0.6rem 0.9rem', fontSize: '1rem', lineHeight: 1.5, whiteSpace: 'pre-wrap' },
  checking: { fontSize: '0.75rem', color: '#9ca3af' },
  correct: { fontSize: '0.8rem', color: '#15803d', fontWeight: 700 },
  correction: { maxWidth: '80%', fontSize: '0.85rem', color: '#374151', textAlign: 'right' },
  almost: { color: '#92400e', fontWeight: 600 },
  wrong: { color: '#b91c1c', fontWeight: 600 },
  changed: { color: '#15803d', fontWeight: 700 },
  why: { display: 'block', fontSize: '0.78rem', color: '#6b7280' },
  inputRow: { display: 'flex', gap: '0.5rem' },
  textarea: { flex: 1, minWidth: 0, border: '1px solid #d1d5db', borderRadius: 8, padding: '0.55rem 0.75rem', fontSize: '1rem', resize: 'none', fontFamily: 'inherit' },
  send: { padding: '0 1.25rem', background: '#4f46e5', color: '#fff', border: 'none', borderRadius: 8, fontWeight: 600, cursor: 'pointer', fontSize: '0.95rem', fontFamily: 'inherit' },
  picker: { marginTop: '0.5rem' },
  footer: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '0.75rem' },
  toggle: { fontSize: '0.85rem', color: '#374151', display: 'flex', alignItems: 'center', gap: '0.35rem' },
  finish: { background: '#fff', color: '#374151', border: '1px solid #d1d5db', borderRadius: 8, padding: '0.45rem 1rem', fontSize: '0.9rem', cursor: 'pointer', fontFamily: 'inherit' },
}
