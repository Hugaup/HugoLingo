import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { orderedOptions, pickExercise } from '../utils/vocab'
import { ALICE, calls, mockBackend, renderAppAt } from './helpers'

const ME = { 'GET /auth/me': { body: ALICE } }

const OVERVIEW = {
  available: true,
  groups: [
    { kind: 'phrase', topic: 'greetings', total: 14, seen: 2, learned: 1, due: 0 },
    { kind: 'phrase', topic: 'politeness', total: 8, seen: 0, learned: 0, due: 0 },
    { kind: 'word', topic: 'food', total: 25, seen: 3, learned: 2, due: 1 },
    { kind: 'word', topic: 'home', total: 20, seen: 0, learned: 0, due: 0 },
  ],
  total: 67, learned: 3, due: 1,
}

let nextId = 1
function word(text, translation, extra = {}) {
  return {
    id: nextId++, kind: 'word', text, article: 'el', display: `el ${text}`, translation, pos: 'noun',
    topic: 'food', level: 1, example: `Me gusta el ${text}.`, example_translation: `I like the ${translation.split(';')[0]}.`,
    box: null, is_new: true, cloze: 'Me gusta el ___.', options: [], ...extra,
  }
}
const withOptions = (item, ...others) => ({ ...item, options: others })

describe('choosing exercises', () => {
  it('mixed mode gets harder as an item climbs the review boxes', () => {
    const item = word('pan', 'bread')
    expect(pickExercise({ ...item, is_new: true }, 'mixed', 0)).toBe('flashcard')
    expect(pickExercise({ ...item, is_new: false, box: 0 }, 'mixed', 0)).toBe('choice_to_native')
    expect(pickExercise({ ...item, is_new: false, box: 1 }, 'mixed', 1)).toBe('choice_to_target')
    expect(pickExercise({ ...item, is_new: false, box: 2 }, 'mixed', 0)).toBe('type_to_target')
    expect(pickExercise({ ...item, is_new: false, box: 4 }, 'mixed', 0)).toBe('cloze')
    expect(pickExercise({ ...item, is_new: false, box: 4, kind: 'phrase' }, 'mixed', 0)).toBe('type_to_target')
  })

  it('a fixed mode always uses its exercise', () => {
    const item = word('pan', 'bread', { is_new: false, box: 1 })
    expect(pickExercise(item, 'flashcards', 3)).toBe('flashcard')
    expect([0, 1].map(i => pickExercise(item, 'typing', i))).toEqual(['type_to_target', 'type_to_native'])
    expect(pickExercise({ ...item, cloze: null }, 'cloze', 0)).toBe('type_to_target')
  })

  it('places the right answer among the options in a stable spot', () => {
    const item = withOptions(word('pan', 'bread'), word('queso', 'cheese'), word('vino', 'wine'), word('arroz', 'rice'))
    const order = orderedOptions(item)
    expect(order).toHaveLength(4)
    expect(order).toContain(item)
    expect(orderedOptions(item)).toEqual(order)
  })
})

