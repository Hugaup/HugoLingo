import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { ALICE, calls, mockBackend, renderAppAt } from './helpers'

const ME = { 'GET /auth/me': { body: { ...ALICE, target_language: 'spanish' } } }
const NOW = new Date()
const inDays = n => new Date(NOW.getTime() + n * 24 * 60 * 60 * 1000).toISOString()
const NO_COUNTS = { needs_work: 0, getting_there: 0, fixed: 0 }

const sheetsOf = (...progress) => progress.map(([answered, correct, title = null], i) => (
  { number: i + 1, title, questions: 12, answered, correct }
))
const topic = (id, title, spanish, category, level, sheets, extra = {}) => ({
  id, title, spanish, category, level, sheets,
  questions: sheets.length * 12,
  answered: sheets.reduce((n, s) => n + s.answered, 0),
  correct: sheets.reduce((n, s) => n + s.correct, 0),
  status: null, due_at: null, is_due: false, ...extra,
})

const OVERVIEW = {
  categories: [{ id: 'articles', title: 'Articles' }, { id: 'verbs', title: 'Verbs' }, { id: 'mixed', title: 'Mixed practice' }],
  topics: [
    topic('articulos-definidos', 'Definite articles', 'Artículos definidos', 'articles', 1, sheetsOf([12, 11], [0, 0])),
    topic('ser-y-estar', 'Ser or estar', 'Ser y estar', 'verbs', 1, sheetsOf([12, 9], [3, 2], [0, 0]),
      { status: 'needs_work', due_at: NOW.toISOString(), is_due: true }),
    topic('por-o-para', 'Por or para', 'Por o para', 'verbs', 3, sheetsOf([0, 0], [0, 0], [0, 0])),
    topic('find-the-mistake', 'Find the mistake', 'Encuentra el error', 'mixed', null, sheetsOf([0, 0, 'A1'], [0, 0, 'A2'])),
  ],
  questions: 132,
  correct: 22,
}

const SER_TOPIC = {
  ...OVERVIEW.topics[1],
  rule: ['ser: identity, origin, profession…', 'estar: location, temporary states…'],
}

const SHEET = {
  topic: 'ser-y-estar', topic_title: 'Ser or estar', number: 1, title: null, sheet_count: 3,
  questions: [
    { id: '1-01', kind: 'choice', text: 'Mis amigos ___ muy simpáticos.', options: ['están', 'son', 'estamos', 'es'] },
    { id: '1-02', kind: 'choice', text: '¿Dónde ___ las llaves?', options: ['son', 'es', 'están', 'está'] },
  ],
}
const REVIEW = { ...SHEET, number: null, title: 'Review' }
const RIGHT = { '1-01': 'son', '1-02': 'están' }
const grade = ({ question_id: id, answer }) => {
  const ok = RIGHT[id] === answer
  const text = SHEET.questions.find(q => q.id === id).text
  return {
    body: {
      result: ok ? 'correct' : 'wrong', is_correct: ok, answer: RIGHT[id], sentence: text.replace('___', RIGHT[id]),
      explanation: id === '1-01' ? 'Character: ser.' : 'Where something is: estar.', fix: null,
      status: ok ? null : 'needs_work', due_at: ok ? null : NOW.toISOString(),
    },
  }
}

