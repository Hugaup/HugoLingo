import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { markChanges } from '../utils/conversation'
import { ALICE, calls, mockBackend, renderAppAt } from './helpers'

const ME = { 'GET /auth/me': { body: ALICE } }
const NO_WEAK = { 'GET /history/weak-spots/spanish': { body: { verbs: [], tenses: [], combos: [], due_count: 0 } } }
const SCENARIOS = {
  'GET /conversation/scenarios': {
    body: [
      { id: 'cafe', title: 'At the café', description: 'Order something to drink and eat.', goal: 'Order a drink and something to eat, then ask for the bill.' },
      { id: 'hotel', title: 'Hotel check-in', description: 'Arrive at your hotel.', goal: 'Check in.' },
    ],
  },
}
// The AI opens with a question; later replies are the same short line
const REPLY = {
  'POST /conversation/reply': ({ messages }) => ({
    stream: messages.length === 0 ? ['¡Hola! ', '¿Qué quieres ', 'tomar?'] : ['Muy bien. ', '¿Algo más?'],
  }),
}
const CORRECT = { result: 'correct', corrected: null, explanation: null, verb_mistakes: [] }
const VERB_MISTAKE = {
  result: 'wrong', corrected: 'Yo quiero un bocadillo.',
  explanation: '“querer” is the infinitivo — this one needs the presente (indicativo): “quiero”.',
  verb_mistakes: [{ verb: 'querer', wrong: 'querer', right: 'quiero' }],
}
const CHECK = { 'POST /conversation/check': ({ message }) => ({ body: message.includes('querer') ? VERB_MISTAKE : CORRECT }) }

async function openCafe() {
  renderAppAt('/practice/spanish/conversation')
  await userEvent.click(await screen.findByRole('button', { name: /At the café/ }))
  await screen.findByRole('button', { name: 'What does "tomar" mean?' })  // the opener has finished
}

// Send a message and wait until the AI's nth reply has finished (its words become clickable)
async function say(text, nthReply) {
  await userEvent.type(screen.getByLabelText('Your message'), `${text}{Enter}`)
  await waitFor(() => expect(screen.getAllByRole('button', { name: 'What does "más" mean?' })).toHaveLength(nthReply))
}

describe('helpers', () => {
  it('markChanges marks the words the learner did not write', () => {
    expect(markChanges('Yo querer un bocadillo.', 'Yo quiero un bocadillo.')).toEqual([
      { word: 'Yo', changed: false }, { word: 'quiero', changed: true },
      { word: 'un', changed: false }, { word: 'bocadillo.', changed: false },
    ])
    // punctuation and capitals don't count; a repeated word is only "kept" as often as it was written
    expect(markChanges('oui ça va', 'Oui, ça va.').every(w => !w.changed)).toBe(true)
    expect(markChanges('la casa', 'la casa la').map(w => w.changed)).toEqual([false, false, true])
  })
})

