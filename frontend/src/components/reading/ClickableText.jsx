import { useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../../api'
import SpeakButton from '../SpeakButton'

// Splits text into words (kept, odd indices) and everything between them
const WORD = /(\p{L}+(?:['’-]\p{L}+)*)/u

// The sentence around a character offset, as context for the lookup
function sentenceAround(text, offset) {
  const before = text.slice(0, offset)
  const start = Math.max(before.lastIndexOf('. '), before.lastIndexOf('! '), before.lastIndexOf('? ')) + 1
  const after = text.slice(offset).search(/[.!?](\s|$)/)
  return text.slice(start, after === -1 ? text.length : offset + after + 1).trim()
}

// A reading passage where every word can be clicked to see its meaning
// and be added to the user's vocabulary.
export default function ClickableText({ text, language, style }) {
  const [active, setActive] = useState(null)  // { index, word, sentence, top, left }
  const boxRef = useRef(null)

  // Each piece of the text with its character offset (for the sentence context)
  const tokens = useMemo(() => {
    const out = []
    let at = 0
    for (const part of text.split(WORD)) {
      out.push({ part, at })
      at += part.length
    }
    return out
  }, [text])

  const parts = tokens.map(({ part, at }, i) => {
    if (i % 2 === 0) return <span key={i}>{part}</span>
    return (
      <button
        key={i}
        type="button"
        style={active?.index === i ? { ...s.word, ...s.wordActive } : s.word}
        aria-label={`What does "${part}" mean?`}
        onClick={e => {
          if (active?.index === i) { setActive(null); return }
          const box = boxRef.current.getBoundingClientRect()
          const btn = e.currentTarget.getBoundingClientRect()
          setActive({
            index: i, word: part, sentence: sentenceAround(text, at),
            top: btn.bottom - box.top + 6,
            left: Math.max(0, Math.min(btn.left - box.left, box.width - 290)),
          })
        }}
      >
        {part}
      </button>
    )
  })

  return (
    <div ref={boxRef} style={s.box}>
      <p style={style}>{parts}</p>
      {active && (
        <WordPopover
          key={active.index}
          language={language}
          word={active.word}
          sentence={active.sentence}
          position={{ top: active.top, left: active.left }}
          onClose={() => setActive(null)}
        />
      )}
    </div>
  )
}

function WordPopover({ language, word, sentence, position, onClose }) {
  const [data, setData]   = useState(null)
  const [error, setError] = useState(null)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    api.lookupWord(language, word, sentence)
      .then(d => { setData(d); setSaved(d.in_my_words) })
      .catch(e => setError(e.message))
  }, [language, word, sentence])

  useEffect(() => {
    const onKey = e => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  async function save() {
    setSaving(true)
    try {
      await api.addMyWord(language, { lemma: data.lemma, translation: data.translation, pos: data.pos, example: sentence })
      setSaved(true)
    } catch (e) {
      setError(e.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div role="dialog" aria-label={`Meaning of ${word}`} style={{ ...s.popover, ...position }}>
      <button type="button" style={s.close} aria-label="Close" onClick={onClose}>×</button>
      {!data && !error && <p style={s.muted}>Looking up “{word}”…</p>}
      {error && <p style={s.error}>{error}</p>}
      {data && (
        <>
          <p style={s.lemma}>
            {data.lemma}
            {data.pos && <span style={s.pos}> {data.pos}</span>}
            <SpeakButton text={data.lemma} language={language} />
          </p>
          <p style={s.translation}>{data.translation.split(';').map(t => t.trim()).join(' / ')}</p>
          {data.source === 'ai' || data.source === 'dictionary'
            ? <p style={s.source}>AI translation — may be imperfect</p>
            : <p style={s.source}>From the vocabulary list</p>}
          {saved
            ? <p style={s.saved}>✓ In my words</p>
            : <button type="button" style={s.add} onClick={save} disabled={saving}>{saving ? 'Adding…' : '+ Add to my words'}</button>}
        </>
      )}
    </div>
  )
}

const s = {
  box: { position: 'relative' },
  word: { background: 'none', border: 'none', padding: 0, margin: 0, font: 'inherit', color: 'inherit', cursor: 'pointer', textDecoration: 'underline dotted #c7d2fe', textUnderlineOffset: 3 },
  wordActive: { background: '#e0e7ff', borderRadius: 3, textDecoration: 'none' },
  popover: { position: 'absolute', zIndex: 10, width: 280, background: '#fff', border: '1px solid #e5e7eb', borderRadius: 10, boxShadow: '0 6px 20px rgba(0,0,0,0.12)', padding: '0.8rem 0.9rem', fontFamily: 'system-ui, sans-serif' },
  close: { position: 'absolute', top: 4, right: 8, background: 'none', border: 'none', fontSize: '1.2rem', color: '#9ca3af', cursor: 'pointer' },
  lemma: { fontWeight: 800, fontSize: '1.1rem', color: '#1e1b4b', margin: '0 1.2rem 0.2rem 0' },
  pos: { fontWeight: 400, fontSize: '0.8rem', color: '#9ca3af' },
  translation: { color: '#374151', margin: '0 0 0.35rem' },
  source: { fontSize: '0.72rem', color: '#9ca3af', margin: '0 0 0.6rem' },
  add: { background: '#4f46e5', color: '#fff', border: 'none', borderRadius: 8, padding: '0.4rem 0.8rem', fontSize: '0.85rem', fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' },
  saved: { color: '#15803d', fontWeight: 600, fontSize: '0.85rem', margin: 0 },
  muted: { color: '#6b7280', margin: 0, fontSize: '0.9rem' },
  error: { color: '#b91c1c', margin: 0, fontSize: '0.88rem' },
}