describe('grammar page', () => {
  it('shows the score, what to review and every topic by level and category', async () => {
    mockBackend({ ...ME, 'GET /grammar/spanish': { body: OVERVIEW } })
    renderAppAt('/practice/spanish/grammar')

    expect(await screen.findByRole('heading', { name: 'Grammar — Spanish' })).toBeInTheDocument()
    // the heading shows while the overview is still loading: wait for the data
    expect(await screen.findByRole('meter', { name: 'Grammar score' })).toHaveAttribute('aria-valuenow', '17')
    expect(screen.getByText('22 of 132 questions right · 2 of 10 sheets completed')).toBeInTheDocument()

    const review = screen.getByRole('region', { name: 'To review' })
    expect(within(review).getByText('Ser or estar')).toBeInTheDocument()
    expect(within(review).getByRole('button', { name: 'Review Ser or estar' })).toBeInTheDocument()

    const a1 = screen.getByRole('region', { name: 'A1 · Beginner' })
    expect(within(a1).getByRole('heading', { name: 'Articles' })).toBeInTheDocument()
    expect(within(a1).getByRole('button', { name: /Definite articles.*Artículos definidos.*1 of 2 sheets/ })).toBeInTheDocument()
    expect(within(a1).getByRole('button', { name: /Ser or estar.*Needs work.*1 of 3 sheets/ })).toBeInTheDocument()
    expect(within(screen.getByRole('region', { name: 'B1 · Intermediate' })).getByText('Por or para')).toBeInTheDocument()
    expect(within(screen.getByRole('region', { name: 'Mixed practice' })).getByText('Find the mistake')).toBeInTheDocument()
  })

  it('opens a topic, and its review sheet from "To review"', async () => {
    mockBackend({
      ...ME,
      'GET /grammar/spanish': { body: OVERVIEW },
      'GET /grammar/spanish/topics/ser-y-estar': { body: SER_TOPIC },
      'GET /grammar/spanish/topics/ser-y-estar/review': { body: REVIEW },
    })
    renderAppAt('/practice/spanish/grammar')
    await userEvent.click(await screen.findByRole('button', { name: /Ser or estar.*sheets/ }))
    expect(await screen.findByRole('heading', { name: 'Ser or estar', level: 1 })).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: '← Grammar' }))
    await userEvent.click(await screen.findByRole('button', { name: 'Review Ser or estar' }))
    expect(await screen.findByRole('heading', { name: /Ser or estar\s*Review/ })).toBeInTheDocument()
  })

  it('is reached from the Practice page', async () => {
    mockBackend({
      ...ME,
      'GET /history/weak-spots/spanish': { body: { items: [], topics: [], counts: NO_COUNTS, due_count: 0, grammar_due_count: 0, next_check_up_at: null } },
      'GET /grammar/spanish': { body: OVERVIEW },
    })
    renderAppAt('/practice/spanish')
    await userEvent.click(await screen.findByRole('button', { name: /Grammar/ }))
    expect(await screen.findByRole('heading', { name: 'Grammar — Spanish' })).toBeInTheDocument()
  })
})

describe('grammar topic', () => {
  it('shows the rule and each sheet with how far you got', async () => {
    mockBackend({
      ...ME,
      'GET /grammar/spanish/topics/ser-y-estar': { body: SER_TOPIC },
      'GET /grammar/spanish/topics/ser-y-estar/sheets/2': { body: { ...SHEET, number: 2 } },
    })
    renderAppAt('/practice/spanish/grammar/ser-y-estar')

    const rule = await screen.findByRole('region', { name: 'The rule' })
    expect(within(rule).getAllByRole('listitem')).toHaveLength(2)
    expect(screen.getByText('Ser y estar')).toBeInTheDocument()
    expect(screen.getByText('1 of 3 done')).toBeInTheDocument()
    expect(screen.getByText('✓ 9 of 12 right')).toBeInTheDocument()
    expect(screen.getByText('3 of 12 answered')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Do again: exercise 1' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Start: exercise 3' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Review your mistakes →' })).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Continue: exercise 2' }))
    expect(await screen.findByText('Exercise 2')).toBeInTheDocument()
  })
})

