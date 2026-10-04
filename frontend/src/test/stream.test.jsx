import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { api } from '../api'
import { ALICE, calls, mockBackend, renderAppAt } from './helpers'

const ME = { 'GET /auth/me': { body: ALICE } }

describe('streamed AI replies', () => {
  it('api.chatStream reports the text so far as each piece arrives', async () => {
    mockBackend({ 'POST /chat/stream': { stream: ['Ho', 'la', ' mundo'] } })
    const seen = []
    const full = await api.chatStream([{ role: 'user', content: 'hi' }], t => seen.push(t))
    expect(seen).toEqual(['Ho', 'Hola', 'Hola mundo'])
    expect(full).toBe('Hola mundo')
  })

  it('the chat panel shows the streamed reply and sends the system prompt', async () => {
    const fetchMock = mockBackend({
      ...ME,
      'GET /verbs/tenses/spanish': { body: [] },
      'POST /chat/stream': { stream: ['El pretérito ', 'describe acciones ', 'terminadas.'] },
    })
    renderAppAt('/practice/spanish/conjugation')

    await userEvent.type(await screen.findByPlaceholderText(/Ask about spanish tenses/), '¿Qué es el pretérito?')
    await userEvent.click(screen.getByRole('button', { name: 'Send' }))

    expect(await screen.findByText('El pretérito describe acciones terminadas.')).toBeInTheDocument()
    const sent = calls(fetchMock).find(c => c.key === 'POST /chat/stream').body.messages
    expect(sent[0].role).toBe('system')
    expect(sent.at(-1)).toEqual({ role: 'user', content: '¿Qué es el pretérito?' })
  })

  it('opening the conjugation page does not scroll down to the chat panel', async () => {
    mockBackend({ ...ME, 'GET /verbs/tenses/spanish': { body: [] } })
    const scrollIntoView = vi.spyOn(Element.prototype, 'scrollIntoView')
    renderAppAt('/practice/spanish/conjugation')

    await screen.findByPlaceholderText(/Ask about spanish tenses/)
    expect(scrollIntoView).not.toHaveBeenCalled()
    scrollIntoView.mockRestore()
  })

  it('shows an error in the chat when the AI request fails', async () => {
    mockBackend({
      ...ME,
      'GET /verbs/tenses/spanish': { body: [] },
      'POST /chat/stream': { status: 502, body: { detail: 'LLM unavailable' } },
    })
    renderAppAt('/practice/spanish/conjugation')

    await userEvent.type(await screen.findByPlaceholderText(/Ask about spanish tenses/), 'hola')
    await userEvent.click(screen.getByRole('button', { name: 'Send' }))
    expect(await screen.findByText('Error: LLM unavailable')).toBeInTheDocument()
  })
})
