const LANG_CHARS = {
  french:   ['é', 'è', 'ê', 'ë', 'à', 'â', 'ä', 'ù', 'û', 'ü', 'ô', 'ö', 'î', 'ï', 'ç', 'œ', 'æ'],
  spanish:  ['á', 'é', 'í', 'ó', 'ú', 'ü', 'ñ', '¿', '¡'],
  english:  [],
  norwegian:['å', 'æ', 'ø'],
  galician: ['á', 'é', 'í', 'ó', 'ú', 'ü', 'ñ', 'â', 'ê', 'ô'],
}

// Use the native setters so React's onChange fires after the DOM update
const NATIVE_SETTERS = {
  INPUT: Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set,
  TEXTAREA: Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value')?.set,
}

// Accent buttons: insert into whichever text box has focus (input or textarea)
export default function CharPicker({ language, style }) {
  const chars = LANG_CHARS[language] || []
  if (!chars.length) return null

  function insert(char) {
    const el = document.activeElement
    const nativeSetter = el && NATIVE_SETTERS[el.tagName]
    if (!nativeSetter) return
    const start = el.selectionStart ?? el.value.length
    const end   = el.selectionEnd   ?? el.value.length
    nativeSetter.call(el, el.value.slice(0, start) + char + el.value.slice(end))
    el.dispatchEvent(new Event('input', { bubbles: true }))
    requestAnimationFrame(() => {
      el.focus()
      el.selectionStart = el.selectionEnd = start + char.length
    })
  }

  return (
    <div style={{ ...s.row, ...style }}>
      <span style={s.label}>Insert:</span>
      {chars.map(c => (
        <button
          key={c}
          style={s.btn}
          tabIndex={-1}
          onMouseDown={e => { e.preventDefault(); insert(c) }}
        >
          {c}
        </button>
      ))}
    </div>
  )
}

const s = {
  row: { display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '0.3rem', padding: '0.4rem 0.6rem', background: '#f3f4f6', borderRadius: 8, marginBottom: '0.75rem' },
  label: { fontSize: '0.75rem', color: '#9ca3af', marginRight: '0.2rem', whiteSpace: 'nowrap' },
  btn: { padding: '0.2rem 0.5rem', background: '#fff', border: '1px solid #d1d5db', borderRadius: 5, cursor: 'pointer', fontSize: '1rem', lineHeight: 1.4, fontFamily: 'inherit' },
}
