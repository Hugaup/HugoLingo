import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { gradeForm } from '../utils/grading'
import { ALICE, calls, mockBackend, renderAppAt } from './helpers'

const ME = { 'GET /auth/me': { body: ALICE } }
const PRET = { mood: 'Indicativo', tense: 'Indicativo pretérito perfecto simple' }
const FORMS = ['tuve', 'tuviste', 'tuvo', 'tuvimos', 'tuvisteis', 'tuvieron']
const PERSONS = ['1s', '2s', '3s', '1p', '2p', '3p']
const EXPLANATION = {
  summary: "tener doesn't follow the regular -er pattern here (that would give “tenió”). Its stem in this tense is tuv-.",
  ...PRET,
  forms: PERSONS.map((person, i) => ({ person, form: FORMS[i] })),
}

describe('gradeForm (browser copy of the server grader)', () => {
  it.each([
    ['tuvo', 'tuvo', [], 'correct'],
    ['  TUVO ', 'tuvo', [], 'correct'],
    ['tuvó', 'tuvo', [], 'almost'],
    ['hable', 'hablé', [], 'almost'],
    ['nino', 'niño', [], 'almost'],
    ['tuviese', 'tuviera', ['tuviese'], 'correct'],
    ['tuve', 'tuvo', [], 'wrong'],
    ['', 'tuvo', [], 'wrong'],
  ])('%s vs %s → %s', (answer, correct, alternates, expected) => {
    expect(gradeForm(answer, correct, alternates)).toBe(expected)
  })
})

describe('review drill feedback', () => {
  const PROMPTS = [
    { verb_infinitive: 'tener', ...PRET, person: '1s', reason: 'due' },
    { verb_infinitive: 'tener', ...PRET, person: '3s', reason: 'weak' },
  ]
  const grade = ({ answer, person }) => {
    if (person === '1s') {
      return { body: { is_correct: false, result: 'almost', expected: 'tuve', alternates: [],
        explanation: { ...EXPLANATION, summary: 'Almost — just the accents: it\'s “tuve”.' } } }
    }
    return { body: { is_correct: false, result: 'wrong', expected: 'tuvo', alternates: [], explanation: EXPLANATION, answer } }
  }

  it('shows "almost" kindly, explains real mistakes in one line, and keeps the forms behind a toggle', async () => {
    mockBackend({ ...ME, 'GET /history/drill/spanish': { body: PROMPTS }, 'POST /history/drill/check': grade })
    renderAppAt('/practice/spanish/review')

    await userEvent.type(await screen.findByLabelText('yo'), 'tuvé{Enter}')
    expect(await screen.findByRole('status')).toHaveTextContent('≈ Almost — check the accents: tuve')
    expect(screen.queryByText(/regular -er pattern/)).not.toBeInTheDocument()

    await userEvent.keyboard('{Enter}')
    await userEvent.type(await screen.findByLabelText('él/ella'), 'tenió{Enter}')
    expect(await screen.findByRole('status')).toHaveTextContent('✗ Correct answer: tuvo')
    expect(screen.getByText(EXPLANATION.summary)).toBeInTheDocument()

    // Compact by default: the full tense only appears on request
    expect(screen.queryByRole('definition')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Show all forms ▾' }))
    const forms = screen.getByLabelText('All forms in this tense')
    expect(within(forms).getAllByRole('definition').map(d => d.textContent)).toEqual(FORMS)
    await userEvent.click(screen.getByRole('button', { name: 'Hide forms ▴' }))
    expect(screen.queryByLabelText('All forms in this tense')).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'See results' }))
    const summary = await screen.findByRole('region', { name: 'Session summary' })
    expect(within(summary).getByText('0 / 2 correct')).toBeInTheDocument()
    expect(within(summary).getByText(/1 answer was only an accent away — still counted as a mistake/)).toBeInTheDocument()
    expect(within(summary).getByText('accents')).toBeInTheDocument()
    // Already in the drill: offer another round, not a link to itself
    expect(within(summary).queryByRole('button', { name: 'Review these now →' })).not.toBeInTheDocument()
    expect(within(summary).getByRole('button', { name: 'Review again' })).toBeInTheDocument()
  })
})

describe('verb table feedback', () => {
  it('marks accent slips as almost, reports them, and links to the review drill', async () => {
    const fetchMock = mockBackend({
      ...ME,
      'GET /verbs/tenses/spanish': { body: [PRET] },
      'GET /verbs/random/spanish': { body: ['tener'] },
      'GET /verbs/table/spanish/tener': {
        body: { infinitive: 'tener', language: 'spanish', table: { Indicativo: { [PRET.tense]: PERSONS.map((p, i) => ({ person: p, form: FORMS[i], alternates: [] })) } } },
      },
      'POST /history/attempts': { status: 204 },
      'GET /history/drill/spanish': { body: [] },
    })
    renderAppAt('/practice/spanish/conjugation')

    await userEvent.click(await screen.findByRole('button', { name: 'Test Yourself' }))
    await userEvent.click(screen.getByRole('button', { name: /Verb Table/ }))
    await userEvent.click(await screen.findByRole('button', { name: 'Start exercise →' }))
    const [yo, tu] = await screen.findAllByRole('textbox')
    await userEvent.type(yo, 'tuvé')
    await userEvent.type(tu, 'tuviste')
    await userEvent.click(screen.getByRole('button', { name: 'Check answers' }))

    expect(screen.getByText('1/6 correct')).toBeInTheDocument()
    expect(screen.getByText(/1 only an accent away \(counted as mistakes\)/)).toBeInTheDocument()
    expect(screen.getByLabelText('almost')).toBeInTheDocument()

    const report = calls(fetchMock).find(c => c.key === 'POST /history/attempts').body.attempts
    expect(report[0]).toMatchObject({ person: '1s', is_correct: false, is_almost: true })
    expect(report[1]).toMatchObject({ person: '2s', is_correct: true, is_almost: false })
    expect(report[2]).toMatchObject({ person: '3s', is_correct: false, is_almost: false })

    await userEvent.click(screen.getByRole('button', { name: 'Review mistakes →' }))
    expect(await screen.findByRole('heading', { name: 'Review — Spanish' })).toBeInTheDocument()
  })
})

