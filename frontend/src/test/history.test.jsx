import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { ALICE, calls, mockBackend, renderAppAt } from './helpers'

const ME = { 'GET /auth/me': { body: ALICE } }
const PRET = { mood: 'Indicativo', tense: 'Indicativo pretérito perfecto simple' }
const PRET_LABEL = 'pretérito perfecto simple (indicativo)'
const NO_WEAK = { verbs: [], tenses: [], combos: [], due_count: 0 }
const WEAK = {
  verbs: [{ verb_infinitive: 'tener', attempts: 4, mistakes: 3, weakness: 0.5, last_mistake_at: null }],
  tenses: [{ ...PRET, attempts: 3, mistakes: 3, weakness: 0.6, last_mistake_at: null }],
  combos: [{ verb_infinitive: 'tener', ...PRET, attempts: 3, mistakes: 3, weakness: 0.6, last_mistake_at: null }],
  due_count: 2,
}

describe('Work on this panel', () => {
  it('lists the weakest verb + tense on the practice page and opens the review drill', async () => {
    mockBackend({
      ...ME,
      'GET /history/weak-spots/spanish': { body: WEAK },
      'GET /history/drill/spanish': { body: [] },
    })
    renderAppAt('/practice/spanish')

    const panel = await screen.findByRole('region', { name: 'Work on this' })
    expect(within(panel).getByText('tener')).toBeInTheDocument()
    expect(within(panel).getByText(PRET_LABEL)).toBeInTheDocument()
    expect(within(panel).getByText('3 mistakes')).toBeInTheDocument()
    expect(within(panel).getByText('2 due for review')).toBeInTheDocument()

    await userEvent.click(within(panel).getByRole('button', { name: 'Practise these →' }))
    expect(await screen.findByRole('heading', { name: 'Review — Spanish' })).toBeInTheDocument()
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
    { verb_infinitive: 'tener', ...PRET, person: '3s', reason: 'due' },
    { verb_infinitive: 'tener', ...PRET, person: '1s', reason: 'weak' },
  ]
  const grade = ({ answer, person }) => {
    const expected = person === '1s' ? 'tuve' : 'tuvo'
    const ok = answer === expected
    return {
      body: {
        is_correct: ok, result: ok ? 'correct' : 'wrong', expected, alternates: [],
        explanation: ok ? null : { summary: 'Rule hint.', mood: PRET.mood, tense: PRET.tense, forms: [] },
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
    expect(await screen.findByText('Nothing to review yet')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Go to conjugation practice' })).toBeInTheDocument()
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
