import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { ALICE, calls, mockBackend, renderAppAt } from './helpers'

const SPANISH_ALICE = { ...ALICE, target_language: 'spanish' }
const stats = (today, streak = 0) => ({
  'GET /history/stats': { body: { total: 40, correct: 30, accuracy: 75, today_count: today, streak_days: streak, daily: [] } },
})
const DUE = {
  'GET /history/weak-spots/spanish': { body: { items: [], counts: { needs_work: 0, getting_there: 0, fixed: 0 }, due_count: 2, next_check_up_at: null } },
  'GET /vocab/spanish/overview': { body: { available: true, groups: [], total: 300, learned: 10, due: 5 } },
}

describe('home dashboard', () => {
  // Only Spanish is offered for now: nothing to pick, and it's saved as the user's language
  it.each([
    ['first visit', null, 'Welcome, alice'],
    ['a language that is no longer offered', 'french', 'Welcome back, alice'],
  ])('%s: goes straight to the Spanish dashboard and saves Spanish', async (_, current, heading) => {
    const fetchMock = mockBackend({
      'GET /auth/me': { body: { ...ALICE, target_language: current } },
      'PATCH /auth/me': { body: SPANISH_ALICE },
      ...stats(0), ...DUE,
    })
    renderAppAt('/')
    expect(await screen.findByRole('heading', { name: heading })).toBeInTheDocument()
    expect(within(screen.getByRole('region', { name: 'Continue' })).getByText(/Spanish/)).toBeInTheDocument()
    expect(screen.queryByRole('radiogroup', { name: 'Language' })).not.toBeInTheDocument()
    await waitFor(() => expect(calls(fetchMock).find(c => c.key === 'PATCH /auth/me')?.body).toEqual({ target_language: 'spanish' }))
  })

  it("doesn't save anything when Spanish is already set", async () => {
    const fetchMock = mockBackend({ 'GET /auth/me': { body: SPANISH_ALICE }, ...stats(0), ...DUE })
    renderAppAt('/')
    await screen.findByRole('heading', { name: 'Welcome back, alice' })
    expect(calls(fetchMock).some(c => c.key === 'PATCH /auth/me')).toBe(false)
  })

  it('sends practice pages for a language that is not offered back home', async () => {
    mockBackend({ 'GET /auth/me': { body: SPANISH_ALICE }, 'PATCH /auth/me': { body: SPANISH_ALICE }, ...stats(0), ...DUE })
    renderAppAt('/practice/french/conjugation')
    expect(await screen.findByRole('heading', { name: 'Welcome back, alice' })).toBeInTheDocument()
  })

  it("shows today's goal, the streak and what's due", async () => {
    const fetchMock = mockBackend({ 'GET /auth/me': { body: SPANISH_ALICE }, ...stats(7, 3), ...DUE })
    renderAppAt('/')

    const today = await screen.findByRole('region', { name: 'Today' })
    expect(await within(today).findByText(/13 more to reach your daily goal/)).toBeInTheDocument()
    expect(today).toHaveTextContent('7 / 20 answers')
    expect(today).toHaveTextContent('3-day streak')
    expect(within(today).getByRole('progressbar', { name: 'Daily goal' })).toHaveAttribute('aria-valuenow', '7')
    // Today's count and the streak are across all languages
    expect(calls(fetchMock).find(c => c.key.startsWith('GET /history/stats')).key).not.toMatch(/language=/)

    const next = screen.getByRole('region', { name: 'Continue' })
    expect(await within(next).findByRole('button', { name: '5 words to review' })).toBeInTheDocument()
    await userEvent.click(within(next).getByRole('button', { name: '2 verb tenses to review' }))
    expect(await screen.findByRole('heading', { name: 'Review — Spanish' })).toBeInTheDocument()
  })

  it('says when the goal is reached and when nothing is due', async () => {
    mockBackend({
      'GET /auth/me': { body: SPANISH_ALICE }, ...stats(25),
      'GET /history/weak-spots/spanish': { body: { items: [], counts: { needs_work: 0, getting_there: 0, fixed: 0 }, due_count: 0, next_check_up_at: null } },
      'GET /vocab/spanish/overview': { body: { available: true, groups: [], total: 300, learned: 0, due: 0 } },
    })
    renderAppAt('/')
    expect(await screen.findByText('Goal reached — well done!')).toBeInTheDocument()
    expect(screen.getByText('Nothing due — learn something new')).toBeInTheDocument()
  })

  it('continue and the shortcuts open the practice areas', async () => {
    mockBackend({ 'GET /auth/me': { body: SPANISH_ALICE }, ...stats(0), ...DUE })
    renderAppAt('/')
    await userEvent.click(await screen.findByRole('button', { name: 'Continue practising →' }))
    expect(await screen.findByRole('heading', { name: 'Spanish Practice' })).toBeInTheDocument()

    await userEvent.click(screen.getByRole('link', { name: 'HugoLingo' }))
    await userEvent.click(await screen.findByRole('button', { name: /Conversation/ }))
    expect(await screen.findByRole('heading', { name: 'Conversation — Spanish' })).toBeInTheDocument()
  })
})

describe('top bar and settings', () => {
  it('links Practice to your language and marks the current page', async () => {
    mockBackend({ 'GET /auth/me': { body: SPANISH_ALICE }, ...stats(0), ...DUE })
    renderAppAt('/progress')
    const nav = await screen.findByRole('navigation', { name: 'Main' })
    expect(within(nav).getByRole('link', { name: 'Practice' })).toHaveAttribute('href', '/practice/spanish')
    expect(within(nav).getByRole('link', { name: 'Progress' })).toHaveAttribute('aria-current', 'page')
  })

  it('can log out from the settings page (the top bar hides it on phones)', async () => {
    const fetchMock = mockBackend({
      'GET /auth/me': { body: SPANISH_ALICE },
      'POST /auth/logout': { status: 204 },
    })
    renderAppAt('/settings')
    const account = await screen.findByRole('region', { name: 'Account' })
    expect(account).toHaveTextContent('Logged in as alice')
    await userEvent.click(within(account).getByRole('button', { name: 'Log out' }))
    expect(await screen.findByRole('button', { name: 'Log in' })).toBeInTheDocument()
    expect(calls(fetchMock).map(c => c.key)).toContain('POST /auth/logout')
  })
})
