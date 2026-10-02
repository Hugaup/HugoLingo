import { render } from '@testing-library/react'
import { vi } from 'vitest'
import App from '../App'

export const ALICE = {
  id: 1, username: 'alice', native_language: 'english',
  target_language: null, level: 2, daily_goal: 20,
}

function response(status, body) {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: String(status),
    json: async () => body,
  }
}

/**
 * Replace global fetch with a fake backend.
 * routes: { 'METHOD /path': {status, body} | (requestBody) => {status, body} }
 * Paths are given without the /api prefix; a key without a query string also
 * matches that path with any query. Unmocked routes return 404.
 */
export function mockBackend(routes) {
  const fetchMock = vi.fn(async (url, opts = {}) => {
    const key = `${opts.method ?? 'GET'} ${url.replace(/^\/api/, '')}`
    const route = routes[key] ?? routes[key.split('?')[0]]
    if (!route) return response(404, { detail: `No mock for ${key}` })
    const reqBody = opts.body ? JSON.parse(opts.body) : undefined
    const { status = 200, body = null } = typeof route === 'function' ? route(reqBody) : route
    return response(status, body)
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

/** Requests the app made, as [{key, body}] */
export function calls(fetchMock) {
  return fetchMock.mock.calls.map(([url, opts = {}]) => ({
    key: `${opts.method ?? 'GET'} ${url.replace(/^\/api/, '')}`,
    body: opts.body ? JSON.parse(opts.body) : undefined,
  }))
}

export function renderAppAt(path) {
  window.history.pushState({}, '', path)
  return render(<App />)
}