describe('grammar sheet', () => {
  it('marks each answer at once, counts them, and ends with the score', async () => {
    const fetchMock = mockBackend({
      ...ME,
      'GET /grammar/spanish/topics/ser-y-estar/sheets/1': { body: SHEET },
      'GET /grammar/spanish/topics/ser-y-estar/sheets/2': { body: { ...SHEET, number: 2 } },
      'POST /grammar/answer': grade,
    })
    renderAppAt('/practice/spanish/grammar/ser-y-estar/1')

    expect(await screen.findByText(/You have answered/)).toHaveTextContent('You have answered 0 of 2 questions')
    const first = screen.getByRole('group', { name: 'Options for question 1' })
    await userEvent.click(within(first).getByRole('button', { name: 'están' }))

    // The wrong choice is marked, the right one shown, the gap filled, the rule given
    expect(await within(first).findByRole('button', { name: '✗ están' })).toBeDisabled()
    expect(within(first).getByRole('button', { name: '✓ son' })).toBeDisabled()
    expect(screen.getByText('Character: ser.')).toBeInTheDocument()
    expect(first.closest('li')).toHaveTextContent('Mis amigos son muy simpáticos.')
    expect(screen.getByText(/You have answered/)).toHaveTextContent('You have answered 1 of 2 questions · 0 right')
    expect(calls(fetchMock)).toContainEqual({
      key: 'POST /grammar/answer',
      body: { language: 'spanish', topic: 'ser-y-estar', question_id: '1-01', answer: 'están' },
    })

    await userEvent.click(within(screen.getByRole('group', { name: 'Options for question 2' })).getByRole('button', { name: 'están' }))
    const results = await screen.findByRole('region', { name: 'Sheet results' })
    expect(within(results).getByText('1 / 2 correct')).toBeInTheDocument()

    await userEvent.click(within(results).getByRole('button', { name: 'Next exercise →' }))
    expect(await screen.findByText('Exercise 2')).toBeInTheDocument()
    expect(screen.getByText(/You have answered/)).toHaveTextContent('You have answered 0 of 2 questions')
  })

  it('restarts with every answer cleared', async () => {
    mockBackend({ ...ME, 'GET /grammar/spanish/topics/ser-y-estar/sheets/1': { body: SHEET }, 'POST /grammar/answer': grade })
    renderAppAt('/practice/spanish/grammar/ser-y-estar/1')
    const first = await screen.findByRole('group', { name: 'Options for question 1' })
    await userEvent.click(within(first).getByRole('button', { name: 'son' }))
    expect(await within(first).findByRole('button', { name: '✓ son' })).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Restart this exercise' }))
    const again = await screen.findByRole('group', { name: 'Options for question 1' })
    expect(within(again).getByRole('button', { name: 'son' })).toBeEnabled()
    expect(screen.getByText(/You have answered/)).toHaveTextContent('You have answered 0 of 2 questions')
  })

  it('says where the topic stands after a review sheet', async () => {
    mockBackend({
      ...ME,
      'GET /grammar/spanish/topics/ser-y-estar/review': { body: { ...REVIEW, questions: SHEET.questions.slice(0, 1) } },
      'POST /grammar/answer': {
        body: { result: 'correct', is_correct: true, answer: 'son', sentence: 'Mis amigos son muy simpáticos.',
          explanation: 'Character: ser.', fix: null, status: 'getting_there', due_at: inDays(1) },
      },
    })
    renderAppAt('/practice/spanish/grammar/ser-y-estar/review')
    await userEvent.click(within(await screen.findByRole('group', { name: 'Options for question 1' })).getByRole('button', { name: 'son' }))
    const results = await screen.findByRole('region', { name: 'Sheet results' })
    expect(results).toHaveTextContent('Getting there')
    expect(results).toHaveTextContent('check-up tomorrow')
    expect(within(results).queryByRole('button', { name: 'Next exercise →' })).not.toBeInTheDocument()
  })

  it('find the mistake: a typed correction, marked up, and accent slips are "almost"', async () => {
    const fetchMock = mockBackend({
      ...ME,
      'GET /grammar/spanish/topics/find-the-mistake/sheets/1': {
        body: {
          topic: 'find-the-mistake', topic_title: 'Find the mistake', number: 1, title: 'A1', sheet_count: 5,
          questions: [
            { id: 'm001', kind: 'correct', text: 'Tengo una libro nuevo.', options: [] },
            { id: 'm002', kind: 'correct', text: 'El esta aqui.', options: [] },
          ],
        },
      },
      'POST /grammar/answer': ({ question_id: id }) => ({
        body: id === 'm001'
          ? { result: 'wrong', is_correct: false, answer: 'Tengo un libro nuevo.', sentence: 'Tengo un libro nuevo.',
            explanation: "The mistake is still there: una → un. 'libro' is masculine.",
            fix: { wrong: 'una', right: 'un', before: 'Tengo ', after: ' libro nuevo.' }, status: 'needs_work', due_at: NOW.toISOString() }
          : { result: 'almost', is_correct: false, answer: 'Él está aquí.', sentence: 'Él está aquí.',
            explanation: 'Almost — just the accents.', fix: null, status: 'needs_work', due_at: NOW.toISOString() },
      }),
    })
    renderAppAt('/practice/spanish/grammar/find-the-mistake/1')

    expect(await screen.findByText(/Each sentence has one mistake/)).toBeInTheDocument()
    await userEvent.type(screen.getByLabelText('Corrected sentence 1'), 'Tengo una libro nuevo.{Enter}')
    const correction = (await screen.findByText('Correction:')).parentElement
    expect(correction).toHaveTextContent('Correction: Tengo una un libro nuevo.')
    expect(within(correction).getByText('una').tagName).toBe('DEL')
    expect(within(correction).getByText('un').tagName).toBe('INS')

    await userEvent.type(screen.getByLabelText('Corrected sentence 2'), 'El esta aqui{Enter}')
    expect(await screen.findByText('Almost — check the accents')).toBeInTheDocument()
    expect(calls(fetchMock)).toContainEqual({
      key: 'POST /grammar/answer',
      body: { language: 'spanish', topic: 'find-the-mistake', question_id: 'm002', answer: 'El esta aqui' },
    })
    expect(within(await screen.findByRole('region', { name: 'Sheet results' })).getByText('0 / 2 correct')).toBeInTheDocument()
  })
})