describe('vocabulary page', () => {
  it('is reachable from the practice page and shows phrases and topics with progress', async () => {
    mockBackend({
      ...ME,
      'GET /history/weak-spots/spanish': { body: { verbs: [], tenses: [], combos: [], due_count: 0 } },
      'GET /vocab/spanish/overview': { body: OVERVIEW },
    })
    renderAppAt('/practice/spanish')

    await userEvent.click(await screen.findByRole('button', { name: /Vocabulary/ }))
    expect(await screen.findByRole('heading', { name: 'Vocabulary — Spanish' })).toBeInTheDocument()

    const phrases = screen.getByRole('region', { name: 'Everyday phrases' })
    expect(within(phrases).getByText('1 / 22 learned')).toBeInTheDocument()
    const food = screen.getByRole('region', { name: 'Food & drink' })
    expect(within(food).getByText('2 / 25 learned')).toBeInTheDocument()
    expect(within(food).getByText('1 due')).toBeInTheDocument()
    expect(screen.getByText(/item is due for review/)).toBeInTheDocument()
    // Topics in a fixed, sensible order (home before food), not the server's order
    const topics = screen.getAllByRole('region').map(r => r.getAttribute('aria-label'))
    expect(topics.indexOf('Home')).toBeLessThan(topics.indexOf('Food & drink'))
  })

  it('says so when a language has no vocabulary yet', async () => {
    mockBackend({ ...ME, 'GET /vocab/english/overview': { body: { available: false, groups: [], total: 0, learned: 0, due: 0 } } })
    renderAppAt('/practice/english/vocabulary')
    expect(await screen.findByText("Vocabulary isn't available for English yet.")).toBeInTheDocument()
  })

  it('flashcards: reveal, self-grade, and a summary at the end', async () => {
    const pan = word('pan', 'bread')
    const queso = word('queso', 'cheese')
    const fetchMock = mockBackend({
      ...ME,
      'GET /vocab/spanish/overview': { body: OVERVIEW },
      'GET /vocab/spanish/session': { body: [pan, queso] },
      'POST /vocab/check': ({ knew }) => ({ body: { is_correct: knew, result: knew ? 'correct' : 'wrong', expected: 'x', accepted: [], box: knew ? 1 : 0 } }),
    })
    renderAppAt('/practice/spanish/vocabulary')

    await userEvent.click(within(await screen.findByRole('region', { name: 'Food & drink' })).getByRole('button', { name: 'Practise' }))
    expect(await screen.findByText('el pan')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Show translation' }))
    expect(screen.getByText('bread')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'I knew it' }))

    expect(await screen.findByText('el queso')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Show translation' }))
    await userEvent.click(screen.getByRole('button', { name: "I didn't know" }))

    const summary = await screen.findByRole('region', { name: 'Session summary' })
    expect(within(summary).getByText('1 / 2 correct')).toBeInTheDocument()
    expect(within(summary).getByText('el queso — cheese')).toBeInTheDocument()
    const session = calls(fetchMock).find(c => c.key.startsWith('GET /vocab/spanish/session'))
    expect(session.key).toMatch(/kind=word/)
    expect(session.key).toMatch(/topic=food/)
    expect(calls(fetchMock).filter(c => c.key === 'POST /vocab/check').map(c => c.body)).toEqual([
      { item_id: pan.id, exercise: 'flashcard', answer: '', knew: true },
      { item_id: queso.id, exercise: 'flashcard', answer: '', knew: false },
    ])
  })

  it('multiple choice: picking an option shows right and wrong', async () => {
    const pan = withOptions(word('pan', 'bread', { is_new: false, box: 0 }), word('queso', 'cheese'), word('vino', 'wine'), word('arroz', 'rice'))
    const fetchMock = mockBackend({
      ...ME,
      'GET /vocab/spanish/overview': { body: OVERVIEW },
      'GET /vocab/spanish/session': { body: [pan] },
      'POST /vocab/check': ({ answer }) => ({ body: { is_correct: answer === 'bread', result: answer === 'bread' ? 'correct' : 'wrong', expected: 'bread', accepted: ['bread'], box: 0 } }),
    })
    renderAppAt('/practice/spanish/vocabulary')

    await userEvent.click(await screen.findByRole('radio', { name: 'Multiple choice' }))
    await userEvent.click(screen.getByRole('button', { name: 'Review now' }))
    expect(await screen.findByText('What does it mean?')).toBeInTheDocument()
    await userEvent.click(within(screen.getByRole('group', { name: 'Options' })).getByRole('button', { name: 'wine' }))

    expect(await screen.findByRole('status')).toHaveTextContent('✗ bread')
    expect(screen.getByText('Me gusta el pan.')).toBeInTheDocument()  // the example is shown after answering
    expect(calls(fetchMock).find(c => c.key === 'POST /vocab/check').body).toMatchObject({ exercise: 'choice_to_native', answer: 'wine' })
  })

  it('typing: accent slips are "almost", with accent buttons for the target language', async () => {
    const item = word('habitación', 'room; bedroom', { is_new: false, box: 2, article: 'la', display: 'la habitación', topic: 'home' })
    mockBackend({
      ...ME,
      'GET /vocab/spanish/overview': { body: OVERVIEW },
      'GET /vocab/spanish/session': { body: [item] },
      'POST /vocab/check': { body: { is_correct: false, result: 'almost', expected: 'habitación', accepted: ['habitación'], box: 0 } },
    })
    renderAppAt('/practice/spanish/vocabulary')

    await userEvent.click(within(await screen.findByRole('region', { name: 'Home' })).getByRole('button', { name: 'Practise' }))
    expect(await screen.findByText('room / bedroom')).toBeInTheDocument()  // mixed mode, box 2 → type the word
    expect(screen.getByRole('button', { name: 'ó' })).toBeInTheDocument()
    await userEvent.type(screen.getByLabelText('Your answer'), 'habitacion{Enter}')
    expect(await screen.findByRole('status')).toHaveTextContent('≈ Almost — check the accents: la habitación')
  })

  it('fill the gap shows the sentence with a gap and its translation', async () => {
    const item = word('pan', 'bread', { is_new: false, box: 4 })
    mockBackend({
      ...ME,
      'GET /vocab/spanish/overview': { body: OVERVIEW },
      'GET /vocab/spanish/session': { body: [item] },
    })
    renderAppAt('/practice/spanish/vocabulary')

    await userEvent.click(await screen.findByRole('radio', { name: 'Fill the gap' }))
    await userEvent.click(within(screen.getByRole('region', { name: 'Food & drink' })).getByRole('button', { name: 'Practise' }))
    expect(await screen.findByText('Me gusta el ___.')).toBeInTheDocument()
    expect(screen.getByText('I like the bread.')).toBeInTheDocument()
  })

  it('lists all everyday phrases grouped by situation', async () => {
    const phrase = (text, translation, topic) => ({ ...word(text, translation), kind: 'phrase', article: null, display: text, pos: null, topic, box: null })
    mockBackend({
      ...ME,
      'GET /vocab/spanish/overview': { body: OVERVIEW },
      'GET /vocab/spanish/items': { body: [phrase('hola', 'hello; hi', 'greetings'), phrase('gracias', 'thank you; thanks', 'politeness')] },
    })
    renderAppAt('/practice/spanish/vocabulary')

    await userEvent.click(within(await screen.findByRole('region', { name: 'Everyday phrases' })).getByRole('button', { name: 'See all' }))
    expect(await screen.findByRole('heading', { name: 'Everyday phrases' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Greetings' })).toBeInTheDocument()
    expect(screen.getByText('thank you / thanks')).toBeInTheDocument()
  })

  it('shows words learned on the progress page', async () => {
    mockBackend({
      'GET /auth/me': { body: { ...ALICE, target_language: 'spanish' } },
      'GET /history/stats': { body: { total: 0, correct: 0, accuracy: 0, today_count: 0, streak_days: 0, daily: [{ date: '2026-10-01', total: 0, correct: 0 }] } },
      'GET /history/grid/spanish': { body: { tenses: [], rows: [] } },
      'GET /history/weak-spots/spanish': { body: { verbs: [], tenses: [], combos: [], due_count: 0 } },
      'GET /vocab/spanish/overview': { body: OVERVIEW },
    })
    renderAppAt('/progress')
    expect(await screen.findByText('Words learned')).toBeInTheDocument()
    expect(screen.getByText('3 / 67')).toBeInTheDocument()
  })
})
