import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { ALICE, calls, mockBackend, renderAppAt } from './helpers'

const ME = { 'GET /auth/me': { body: ALICE } }
const NO_WEAK = { 'GET /history/weak-spots/spanish': { body: { items: [], counts: { needs_work: 0, getting_there: 0, fixed: 0 }, due_count: 0, next_check_up_at: null } } }
const PASSAGE = 'Ayer tuve un día muy largo. Después corrí al parque con mi perro.'
const READING = {
  'POST /exercises/generate': {
    body: { id: 9, type: 'reading', language: 'spanish', difficulty: 2,
      content: { passage: PASSAGE, questions: [{ question: '¿Adónde fue?', correct_answer: 'al parque' }] } },
  },
}

async function openReading() {
  renderAppAt('/practice/spanish')
  await userEvent.click(await screen.findByRole('button', { name: /Reading/ }))
  await userEvent.click(screen.getByRole('button', { name: '1', exact: true }))
  await userEvent.click(screen.getByRole('button', { name: 'Start →' }))
  await screen.findByText(/click any word/)
}

describe('reading: click a word to learn it', () => {
  it('looks the word up with its sentence and saves it to my words', async () => {
    const fetchMock = mockBackend({
      ...ME, ...NO_WEAK, ...READING,
      'POST /vocab/lookup': { body: { word: 'tuve', lemma: 'tener', translation: 'to have', pos: 'verb', source: 'vocabulary', item_id: 3, in_my_words: false } },
      'POST /vocab/my-words': { body: { item_id: 3, added: true } },
    })
    await openReading()

    await userEvent.click(screen.getByRole('button', { name: 'What does "tuve" mean?' }))
    const popup = await screen.findByRole('dialog', { name: 'Meaning of tuve' })
    expect(await within(popup).findByText('tener')).toBeInTheDocument()
    expect(within(popup).getByText('to have')).toBeInTheDocument()
    expect(within(popup).getByText('From the vocabulary list')).toBeInTheDocument()

    await userEvent.click(within(popup).getByRole('button', { name: '+ Add to my words' }))
    expect(await within(popup).findByText('✓ In my words')).toBeInTheDocument()

    expect(calls(fetchMock).find(c => c.key === 'POST /vocab/lookup').body).toEqual({
      language: 'spanish', word: 'tuve', context: 'Ayer tuve un día muy largo.',
    })
    expect(calls(fetchMock).find(c => c.key === 'POST /vocab/my-words').body).toEqual({
      language: 'spanish', lemma: 'tener', translation: 'to have', pos: 'verb', example: 'Ayer tuve un día muy largo.',
    })
  })

  it('marks AI translations, and says when a word is already saved', async () => {
    const fetchMock = mockBackend({
      ...ME, ...NO_WEAK, ...READING,
      'POST /vocab/lookup': { body: { word: 'corrí', lemma: 'correr', translation: 'to run', pos: 'verb', source: 'ai', item_id: null, in_my_words: true } },
    })
    await openReading()

    await userEvent.click(screen.getByRole('button', { name: 'What does "corrí" mean?' }))
    const popup = await screen.findByRole('dialog', { name: 'Meaning of corrí' })
    expect(await within(popup).findByText('AI translation — may be imperfect')).toBeInTheDocument()
    expect(within(popup).getByText('✓ In my words')).toBeInTheDocument()
    expect(calls(fetchMock).find(c => c.key === 'POST /vocab/lookup').body.context)
      .toBe('Después corrí al parque con mi perro.')
  })

  it('closes with Escape or by clicking the word again', async () => {
    mockBackend({
      ...ME, ...NO_WEAK, ...READING,
      'POST /vocab/lookup': { body: { word: 'perro', lemma: 'perro', translation: 'dog', pos: 'noun', source: 'vocabulary', item_id: 5, in_my_words: false } },
    })
    await openReading()
    const perro = screen.getByRole('button', { name: 'What does "perro" mean?' })

    await userEvent.click(perro)
    await screen.findByRole('dialog', { name: 'Meaning of perro' })
    await userEvent.keyboard('{Escape}')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()

    await userEvent.click(perro)
    await screen.findByRole('dialog', { name: 'Meaning of perro' })
    await userEvent.click(perro)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('shows an error when the lookup fails', async () => {
    mockBackend({
      ...ME, ...NO_WEAK, ...READING,
      'POST /vocab/lookup': { status: 502, body: { detail: "Couldn't look that word up right now — is Ollama running?" } },
    })
    await openReading()
    await userEvent.click(screen.getByRole('button', { name: 'What does "largo" mean?' }))
    expect(await screen.findByText(/Couldn't look that word up/)).toBeInTheDocument()
  })
})

describe('my words on the vocabulary page', () => {
  const OVERVIEW = {
    available: true,
    groups: [
      { kind: 'phrase', topic: 'greetings', total: 14, seen: 0, learned: 0, due: 0 },
      { kind: 'personal', topic: 'my_words', total: 2, seen: 2, learned: 0, due: 2 },
    ],
    total: 16, learned: 0, due: 2,
  }
  const mine = (id, text, translation) => ({
    id, kind: 'personal', text, article: null, display: text, translation, pos: 'verb', topic: 'my_words',
    level: 1, example: `Hoy voy a ${text}.`, example_translation: '', box: 0,
  })

  it('shows a My words card and lets a word be removed', async () => {
    const fetchMock = mockBackend({
      ...ME,
      'GET /vocab/spanish/overview': { body: OVERVIEW },
      'GET /vocab/spanish/items': { body: [mine(41, 'correr', 'to run'), mine(42, 'saltar', 'to jump')] },
      'DELETE /vocab/my-words/41': { status: 204 },
    })
    renderAppAt('/practice/spanish/vocabulary')

    const card = await screen.findByRole('region', { name: 'My words' })
    expect(within(card).getByText('Words you saved while reading')).toBeInTheDocument()
    await userEvent.click(within(card).getByRole('button', { name: 'See all' }))

    expect(await screen.findByRole('heading', { name: 'My words' })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Remove correr' }))
    expect(screen.queryByText('correr')).not.toBeInTheDocument()
    expect(screen.getByText('saltar')).toBeInTheDocument()
    expect(calls(fetchMock).map(c => c.key)).toContain('DELETE /vocab/my-words/41')
    expect(calls(fetchMock).find(c => c.key.startsWith('GET /vocab/spanish/items')).key).toMatch(/kind=personal/)
  })
})
