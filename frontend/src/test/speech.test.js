import { afterEach, describe, expect, it, vi } from 'vitest'
import { speak, voiceFor } from '../utils/speech'

const v = (name, lang, extra = {}) => ({ name, lang, ...extra })

// What Chrome on macOS lists: the English default first, robotic voices before good ones
const MAC_VOICES = [
  v('Samantha', 'en-US', { default: true }),
  v('Eddy (Spanish (Spain))', 'es-ES'),
  v('Eddy (Spanish (Mexico))', 'es-MX'),
  v('Paulina', 'es-MX'),
  v('Mónica', 'es-ES'),
  v('Thomas', 'fr-FR'),
]

describe('voiceFor', () => {
  it('picks a voice of the language, never the English default', () => {
    expect(voiceFor('es-ES', MAC_VOICES).name).toBe('Mónica')
    expect(voiceFor('fr-FR', MAC_VOICES).name).toBe('Thomas')
  })

  it('prefers the exact locale, then any voice of the language', () => {
    expect(voiceFor('es-ES', [v('Paulina', 'es-MX'), v('Jorge', 'es-ES')]).name).toBe('Jorge')
    expect(voiceFor('es-ES', [v('Samantha', 'en-US'), v('Paulina', 'es-MX')]).name).toBe('Paulina')
  })

  it('prefers a natural voice over a robotic one', () => {
    expect(voiceFor('es-ES', [v('Eddy (Spanish (Spain))', 'es-ES'), v('Google español', 'es-ES')]).name).toBe('Google español')
    expect(voiceFor('es-ES', [v('Samantha', 'en-US'), v('Eddy (Spanish (Spain))', 'es-ES')]).name).toBe('Eddy (Spanish (Spain))')
  })

  it('understands underscore and lowercase locales (Android)', () => {
    expect(voiceFor('es-ES', [v('English', 'en_US'), v('Spanish', 'es_ES')]).name).toBe('Spanish')
    expect(voiceFor('es-ES', [v('Spanish', 'es-es')]).name).toBe('Spanish')
  })

  it('returns null when no voice of the language is installed', () => {
    expect(voiceFor('es-ES', [v('Samantha', 'en-US')])).toBeNull()
    expect(voiceFor('es-ES', [])).toBeNull()
  })
})

describe('speak', () => {
  afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers() })

  function install(initialVoices) {
    const spoken = []
    const listeners = new Set()
    const synth = {
      voices: initialVoices,
      getVoices: () => synth.voices,
      addEventListener: (_, fn) => listeners.add(fn),
      removeEventListener: (_, fn) => listeners.delete(fn),
      cancel: vi.fn(),
      speak: u => spoken.push({ text: u.text, lang: u.lang, voice: u.voice?.name }),
      loadVoices: voices => { synth.voices = voices; [...listeners].forEach(fn => fn()) },
      listeners,
    }
    vi.stubGlobal('SpeechSynthesisUtterance', class { constructor(text) { this.text = text } })
    vi.stubGlobal('speechSynthesis', synth)
    return { synth, spoken }
  }

  it('reads Spanish with a Spanish voice', () => {
    const { spoken } = install(MAC_VOICES)
    expect(speak('Hola, ¿qué tal?', 'spanish')).toBe(true)
    expect(spoken).toEqual([{ text: 'Hola, ¿qué tal?', lang: 'es-ES', voice: 'Mónica' }])
  })

  it('waits for the voices to load instead of speaking with the default voice', async () => {
    const { synth, spoken } = install([])  // Chrome before `voiceschanged`
    speak('Buenos días', 'spanish')
    expect(spoken).toEqual([])
    synth.loadVoices(MAC_VOICES)
    await vi.waitFor(() => expect(spoken).toEqual([{ text: 'Buenos días', lang: 'es-ES', voice: 'Mónica' }]))
    expect(synth.listeners.size).toBe(0)
  })

  it('still speaks if the voices never load', async () => {
    vi.useFakeTimers()
    const { spoken } = install([])
    speak('Buenos días', 'spanish')
    await vi.advanceTimersByTimeAsync(2000)
    expect(spoken).toEqual([{ text: 'Buenos días', lang: 'es-ES', voice: undefined }])
  })
})
