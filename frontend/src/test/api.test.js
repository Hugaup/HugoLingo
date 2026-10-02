import { afterEach, describe, expect, it, vi } from 'vitest'
import { api, ApiError, setUnauthorizedHandler } from '../api'
import { mockBackend } from './helpers'

afterEach(() => setUnauthorizedHandler(null))

describe('api request handling', () => {
  it('returns null for 204 No Content', async () => {
    mockBackend({ 'POST /auth/logout': { status: 204 } })
    await expect(api.logout()).resolves.toBeNull()
  })

  it('turns FastAPI validation errors into a readable message', async () => {
    mockBackend({
      'POST /auth/signup': {
        status: 422,
        body: { detail: [{ loc: ['body', 'username'], msg: 'String should have at least 3 characters' }] },
      },
    })
    const err = await api.signup('ab', 'pass').catch(e => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err.status).toBe(422)
    expect(err.message).toBe('String should have at least 3 characters')
  })

  it('notifies the auth layer when a session has expired', async () => {
    const handler = vi.fn()
    setUnauthorizedHandler(handler)
    mockBackend({ 'GET /progress': { status: 401, body: { detail: 'Not logged in' } } })
    await expect(api.getProgress()).rejects.toThrow('Not logged in')
    expect(handler).toHaveBeenCalledOnce()
  })

  it('does not treat a failed login as an expired session', async () => {
    const handler = vi.fn()
    setUnauthorizedHandler(handler)
    mockBackend({ 'POST /auth/login': { status: 401, body: { detail: 'Wrong username or password' } } })
    await expect(api.login('alice', 'nope')).rejects.toThrow('Wrong username or password')
    expect(handler).not.toHaveBeenCalled()
  })

  it('no longer sends a client-chosen user_id when checking answers', async () => {
    const fetchMock = mockBackend({ 'POST /exercises/check': { body: {} } })
    await api.checkAnswer(7, 'hola')
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ exercise_id: 7, user_answer: 'hola' })
  })
})
