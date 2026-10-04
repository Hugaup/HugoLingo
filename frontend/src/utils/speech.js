// Pronunciation with the browser's built-in speech synthesis: free, offline,
// no backend involved. Voices depend on the OS/browser. An utterance without an
// explicit voice is read by the browser's default voice (usually English) even
// when its `lang` says Spanish, so we always pick a voice of the right language.

const VOICE_LANG = {
  spanish: 'es-ES',
  french: 'fr-FR',
  english: 'en-GB',
  norwegian: 'nb-NO',
  galician: 'gl-ES',
}

// macOS "Eloquence" and novelty voices: understandable but robotic, only used
// when nothing better is installed for the language.
const LOW_QUALITY = /^(Eddy|Flo|Grandma|Grandpa|Reed|Rocko|Sandy|Shelley|Albert|Bad News|Bahh|Bells|Boing|Bubbles|Cellos|Fred|Good News|Jester|Junior|Kathy|Organ|Ralph|Superstar|Trinoids|Whisper|Wobble|Zarvox)\b/

const VOICES_TIMEOUT_MS = 1500

export function canSpeak() {
  return typeof window !== 'undefined'
    && 'speechSynthesis' in window
    && typeof window.SpeechSynthesisUtterance === 'function'
}

// "es_ES" (Android), "es-es" and "es-ES" are the same locale
const normLang = lang => (lang ?? '').replace('_', '-').toLowerCase()

// Best installed voice for `lang` ("es-ES"), never one of another language:
// exact locale first (es-ES over es-MX), then natural over robotic voices.
export function voiceFor(lang, voices) {
  const want = normLang(lang)
  const base = want.split('-')[0]
  let best = null
  let bestScore = -1
  for (const v of voices) {
    const have = normLang(v.lang)
    if (have.split('-')[0] !== base) continue
    const score = (have === want ? 2 : 0) + (LOW_QUALITY.test(v.name ?? '') ? 0 : 1)
    if (score > bestScore) { best = v; bestScore = score }
  }
  return best
}

// Chrome fills the voice list asynchronously: getVoices() is [] until the
// `voiceschanged` event, and speaking before then uses the default (English) voice.
// Returns null when the voices are already there.
function voicesLoading() {
  const synth = window.speechSynthesis
  if ((synth.getVoices?.() ?? []).length || typeof synth.addEventListener !== 'function') return null
  return new Promise(resolve => {
    const done = () => {
      clearTimeout(timer)
      synth.removeEventListener('voiceschanged', done)
      resolve()
    }
    const timer = setTimeout(done, VOICES_TIMEOUT_MS)
    synth.addEventListener('voiceschanged', done)
  })
}

// Ask for the voices at load time so Chrome has them by the first click.
if (canSpeak()) window.speechSynthesis.getVoices?.()

function say(text, lang, rate) {
  const utterance = new window.SpeechSynthesisUtterance(text)
  utterance.lang = lang
  const voice = voiceFor(lang, window.speechSynthesis.getVoices?.() ?? [])
  if (voice) utterance.voice = voice
  utterance.rate = rate
  window.speechSynthesis.cancel()  // a new click interrupts whatever was playing
  window.speechSynthesis.speak(utterance)
}

// Read `text` aloud in `language`; `slow` for dictation replays. Returns false if unsupported.
export function speak(text, language, { slow = false } = {}) {
  if (!canSpeak() || !text) return false
  const lang = VOICE_LANG[language] ?? 'en-GB'
  const rate = slow ? 0.65 : 0.9
  const loading = voicesLoading()
  if (loading) loading.then(() => say(text, lang, rate))
  else say(text, lang, rate)
  return true
}
