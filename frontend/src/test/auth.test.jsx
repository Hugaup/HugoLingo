import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { ALICE, calls, mockBackend, renderAppAt } from './helpers'

const LOGGED_OUT = { 'GET /auth/me': { status: 401, body: { detail: 'Not logged in' } } }

describe('login flow', () => {
  it('sends logged-out visitors to the login page', async () => {
    mockBackend(LOGGED_OUT)
    renderAppAt('/')
    expect(await screen.findByRole('heading', { name: 'Log in' })).toBeInTheDocument()
  })

  it('logs in and returns to the page the user was trying to open', async () => {
    const fetchMock = mockBackend({ ...LOGGED_OUT, 'POST /auth/login': { body: ALICE } })
    renderAppAt('/settings')

    await userEvent.type(await screen.findByLabelText('Username'), 'alice')
    await userEvent.type(screen.getByLabelText('Password'), 'pass1234')
    await userEvent.click(screen.getByRole('button', { name: 'Log in' }))

    expect(await screen.findByRole('heading', { name: 'Settings' })).toBeInTheDocument()
    expect(within(screen.getByRole('banner')).getByText('alice')).toBeInTheDocument()
    expect(calls(fetchMock)).toContainEqual({
      key: 'POST /auth/login', body: { username: 'alice', password: 'pass1234' },
    })
  })

  it('shows the server error on wrong credentials and stays on the login page', async () => {
    mockBackend({
      ...LOGGED_OUT,
      'POST /auth/login': { status: 401, body: { detail: 'Wrong username or password' } },
    })
    renderAppAt('/login')

    await userEvent.type(await screen.findByLabelText('Username'), 'alice')
    await userEvent.type(screen.getByLabelText('Password'), 'wrong')
    await userEvent.click(screen.getByRole('button', { name: 'Log in' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Wrong username or password')
    expect(screen.getByRole('heading', { name: 'Log in' })).toBeInTheDocument()
  })

  it('logged-in users see the app and can log out', async () => {
    const fetchMock = mockBackend({ 'GET /auth/me': { body: ALICE }, 'POST /auth/logout': { status: 204 } })
    renderAppAt('/')

    expect(await screen.findByRole('heading', { name: 'Welcome, alice' })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Log out' }))

    expect(await screen.findByRole('heading', { name: 'Log in' })).toBeInTheDocument()
    expect(calls(fetchMock).map(c => c.key)).toContain('POST /auth/logout')
  })

  it('an expired session in the middle of using the app sends the user to log in', async () => {
    mockBackend({
      'GET /auth/me': { body: ALICE },
      'PATCH /auth/me': { status: 401, body: { detail: 'Session expired, please log in again' } },
    })
    renderAppAt('/settings')

    await userEvent.click(await screen.findByRole('button', { name: 'Save' }))
    expect(await screen.findByRole('heading', { name: 'Log in' })).toBeInTheDocument()
  })
})

describe('sign-up flow', () => {
  async function fillSignup(username, password, confirm) {
    await userEvent.type(await screen.findByLabelText('Username'), username)
    await userEvent.type(screen.getByLabelText('Password'), password)
    await userEvent.type(screen.getByLabelText('Confirm password'), confirm)
    await userEvent.click(screen.getByRole('button', { name: 'Create account' }))
  }

  it('is reachable from the login page', async () => {
    mockBackend(LOGGED_OUT)
    renderAppAt('/login')
    await userEvent.click(await screen.findByRole('link', { name: 'Create one' }))
    expect(screen.getByRole('heading', { name: 'Create an account' })).toBeInTheDocument()
  })

  it('creates the account and lands on the welcome page', async () => {
    const fetchMock = mockBackend({
      ...LOGGED_OUT,
      'POST /auth/signup': ({ username }) => ({ status: 201, body: { ...ALICE, username } }),
    })
    renderAppAt('/signup')
    await fillSignup('newbie', 'abcd', 'abcd')

    expect(await screen.findByRole('heading', { name: 'Welcome, newbie' })).toBeInTheDocument()
    expect(calls(fetchMock)).toContainEqual({
      key: 'POST /auth/signup', body: { username: 'newbie', password: 'abcd' },
    })
  })

  it.each([
    ['newbie', 'abcd', 'abce', "Passwords don't match."],
    ['newbie', 'abc', 'abc', 'Password must be at least 4 characters.'],
    ['a b', 'abcd', 'abcd', 'Username must be 3–32 characters'],
  ])('rejects %s / %s / %s before calling the server', async (username, password, confirm, message) => {
    const fetchMock = mockBackend(LOGGED_OUT)
    renderAppAt('/signup')
    await fillSignup(username, password, confirm)

    expect(await screen.findByRole('alert')).toHaveTextContent(message)
    expect(calls(fetchMock).map(c => c.key)).not.toContain('POST /auth/signup')
  })

  it('shows when a username is already taken', async () => {
    mockBackend({
      ...LOGGED_OUT,
      'POST /auth/signup': { status: 409, body: { detail: 'That username is already taken' } },
    })
    renderAppAt('/signup')
    await fillSignup('alice', 'abcd', 'abcd')
    expect(await screen.findByRole('alert')).toHaveTextContent('That username is already taken')
  })
})
