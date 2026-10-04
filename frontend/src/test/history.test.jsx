import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { ALICE, calls, mockBackend, renderAppAt } from './helpers'

const ME = { 'GET /auth/me': { body: ALICE } }
const PRET = { mood: 'Indicativo', tense: 'Indicativo pretérito perfecto simple' }
const PRET_LABEL = 'pretérito perfecto simple (indicativo)'
const NO_COUNTS = { needs_work: 0, getting_there: 0, fixed: 0 }
const NO_WEAK = { items: [], counts: NO_COUNTS, due_count: 0, next_check_up_at: null }
const NOW = new Date()
const inDays = n => new Date(NOW.getTime() + n * 24 * 60 * 60 * 1000).toISOString()
const WEAK = {
  items: [
    { verb_infinitive: 'tener', ...PRET, status: 'needs_work', due_at: NOW.toISOString(), is_due: true, mistakes: 3, last_mistake_at: null },
    { verb_infinitive: 'hablar', ...PRET, status: 'getting_there', due_at: inDays(1), is_due: false, mistakes: 1, last_mistake_at: null },
  ],
  counts: { needs_work: 1, getting_there: 1, fixed: 2 },
  due_count: 2,
  next_check_up_at: inDays(1),
}

describe('Work on this panel', () => {
  it('lists what needs work, then what is getting there, and opens the review drill', async () => {
    mockBackend({
      ...ME,
      'GET /history/weak-spots/spanish': { body: WEAK },
      'GET /history/drill/spanish': { body: [] },
    })
    renderAppAt('/practice/spanish')

    const panel = await screen.findByRole('region', { name: 'Work on this' })
    expect(within(panel).getByText('tener').closest('li')).toHaveTextContent(PRET_LABEL)
    expect(within(panel).getByText('3 mistakes')).toBeInTheDocument()
    expect(within(panel).getByText('2 due for review')).toBeInTheDocument()
    // Answered right since: shown with its next check-up instead of a mistake count
    const hablar = within(panel).getByText('hablar').closest('li')
    expect(hablar).toHaveTextContent('check-up tomorrow')
    expect(hablar).toHaveTextContent('Getting there')
    expect(within(panel).getByText('2 fixed')).toBeInTheDocument()

    await userEvent.click(within(panel).getByRole('button', { name: 'Practise these →' }))
    expect(await screen.findByRole('heading', { name: 'Review — Spanish' })).toBeInTheDocument()
  })

  it('says when everything is caught up, with the next check-up', async () => {
    mockBackend({
      ...ME,
      'GET /history/weak-spots/spanish': {
        body: { items: [WEAK.items[1]], counts: { needs_work: 0, getting_there: 1, fixed: 0 }, due_count: 0, next_check_up_at: inDays(3) },
      },
    })
    renderAppAt('/practice/spanish')
    const panel = await screen.findByRole('region', { name: 'Work on this' })
    expect(within(panel).getByText('All caught up — next check-up in 3 days.')).toBeInTheDocument()
    expect(within(panel).queryByRole('button', { name: 'Practise these →' })).not.toBeInTheDocument()
  })

  it('once everything is fixed, says so and links to the full history', async () => {
    mockBackend({
      ...ME,
      'GET /history/weak-spots/spanish': { body: { ...NO_WEAK, counts: { ...NO_COUNTS, fixed: 4 } } },
      'GET /history/mistakes/spanish': { body: { verbs: [], words: [], counts: { ...NO_COUNTS, fixed: 4 } } },
    })
    renderAppAt('/practice/spanish')
    const panel = await screen.findByRole('region', { name: 'Work on this' })
    expect(within(panel).getByText('✓ Nothing left to work on.')).toBeInTheDocument()
    expect(within(panel).getByText('4 fixed')).toBeInTheDocument()

    await userEvent.click(within(panel).getByRole('button', { name: 'All your mistakes →' }))
    expect(await screen.findByRole('tab', { name: 'My mistakes' })).toHaveAttribute('aria-selected', 'true')
  })

  it('shows a short hint instead when there is no history yet', async () => {
    mockBackend({ ...ME, 'GET /history/weak-spots/spanish': { body: NO_WEAK } })
    renderAppAt('/practice/spanish')
    expect(await screen.findByText(/Mistakes you make will show up here/)).toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Work on this' })).not.toBeInTheDocument()
  })
})

