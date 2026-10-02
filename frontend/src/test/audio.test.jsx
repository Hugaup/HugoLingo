import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { pickExercise, wordDiff } from '../utils/vocab'
import { ALICE, calls, mockBackend, renderAppAt } from './helpers'

const ME = { 'GET /auth/me': { body: ALICE } }
const OVERVIEW = {
  available: true,
  groups: [{ kind: 'word', topic: 'food', total: 25, seen: 3, learned: 2, due: 1 }],
  total: 25, learned: 2, due: 1,
}
const pan = (extra = {}) => ({
  id: 7, kind: 'word', text: 'pan', article: 'el', display: 'el pan', translation: 'bread', pos: 'noun',
  topic: 'food', level: 1, example: 'Compro pan en la panadería.', example_translation: 'I buy bread at the bakery.',
  box: 3, is_new: false, cloze: 'Compro ___ en la panadería.', options: [], ...extra,
})

// jsdom has no speech synthesis: fake the browser API and record what gets said
let spoken
function installSpeech() {
  spoken = []
  vi.stubGlobal('SpeechSynthesisUtterance', class { constructor(text) { this.text = text } })
  vi.stubGlobal('speechSynthesis', {
    getVoices: () => [{ lang: 'es-ES', name: 'Mónica' }],
    cancel: vi.fn(),
    speak: u => spoken.push({ text: u.text, lang: u.lang, rate: u.rate, voice: u.voice?.name }),
  })
}

describe('helpers', () => {
  it('wordDiff marks misheard words, ignoring case, accents and punctuation', () => {
    expect(wordDiff('Compro pan en la panadería.', 'compro pon en la panaderia')).toEqual([
      { word: 'Compro', ok: true }, { word: 'pan', ok: false }, { word: 'en', ok: true },
      { word: 'la', ok: true }, { word: 'panadería.', ok: true },
    ])
    expect(wordDiff('Buenos días', 'Buenos').map(w => w.ok)).toEqual([true, false])
  })

  it('listening only appears when the browser can speak', () => {
    const item = pan({ box: 4 })
    expect(pickExercise(item, 'listening', 0, false)).toBe('cloze')
    expect(pickExercise(item, 'listening', 0, true)).toBe('dictation')
    expect([0, 1].map(i => pickExercise(item, 'mixed', i, true))).toEqual(['cloze', 'dictation'])
    expect([0, 1].map(i => pickExercise(item, 'mixed', i, false))).toEqual(['cloze', 'cloze'])
  })
})

describe('without speech support', () => {
  it('hides the Listening mode and the speaker buttons', async () => {
    mockBackend({ ...ME, 'GET /vocab/spanish/overview': { body: OVERVIEW }, 'GET /vocab/spanish/session': { body: [pan({ is_new: true, box: null })] } })
    renderAppAt('/practice/spanish/vocabulary')
    expect(await screen.findByRole('radio', { name: 'Mixed' })).toBeInTheDocument()
    expect(screen.queryByRole('radio', { name: 'Listening' })).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Review now' }))
    expect(await screen.findByText('el pan')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Listen/ })).not.toBeInTheDocument()
  })
})

