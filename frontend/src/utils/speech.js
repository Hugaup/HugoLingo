// Pronunciation with the browser's built-in speech synthesis: free, offline,
// no backend involved. Voices depend on the OS/browser; if a language has no
// voice installed the browser falls back to its default.

const VOICE_LANG = {
  spanish: 'es-ES',
  french: 'fr-FR',
  english: 'en-GB',
  norwegian: 'nb-NO',
  galician: 'gl-ES',
}

export function canSpeak() {
  return typeof window !== 'undefined'
    && 'speechSynthesis' in window
    && typeof window.SpeechSynthesisUtterance === 'function'
}

function voiceFor(lang) {
  const voices = window.speechSynthesis.getVoices?.() ?? []
  return voices.find(v => v.lang === lang) ?? voices.find(v => v.lang?.startsWith(lang.slice(0, 2)))
}

// Read `text` aloud in `language`; `slow` for dictation replays. Returns false if unsupported.
export function speak(text, language, { slow = false } = {}) {
  if (!canSpeak() || !text) return false
  const lang = VOICE_LANG[language] ?? 'en-GB'
  const utterance = new window.SpeechSynthesisUtterance(text)
  utterance.lang = lang
  const voice = voiceFor(lang)
  if (voice) utterance.voice = voice
  utterance.rate = slow ? 0.65 : 0.9
  window.speechSynthesis.cancel()  // a new click interrupts whatever was playing
  window.speechSynthesis.speak(utterance)
  return true
}
