import { canSpeak, speak } from '../utils/speech'

// 🔊 button that reads `text` aloud. Renders nothing where speech isn't supported.
export default function SpeakButton({ text, language, slow = false, label, style }) {
  if (!canSpeak()) return null
  return (
    <button
      type="button"
      style={{ ...s.button, ...style }}
      aria-label={label ?? `Listen: ${text}`}
      title={label ?? 'Listen'}
      onClick={e => { e.stopPropagation(); speak(text, language, { slow }) }}
    >
      {slow ? '🐢' : '🔊'}
    </button>
  )
}

const s = {
  button: { background: 'none', border: 'none', cursor: 'pointer', fontSize: '0.95em', padding: '0 0.25rem', lineHeight: 1, verticalAlign: 'middle' },
}