describe('conversation practice', () => {
  it('is reachable from the practice page and the AI opens the scenario', async () => {
    const fetchMock = mockBackend({ ...ME, ...NO_WEAK, ...SCENARIOS, ...REPLY })
    renderAppAt('/practice/spanish')
    await userEvent.click(await screen.findByRole('button', { name: /Conversation/ }))
    expect(await screen.findByRole('heading', { name: 'Conversation — Spanish' })).toBeInTheDocument()
    await userEvent.click(await screen.findByRole('button', { name: /At the café/ }))

    expect(screen.getByText('Order a drink and something to eat, then ask for the bill.')).toBeInTheDocument()
    expect(await screen.findByRole('button', { name: 'What does "tomar" mean?' })).toBeInTheDocument()
    expect(calls(fetchMock).find(c => c.key === 'POST /conversation/reply').body)
      .toEqual({ language: 'spanish', scenario: 'cafe', messages: [] })
    expect(screen.getByRole('button', { name: 'Finish' })).toBeDisabled()  // nothing said yet
  })

  it('checks each message: a tick when right, the fixed sentence and why when wrong', async () => {
    const fetchMock = mockBackend({ ...ME, ...SCENARIOS, ...REPLY, ...CHECK })
    await openCafe()
    expect(screen.getByRole('button', { name: 'ñ' })).toBeInTheDocument()  // accent buttons

    await say('Un café con leche, por favor.', 1)
    const log = screen.getByRole('log', { name: 'Conversation' })
    expect(await within(log).findByLabelText('Correct')).toBeInTheDocument()

    await say('Yo querer un bocadillo.', 2)
    const correction = await within(log).findByLabelText('Correction')
    expect(within(correction).getByText('quiero')).toHaveStyle({ fontWeight: '700' })
    expect(correction).toHaveTextContent('this one needs the presente')

    const checks = calls(fetchMock).filter(c => c.key === 'POST /conversation/check').map(c => c.body)
    expect(checks).toEqual([
      { language: 'spanish', scenario: 'cafe', previous: '¡Hola! ¿Qué quieres tomar?', message: 'Un café con leche, por favor.' },
      { language: 'spanish', scenario: 'cafe', previous: 'Muy bien. ¿Algo más?', message: 'Yo querer un bocadillo.' },
    ])
    const lastReply = calls(fetchMock).filter(c => c.key === 'POST /conversation/reply').at(-1).body
    expect(lastReply.messages).toEqual([
      { role: 'assistant', content: '¡Hola! ¿Qué quieres tomar?' },
      { role: 'user', content: 'Un café con leche, por favor.' },
      { role: 'assistant', content: 'Muy bien. ¿Algo más?' },
      { role: 'user', content: 'Yo querer un bocadillo.' },
    ])
  })

  it('finishing shows a summary of the corrections, with review for verb mistakes', async () => {
    mockBackend({ ...ME, ...NO_WEAK, ...SCENARIOS, ...REPLY, ...CHECK })
    await openCafe()
    await say('Un café con leche, por favor.', 1)
    await say('Yo querer un bocadillo.', 2)
    await screen.findByLabelText('Correction')

    await userEvent.click(screen.getByRole('button', { name: 'Finish' }))
    const summary = screen.getByRole('region', { name: 'Session summary' })
    expect(summary).toHaveTextContent('1 / 2 correct')
    expect(within(summary).getByText('Yo querer un bocadillo.')).toBeInTheDocument()
    expect(within(summary).getByText('Yo quiero un bocadillo.')).toBeInTheDocument()
    expect(within(summary).getByRole('button', { name: 'Review these now →' })).toBeInTheDocument()

    await userEvent.click(within(summary).getByRole('button', { name: 'New conversation' }))
    expect(await screen.findByRole('button', { name: 'What does "tomar" mean?' })).toBeInTheDocument()
    expect(screen.queryByLabelText('Correction')).not.toBeInTheDocument()
  })

  it('keeps going when a message cannot be checked', async () => {
    mockBackend({
      ...ME, ...SCENARIOS, ...REPLY,
      'POST /conversation/check': { status: 502, body: { detail: "Couldn't check that message right now — is Ollama running?" } },
    })
    await openCafe()
    await say('Un café, por favor.', 1)
    expect(await screen.findByText("Couldn't check this one")).toBeInTheDocument()
    expect(screen.getByLabelText('Your message')).toBeEnabled()
  })

  it('translates an AI line on request and lets its words be looked up', async () => {
    const fetchMock = mockBackend({
      ...ME, ...SCENARIOS, ...REPLY,
      'POST /chat': { body: { content: 'Hello! What would you like to drink?' } },
      'POST /vocab/lookup': { body: { word: 'tomar', lemma: 'tomar', translation: 'to take; to drink', pos: 'verb', source: 'vocabulary', item_id: 3, in_my_words: false } },
    })
    await openCafe()
    await userEvent.click(screen.getByRole('button', { name: 'Translate' }))
    expect(await screen.findByText('Hello! What would you like to drink?')).toBeInTheDocument()
    expect(calls(fetchMock).find(c => c.key === 'POST /chat').body.messages[1])
      .toEqual({ role: 'user', content: '¡Hola! ¿Qué quieres tomar?' })
    await userEvent.click(screen.getByRole('button', { name: 'Hide translation' }))
    expect(screen.queryByText('Hello! What would you like to drink?')).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'What does "tomar" mean?' }))
    expect(await screen.findByRole('dialog', { name: 'Meaning of tomar' })).toHaveTextContent('to take / to drink')
  })
})
