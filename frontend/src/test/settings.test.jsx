import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { ALICE, calls, mockBackend, renderAppAt } from './helpers'

describe('settings page', () => {
  it('saves learning preferences', async () => {
    const fetchMock = mockBackend({
      'GET /auth/me': { body: ALICE },
      'PATCH /auth/me': body => ({ body: { ...ALICE, ...body } }),
    })
    renderAppAt('/settings')

    // Only Spanish is offered for now: shown, not chosen
    expect(await screen.findByText("Language I'm learning")).toBeInTheDocument()
    expect(screen.getByText('🇪🇸 Spanish')).toBeInTheDocument()
    expect(screen.queryByRole('combobox', { name: "Language I'm learning" })).not.toBeInTheDocument()
    await userEvent.selectOptions(screen.getByLabelText('Level'), '4')
    const goal = screen.getByLabelText('Daily goal (answers per day)')
    await userEvent.clear(goal)
    await userEvent.type(goal, '30')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))

    expect(await screen.findByText('Saved.')).toBeInTheDocument()
    expect(calls(fetchMock)).toContainEqual({
      key: 'PATCH /auth/me', body: { target_language: 'spanish', level: 4, daily_goal: 30 },
    })
  })

  it('changes the password', async () => {
    const fetchMock = mockBackend({ 'GET /auth/me': { body: ALICE }, 'POST /auth/password': { status: 204 } })
    renderAppAt('/settings')

    await userEvent.type(await screen.findByLabelText('Current password'), 'oldpass')
    await userEvent.type(screen.getByLabelText('New password'), 'newpass')
    await userEvent.type(screen.getByLabelText('Confirm new password'), 'newpass')
    await userEvent.click(screen.getByRole('button', { name: 'Change password' }))

    expect(await screen.findByText(/Password changed/)).toBeInTheDocument()
    expect(calls(fetchMock)).toContainEqual({
      key: 'POST /auth/password', body: { current_password: 'oldpass', new_password: 'newpass' },
    })
    expect(screen.getByLabelText('Current password')).toHaveValue('')
  })

  it('catches mismatched new passwords without calling the server', async () => {
    const fetchMock = mockBackend({ 'GET /auth/me': { body: ALICE } })
    renderAppAt('/settings')

    await userEvent.type(await screen.findByLabelText('Current password'), 'oldpass')
    await userEvent.type(screen.getByLabelText('New password'), 'newpass')
    await userEvent.type(screen.getByLabelText('Confirm new password'), 'other')
    await userEvent.click(screen.getByRole('button', { name: 'Change password' }))

    expect(await screen.findByText("New passwords don't match.")).toBeInTheDocument()
    expect(calls(fetchMock).map(c => c.key)).not.toContain('POST /auth/password')
  })

  it('shows a wrong current password error from the server', async () => {
    mockBackend({
      'GET /auth/me': { body: ALICE },
      'POST /auth/password': { status: 400, body: { detail: 'Current password is incorrect' } },
    })
    renderAppAt('/settings')

    await userEvent.type(await screen.findByLabelText('Current password'), 'wrong')
    await userEvent.type(screen.getByLabelText('New password'), 'newpass')
    await userEvent.type(screen.getByLabelText('Confirm new password'), 'newpass')
    await userEvent.click(screen.getByRole('button', { name: 'Change password' }))

    expect(await screen.findByText('Current password is incorrect')).toBeInTheDocument()
  })
})