describe('review drill', () => {
  const PROMPTS = [
    { verb_infinitive: 'tener', ...PRET, person: '3s', reason: 'needs_work' },
    { verb_infinitive: 'tener', ...PRET, person: '1s', reason: 'needs_work' },
  ]
  const grade = ({ answer, person }) => {
    const expected = person === '1s' ? 'tuve' : 'tuvo'
    const ok = answer === expected
    return {
      body: {
        is_correct: ok, result: ok ? 'correct' : 'wrong', expected, alternates: [],
        explanation: ok ? null : { summary: 'Rule hint.', mood: PRET.mood, tense: PRET.tense, forms: [] },
        status: ok ? 'getting_there' : 'needs_work', due_at: ok ? inDays(1) : NOW.toISOString(),
      },
    }
  }

  it('grades each answer on the server and summarises the round, all from the keyboard', async () => {
    const fetchMock = mockBackend({
      ...ME,
      'GET /history/drill/spanish': { body: PROMPTS },
      'POST /history/drill/check': grade,
    })
    renderAppAt('/practice/spanish/review')

    expect(await screen.findByText('1 / 2')).toBeInTheDocument()
    expect(screen.getByText(PRET_LABEL)).toBeInTheDocument()
    await userEvent.type(screen.getByLabelText('él/ella'), 'tenió{Enter}')
    expect(await screen.findByRole('status')).toHaveTextContent('Correct answer: tuvo')

    await userEvent.keyboard('{Enter}')  // focus moved to "Next →"
    expect(await screen.findByText('2 / 2')).toBeInTheDocument()
    await userEvent.type(screen.getByLabelText('yo'), 'tuve{Enter}')
    expect(await screen.findByRole('status')).toHaveTextContent('✓ Correct')

    await userEvent.click(screen.getByRole('button', { name: 'See results' }))
    expect(await screen.findByText('1 / 2 correct')).toBeInTheDocument()
    const mistakes = screen.getByRole('list', { name: 'Mistakes' })
    expect(within(mistakes).getByText('tenió')).toBeInTheDocument()
    expect(within(mistakes).getByText('tuvo')).toBeInTheDocument()
    // The last answer was right: tener is getting there, check-up tomorrow
    const recap = screen.getByRole('region', { name: 'Where you stand' })
    expect(recap).toHaveTextContent('tener · pretérito perfecto simple (indicativo)')
    expect(recap).toHaveTextContent('check-up tomorrow')
    expect(recap).toHaveTextContent('Getting there')

    expect(calls(fetchMock)).toContainEqual({
      key: 'POST /history/drill/check',
      body: { language: 'spanish', verb_infinitive: 'tener', ...PRET, person: '3s', answer: 'tenió' },
    })
  })

  it('"Review again" loads a fresh round', async () => {
    const fetchMock = mockBackend({
      ...ME,
      'GET /history/drill/spanish': { body: PROMPTS.slice(0, 1) },
      'POST /history/drill/check': grade,
    })
    renderAppAt('/practice/spanish/review')

    await userEvent.type(await screen.findByLabelText('él/ella'), 'tuvo{Enter}')
    await userEvent.click(await screen.findByRole('button', { name: 'See results' }))
    await userEvent.click(await screen.findByRole('button', { name: 'Review again' }))

    expect(await screen.findByText('1 / 1')).toBeInTheDocument()
    expect(calls(fetchMock).filter(c => c.key.startsWith('GET /history/drill/'))).toHaveLength(2)
  })

  it('explains when there is nothing to review yet', async () => {
    mockBackend({ ...ME, 'GET /history/drill/spanish': { body: [] } })
    renderAppAt('/practice/spanish/review')
    expect(await screen.findByText('Nothing to review right now')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Go to conjugation practice' })).toBeInTheDocument()
  })

  it('drills one verb + tense when asked for it', async () => {
    const fetchMock = mockBackend({ ...ME, 'GET /history/drill/spanish': { body: PROMPTS.slice(0, 1) } })
    renderAppAt(`/practice/spanish/review?verb=tener&mood=Indicativo&tense=${encodeURIComponent(PRET.tense)}`)
    expect(await screen.findByText('1 / 1')).toBeInTheDocument()
    const [drillCall] = calls(fetchMock).filter(c => c.key.startsWith('GET /history/drill/'))
    const query = new URLSearchParams(drillCall.key.split('?')[1])
    expect([query.get('verb'), query.get('mood'), query.get('tense')]).toEqual(['tener', 'Indicativo', PRET.tense])
    expect(screen.getByRole('button', { name: '← My mistakes' })).toBeInTheDocument()
  })
})

describe('my mistakes', () => {
  const MISTAKES = {
    verbs: [
      {
        verb_infinitive: 'tener', ...PRET, status: 'needs_work', due_at: NOW.toISOString(), is_due: true,
        last_seen_at: NOW.toISOString(), total_mistakes: 7,
        mistakes: [
          { person: '3s', user_answer: 'tenió', expected: 'tuvo', is_almost: false, source: 'drill', created_at: '2026-10-03T10:00:00Z' },
          { person: '1s', user_answer: 'tuvé', expected: 'tuve', is_almost: true, source: 'drill', created_at: '2026-10-02T10:00:00Z' },
        ],
      },
      {
        verb_infinitive: 'ser', mood: 'Indicativo', tense: 'Indicativo presente', status: 'fixed', due_at: inDays(7), is_due: false,
        last_seen_at: NOW.toISOString(), total_mistakes: 1,
        mistakes: [{ person: '1p', user_answer: 'semos', expected: 'somos', is_almost: false, source: 'conversation', created_at: '2026-09-01T10:00:00Z' }],
      },
    ],
    words: [{
      item_id: 5, text: 'el gato', translation: 'cat;tomcat', status: 'getting_there', due_at: inDays(3), is_due: false,
      last_seen_at: NOW.toISOString(), total_mistakes: 1,
      mistakes: [{ user_answer: 'perro', exercise: 'type_to_target', is_almost: false, created_at: '2026-10-03T10:00:00Z' }],
    }],
    counts: { needs_work: 1, getting_there: 1, fixed: 1 },
  }
  const backend = () => mockBackend({
    'GET /auth/me': { body: { ...ALICE, target_language: 'spanish' } },
    'GET /history/mistakes/spanish': { body: MISTAKES },
    'GET /history/drill/spanish': { body: [] },
  })

  it('lists every mistake with its status, filters by status and opens a focused drill', async () => {
    const fetchMock = backend()
    renderAppAt('/progress?view=mistakes')

    const verbs = await screen.findByRole('region', { name: 'Verbs' })
    expect(within(verbs).getByText('tener').closest('li')).toHaveTextContent('Needs work')
    expect(within(verbs).getByText('ser').closest('li')).toHaveTextContent('Fixed')
    const words = screen.getByRole('region', { name: 'Words' })
    expect(within(words).getByText('el gato').closest('li')).toHaveTextContent('check-up in 3 days')
    expect(within(words).getByText('cat')).toBeInTheDocument()

    // The latest wrong answers are behind a toggle
    await userEvent.click(within(verbs).getByRole('button', { name: '7 mistakes ▾' }))
    const answers = within(verbs).getByRole('list', { name: 'Wrong answers' })
    expect(within(answers).getByText('tenió')).toBeInTheDocument()
    expect(within(answers).getByText('accents')).toBeInTheDocument()
    expect(within(answers).getByText('…and 5 earlier')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Fixed (1)' }))
    expect(screen.queryByText('tener')).not.toBeInTheDocument()
    expect(screen.getByText('ser')).toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Words' })).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'All (3)' }))
    const [practiseTener] = within(screen.getByRole('region', { name: 'Verbs' })).getAllByRole('button', { name: 'Practise' })
    await userEvent.click(practiseTener)
    expect(await screen.findByRole('heading', { name: 'Review — Spanish' })).toBeInTheDocument()
    expect(calls(fetchMock).map(c => c.key)).toContainEqual(expect.stringMatching(/^GET \/history\/drill\/spanish\?.*verb=tener/))
  })

  it('has a friendly empty state', async () => {
    mockBackend({
      'GET /auth/me': { body: { ...ALICE, target_language: 'spanish' } },
      'GET /history/mistakes/spanish': { body: { verbs: [], words: [], counts: NO_COUNTS } },
    })
    renderAppAt('/progress?view=mistakes')
    expect(await screen.findByText(/No mistakes yet/)).toBeInTheDocument()
  })
})

describe('progress page', () => {
  const daily = Array.from({ length: 30 }, (_, i) => ({
    date: `2026-09-${String(i + 1).padStart(2, '0')}`, total: i === 29 ? 5 : i === 27 ? 3 : 0, correct: i === 29 ? 4 : 0,
  }))
  const STATS = { total: 10, correct: 7, accuracy: 70, today_count: 5, streak_days: 3, daily }
  const GRID = {
    tenses: [PRET],
    rows: [{ verb_infinitive: 'tener', cells: { [`Indicativo||${PRET.tense}`]: { attempts: 2, correct: 1 } } }],
  }

  it('shows the headline numbers, the activity chart and the verbs × tenses grid', async () => {
    mockBackend({
      ...ME,
      'GET /history/stats': { body: STATS },
      'GET /history/grid/french': { body: GRID },
      'GET /history/weak-spots/french': { body: NO_WEAK },
    })
    renderAppAt('/progress')

    expect(await screen.findByText('70%')).toBeInTheDocument()
    expect(screen.getByText('10')).toBeInTheDocument()
    expect(screen.getByText('3 days')).toBeInTheDocument()
    expect(screen.getByText('5 / 20')).toBeInTheDocument()
    expect(screen.getByRole('meter', { name: 'Daily goal' })).toHaveAttribute('aria-valuenow', '5')
    expect(screen.getByRole('img', { name: /8 in total, at most 5 in one day/ })).toBeInTheDocument()

    const cell = screen.getByText('50%')
    await userEvent.hover(cell)
    expect(screen.getByText(/tener · pretérito perfecto simple \(indicativo\): 1 of 2 correct \(50%\)/)).toBeInTheDocument()
  })

  it('opens on the language chosen in Settings and switches with the tabs', async () => {
    const fetchMock = mockBackend({
      'GET /auth/me': { body: { ...ALICE, target_language: 'spanish' } },
      'GET /history/stats': { body: STATS },
      'GET /history/grid/spanish': { body: GRID },
      'GET /history/grid/english': { body: { tenses: [], rows: [] } },
      'GET /history/weak-spots/spanish': { body: NO_WEAK },
      'GET /history/weak-spots/english': { body: NO_WEAK },
    })
    renderAppAt('/progress')

    expect(await screen.findByRole('tab', { name: /Spanish/ })).toHaveAttribute('aria-selected', 'true')
    await screen.findByText('50%')
    await userEvent.click(screen.getByRole('tab', { name: /English/ }))

    expect(await screen.findByText(/Your accuracy for each verb and tense will appear here/)).toBeInTheDocument()
    const keys = calls(fetchMock).map(c => c.key)
    expect(keys).toContain('GET /history/grid/spanish?verbs=12')
    expect(keys).toContain('GET /history/grid/english?verbs=12')
    expect(keys.find(k => k.startsWith('GET /history/stats'))).toMatch(/language=spanish/)
  })
})

describe('verb table exercise', () => {
  it('reports every graded cell to the history', async () => {
    const FORMS = ['tuve', 'tuviste', 'tuvo', 'tuvimos', 'tuvisteis', 'tuvieron']
    const fetchMock = mockBackend({
      ...ME,
      'GET /verbs/tenses/spanish': { body: [PRET] },
      'GET /verbs/random/spanish': { body: ['tener'] },
      'GET /verbs/table/spanish/tener': {
        body: {
          infinitive: 'tener', language: 'spanish',
          table: { Indicativo: { [PRET.tense]: ['1s', '2s', '3s', '1p', '2p', '3p'].map((p, i) => ({ person: p, form: FORMS[i], alternates: [] })) } },
        },
      },
      'POST /history/attempts': { status: 204 },
    })
    renderAppAt('/practice/spanish/conjugation')

    await userEvent.click(await screen.findByRole('button', { name: 'Test Yourself' }))
    await userEvent.click(screen.getByRole('button', { name: /Verb Table/ }))
    await userEvent.click(await screen.findByRole('button', { name: 'Start exercise →' }))
    const [first] = await screen.findAllByRole('textbox')
    await userEvent.type(first, 'tuve')
    await userEvent.click(screen.getByRole('button', { name: 'Check answers' }))

    const report = calls(fetchMock).find(c => c.key === 'POST /history/attempts')
    expect(report.body.language).toBe('spanish')
    expect(report.body.source).toBe('verb_table')
    expect(report.body.attempts).toHaveLength(6)
    expect(report.body.attempts[0]).toEqual({
      verb_infinitive: 'tener', ...PRET, person: '1s', user_answer: 'tuve', expected: 'tuve', is_correct: true, is_almost: false,
    })
    expect(report.body.attempts[1]).toMatchObject({ person: '2s', user_answer: '', is_correct: false })
  })
})