describe('grammar in Work on this and My mistakes', () => {
  const WEAK = {
    items: [],
    topics: [
      { topic: 'ser-y-estar', title: 'Ser or estar', status: 'needs_work', due_at: NOW.toISOString(), is_due: true, mistakes: 2 },
      { topic: 'gustar', title: 'Gustar and similar verbs', status: 'getting_there', due_at: inDays(1), is_due: false, mistakes: 1 },
    ],
    counts: { needs_work: 1, getting_there: 1, fixed: 0 },
    due_count: 0,
    grammar_due_count: 1,
    next_check_up_at: inDays(1),
  }

  it('Work on this lists grammar topics and opens their review sheet', async () => {
    mockBackend({
      ...ME,
      'GET /history/weak-spots/spanish': { body: WEAK },
      'GET /grammar/spanish/topics/ser-y-estar/review': { body: REVIEW },
    })
    renderAppAt('/practice/spanish')

    const panel = await screen.findByRole('region', { name: 'Work on this' })
    expect(within(panel).getByText('1 due for review')).toBeInTheDocument()
    expect(within(panel).getByText('Ser or estar').closest('li')).toHaveTextContent('2 mistakes')
    expect(within(panel).getByText('Gustar and similar verbs').closest('li')).toHaveTextContent('check-up tomorrow')
    expect(within(panel).queryByRole('button', { name: 'Practise these →' })).not.toBeInTheDocument()
    expect(within(panel).queryByRole('button', { name: 'Review Gustar and similar verbs' })).not.toBeInTheDocument()

    await userEvent.click(within(panel).getByRole('button', { name: 'Review Ser or estar' }))
    expect(await screen.findByRole('heading', { name: /Ser or estar\s*Review/ })).toBeInTheDocument()
  })

  it('My mistakes shows grammar answers in their sentence', async () => {
    mockBackend({
      ...ME,
      'GET /history/mistakes/spanish': {
        body: {
          verbs: [], words: [],
          topics: [{
            topic: 'ser-y-estar', title: 'Ser or estar', status: 'needs_work', due_at: NOW.toISOString(), is_due: true,
            last_seen_at: NOW.toISOString(), total_mistakes: 1,
            mistakes: [{ question: 'Mis amigos ___ muy simpáticos.', user_answer: 'están', expected: 'son', is_almost: false, created_at: '2026-10-04T10:00:00Z' }],
          }],
          counts: { needs_work: 1, getting_there: 0, fixed: 0 },
        },
      },
      'GET /grammar/spanish/topics/ser-y-estar/review': { body: REVIEW },
    })
    renderAppAt('/progress?view=mistakes')

    const grammar = await screen.findByRole('region', { name: 'Grammar' })
    await userEvent.click(within(grammar).getByRole('button', { name: '1 mistake ▾' }))
    const given = within(grammar).getByText('están')
    expect(given.tagName).toBe('DEL')
    expect(given.closest('li')).toHaveTextContent('Mis amigos están son muy simpáticos.')

    await userEvent.click(within(grammar).getByRole('button', { name: 'Practise' }))
    expect(await screen.findByRole('heading', { name: /Ser or estar\s*Review/ })).toBeInTheDocument()
  })

  it('the dashboard shows grammar topics due', async () => {
    mockBackend({
      ...ME,
      'GET /history/stats': { body: { total: 0, correct: 0, accuracy: 0, today_count: 0, streak_days: 0, daily: [] } },
      'GET /history/weak-spots/spanish': { body: WEAK },
      'GET /vocab/spanish/overview': { body: { available: true, groups: [], total: 0, learned: 0, due: 0 } },
      'GET /grammar/spanish': { body: OVERVIEW },
    })
    renderAppAt('/')
    const next = await screen.findByRole('region', { name: 'Continue' })
    await userEvent.click(await within(next).findByRole('button', { name: '1 grammar topic to review' }))
    expect(await screen.findByRole('heading', { name: 'Grammar — Spanish' })).toBeInTheDocument()
  })
})