describe('sentence completion feedback', () => {
  const ITEM = {
    sentence: 'Ayer yo ___ mucho trabajo.', subject_hint: 'yo', verb_infinitive: 'tener',
    ...PRET, person: '1s', correct_form: 'tuve', alternates: [],
  }

  it('gives a one-line hint, asks the AI only on request, and ends with a summary', async () => {
    const fetchMock = mockBackend({
      ...ME,
      'GET /verbs/tenses/spanish': { body: [PRET] },
      'POST /conjugation-exercises/sentence/generate': { body: [ITEM] },
      'POST /conjugation-exercises/sentence/check': {
        body: { form_correct: false, form_result: 'wrong', tense_correct: true, hint: EXPLANATION },
      },
      'POST /chat/stream': { stream: ['A long ', 'AI explanation…'] },
    })
    renderAppAt('/practice/spanish/conjugation')

    await userEvent.click(await screen.findByRole('button', { name: 'Test Yourself' }))
    await userEvent.click(screen.getByRole('button', { name: /Sentence Completion/ }))
    await userEvent.click(await screen.findByRole('button', { name: 'Start →' }))

    await userEvent.type(await screen.findByPlaceholderText('Type the conjugated verb…'), 'tenié')
    await waitFor(() => expect(screen.getAllByRole('option').length).toBeGreaterThan(1))
    await userEvent.selectOptions(screen.getByRole('combobox'), `${PRET.mood}||${PRET.tense}`)
    await userEvent.click(screen.getByRole('button', { name: 'Check' }))

    expect(await screen.findByRole('status')).toHaveTextContent('✗ Form incorrect — correct: tuve')
    expect(screen.getByText(EXPLANATION.summary)).toBeInTheDocument()
    // Checking never waits on the LLM: nothing is asked until the toggle opens
    expect(calls(fetchMock).map(c => c.key)).not.toContain('POST /chat/stream')
    await userEvent.click(screen.getByRole('button', { name: 'AI explanation & questions ▾' }))
    expect(await screen.findByText('A long AI explanation…')).toBeInTheDocument()
    const asked = calls(fetchMock).find(c => c.key === 'POST /chat/stream').body.messages
    expect(asked.at(-1).content).toMatch(/explain why "tuve" is correct.*what was wrong with my answer/)
    expect(screen.queryByText(/explain why "tuve" is correct/)).not.toBeInTheDocument()  // the question stays hidden

    await userEvent.click(screen.getByRole('button', { name: 'See results' }))
    const summary = await screen.findByRole('region', { name: 'Session summary' })
    expect(within(summary).getByText('0 / 1 correct')).toBeInTheDocument()
    expect(within(summary).getByText('tenié')).toBeInTheDocument()
    expect(within(summary).getByRole('button', { name: 'Review these now →' })).toBeInTheDocument()
    expect(within(summary).getByRole('button', { name: 'New exercise' })).toBeInTheDocument()
  })
})

describe('classic exercise flow feedback', () => {
  it('shows "almost" for accent slips and a summary after the last exercise', async () => {
    mockBackend({
      ...ME,
      'GET /history/weak-spots/spanish': { body: { verbs: [], tenses: [], combos: [], due_count: 0 } },
      'POST /exercises/generate': {
        body: { id: 7, type: 'grammar', language: 'spanish', difficulty: 2,
          content: { sentence_with_error: 'El esta aqui.', corrected_sentence: 'Él está aquí.', explanation: 'Accents.' } },
      },
      'POST /exercises/check': {
        body: { is_correct: false, almost: true, explanation: 'Almost — just the accents. Accents.', correct_answer: 'Él está aquí.' },
      },
    })
    renderAppAt('/practice/spanish')

    await userEvent.click(await screen.findByRole('button', { name: /Grammar/ }))
    await userEvent.click(screen.getByRole('button', { name: '1', exact: true }))
    await userEvent.click(screen.getByRole('button', { name: 'Start →' }))

    await userEvent.type(await screen.findByPlaceholderText('Type the corrected sentence...'), 'El esta aqui.{Enter}')
    expect(await screen.findByText('Almost — check the accents')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Finish' }))
    const summary = await screen.findByRole('region', { name: 'Session summary' })
    expect(within(summary).getByText('0 / 1 correct')).toBeInTheDocument()
    expect(within(summary).getByText('accents')).toBeInTheDocument()
    expect(within(summary).queryByRole('button', { name: 'Review these now →' })).not.toBeInTheDocument()
  })
})

describe('accent buttons', () => {
  it('insert into the AI chat box too (a textarea)', async () => {
    mockBackend({ ...ME, 'GET /verbs/tenses/spanish': { body: [PRET] } })
    renderAppAt('/practice/spanish/conjugation')

    const chat = await screen.findByPlaceholderText(/Ask about spanish tenses/)
    chat.focus()
    const picker = chat.closest('div').parentElement
    fireEvent.mouseDown(within(picker).getByRole('button', { name: 'ñ' }))
    await waitFor(() => expect(chat).toHaveValue('ñ'))
  })
})