describe('with speech support', () => {
  beforeEach(installSpeech)
  afterEach(() => vi.unstubAllGlobals())

  it('dictation plays the sentence, replays it slower, and highlights misheard words', async () => {
    const fetchMock = mockBackend({
      ...ME,
      'GET /vocab/spanish/overview': { body: OVERVIEW },
      'GET /vocab/spanish/session': { body: [pan()] },
      'POST /vocab/check': { body: { is_correct: false, result: 'wrong', expected: 'Compro pan en la panadería.', accepted: [], box: 0 } },
    })
    renderAppAt('/practice/spanish/vocabulary')

    await userEvent.click(await screen.findByRole('radio', { name: 'Listening' }))
    await userEvent.click(screen.getByRole('button', { name: 'Review now' }))
    expect(await screen.findByText('Listen and type what you hear')).toBeInTheDocument()
    expect(spoken).toEqual([{ text: 'Compro pan en la panadería.', lang: 'es-ES', rate: 0.9, voice: 'Mónica' }])
    expect(screen.queryByText('Compro pan en la panadería.')).not.toBeInTheDocument()  // the text stays hidden

    await userEvent.click(screen.getByRole('button', { name: '🐢 Slower' }))
    expect(spoken.at(-1)).toMatchObject({ text: 'Compro pan en la panadería.', rate: 0.65 })

    expect(screen.getByRole('button', { name: 'í' })).toBeInTheDocument()  // accent buttons
    await userEvent.type(screen.getByLabelText('Your answer'), 'Compro pon en la panaderia{Enter}')
    expect(await screen.findByRole('status')).toHaveTextContent('Not quite')
    const said = screen.getByLabelText('What was said')
    expect(said).toHaveTextContent('Compro pan en la panadería.')
    expect(within(said).getByText('pan')).toHaveStyle({ color: '#b91c1c' })
    expect(within(said).getByText('Compro')).not.toHaveStyle({ color: '#b91c1c' })
    expect(screen.getByText('I buy bread at the bakery.')).toBeInTheDocument()
    expect(calls(fetchMock).find(c => c.key === 'POST /vocab/check').body)
      .toMatchObject({ item_id: 7, exercise: 'dictation', answer: 'Compro pon en la panaderia' })
  })

  it('a phrase dictation plays the phrase itself', async () => {
    const phrase = pan({ kind: 'phrase', text: 'Buenas noches', article: null, display: 'Buenas noches', translation: 'good night', pos: null, topic: 'greetings' })
    mockBackend({ ...ME, 'GET /vocab/spanish/overview': { body: OVERVIEW }, 'GET /vocab/spanish/session': { body: [phrase] } })
    renderAppAt('/practice/spanish/vocabulary')
    await userEvent.click(await screen.findByRole('radio', { name: 'Listening' }))
    await userEvent.click(screen.getByRole('button', { name: 'Review now' }))
    await screen.findByText('Listen and type what you hear')
    expect(spoken.map(s => s.text)).toEqual(['Buenas noches'])
  })

  it('flashcards have a speaker button for the word and the example', async () => {
    mockBackend({ ...ME, 'GET /vocab/spanish/overview': { body: OVERVIEW }, 'GET /vocab/spanish/session': { body: [pan({ is_new: true, box: null })] } })
    renderAppAt('/practice/spanish/vocabulary')
    await userEvent.click(await screen.findByRole('button', { name: 'Review now' }))
    await userEvent.click(await screen.findByRole('button', { name: 'Listen: pan' }))
    expect(spoken).toEqual([expect.objectContaining({ text: 'pan', lang: 'es-ES' })])

    await userEvent.click(screen.getByRole('button', { name: 'Show translation' }))
    await userEvent.click(screen.getByRole('button', { name: 'Listen to the example' }))
    expect(spoken.at(-1).text).toBe('Compro pan en la panadería.')
  })

  it('the reading popup can say the word', async () => {
    mockBackend({
      ...ME,
      'GET /history/weak-spots/spanish': { body: { verbs: [], tenses: [], combos: [], due_count: 0 } },
      'POST /exercises/generate': { body: { id: 9, type: 'reading', language: 'spanish', difficulty: 2, content: { passage: 'Tengo un perro.', questions: [] } } },
      'POST /vocab/lookup': { body: { word: 'perro', lemma: 'perro', translation: 'dog', pos: 'noun', source: 'vocabulary', item_id: 5, in_my_words: false } },
    })
    renderAppAt('/practice/spanish')
    await userEvent.click(await screen.findByRole('button', { name: /Reading/ }))
    await userEvent.click(screen.getByRole('button', { name: '1', exact: true }))
    await userEvent.click(screen.getByRole('button', { name: 'Start →' }))
    await userEvent.click(await screen.findByRole('button', { name: 'What does "perro" mean?' }))
    const popup = await screen.findByRole('dialog', { name: 'Meaning of perro' })
    await userEvent.click(await within(popup).findByRole('button', { name: 'Listen: perro' }))
    expect(spoken).toEqual([expect.objectContaining({ text: 'perro', lang: 'es-ES' })])
    expect(screen.getByRole('dialog')).toBeInTheDocument()  // the click doesn't close the popup
  })
})
