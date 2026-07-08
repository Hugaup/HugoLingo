import { useState, useRef, useEffect } from 'react'
import { api } from '../../api'

export default function ChatPanel({ initialMessages = [], systemPrompt = null, placeholder = 'Ask a question...' }) {
  const [messages, setMessages] = useState(initialMessages)
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  async function send() {
    const text = input.trim()
    if (!text || loading) return
    setInput('')

    const userMsg = { role: 'user', content: text }
    const history = [...messages, userMsg]
    setMessages(history)
    setLoading(true)

    try {
      const toSend = systemPrompt
        ? [{ role: 'system', content: systemPrompt }, ...history]
        : history
      const { content } = await api.chat(toSend)
      setMessages([...history, { role: 'assistant', content }])
    } catch (e) {
      setMessages([...history, { role: 'assistant', content: `Error: ${e.message}` }])
    } finally {
      setLoading(false)
    }
  }

  function handleKey(e) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() }
  }

  return (
    <div style={s.wrap}>
      <div style={s.history}>
        {messages.map((m, i) => (
          <div key={i} style={m.role === 'user' ? s.user : s.assistant}>
            <span style={s.bubble(m.role)}>{m.content}</span>
          </div>
        ))}
        {loading && (
          <div style={s.assistant}>
            <span style={{ ...s.bubble('assistant'), color: '#888' }}>...</span>
          </div>
        )}
        <div ref={bottomRef} />
      </div>
      <div style={s.inputRow}>
        <textarea
          style={s.textarea}
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKey}
          placeholder={placeholder}
          rows={2}
        />
        <button style={s.sendBtn} onClick={send} disabled={loading || !input.trim()}>
          Send
        </button>
      </div>
    </div>
  )
}

const s = {
  wrap: { border: '1px solid #e5e7eb', borderRadius: 10, overflow: 'hidden', background: '#fff' },
  history: { maxHeight: 320, overflowY: 'auto', padding: '1rem', display: 'flex', flexDirection: 'column', gap: '0.5rem' },
  user: { display: 'flex', justifyContent: 'flex-end' },
  assistant: { display: 'flex', justifyContent: 'flex-start' },
  bubble: (role) => ({
    maxWidth: '80%',
    padding: '0.5rem 0.85rem',
    borderRadius: role === 'user' ? '12px 12px 2px 12px' : '12px 12px 12px 2px',
    background: role === 'user' ? '#4f46e5' : '#f3f4f6',
    color: role === 'user' ? '#fff' : '#111',
    fontSize: '0.9rem',
    lineHeight: 1.5,
    whiteSpace: 'pre-wrap',
  }),
  inputRow: { display: 'flex', gap: '0.5rem', padding: '0.75rem', borderTop: '1px solid #e5e7eb', background: '#f9fafb' },
  textarea: { flex: 1, border: '1px solid #d1d5db', borderRadius: 8, padding: '0.5rem 0.75rem', fontSize: '0.9rem', resize: 'none', fontFamily: 'inherit' },
  sendBtn: { padding: '0 1.25rem', background: '#4f46e5', color: '#fff', border: 'none', borderRadius: 8, fontWeight: 600, cursor: 'pointer', fontSize: '0.9rem' },
}
