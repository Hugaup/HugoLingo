const BASE = '/api'

export class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.status = status
  }
}

// Called when any request comes back 401 (session missing/expired), so the
// auth layer can drop the user and send them to the login page.
let onUnauthorized = null
export function setUnauthorizedHandler(fn) {
  onUnauthorized = fn
}

// FastAPI sends a string for HTTPException and a list of {loc, msg} for validation errors
function errorMessage(detail, fallback) {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return detail.map(d => d.msg).join('. ')
  return fallback
}

async function request(method, path, body) {
  // Session cookie is httpOnly and same-origin (via the /api proxy), so fetch sends it automatically
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    // A 401 from /auth/login just means wrong credentials, not an expired session
    if (res.status === 401 && path !== '/auth/login') onUnauthorized?.()
    throw new ApiError(errorMessage(err.detail, 'Request failed'), res.status)
  }
  if (res.status === 204) return null
  return res.json()
}

export const api = {
  // Auth
  signup: (username, password) => request('POST', '/auth/signup', { username, password }),
  login: (username, password) => request('POST', '/auth/login', { username, password }),
  logout: () => request('POST', '/auth/logout'),
  me: () => request('GET', '/auth/me'),
  updateSettings: (settings) => request('PATCH', '/auth/me', settings),
  changePassword: (currentPassword, newPassword) =>
    request('POST', '/auth/password', { current_password: currentPassword, new_password: newPassword }),

  generateExercise: (type, language, difficulty) =>
    request('POST', '/exercises/generate', { type, language, difficulty }),

  checkAnswer: (exerciseId, userAnswer) =>
    request('POST', '/exercises/check', {
      exercise_id: exerciseId,
      user_answer: userAnswer,
    }),

  getProgress: () => request('GET', '/progress'),

  // Verbs
  searchVerbs: (language, q, limit = 20) =>
    request('GET', `/verbs/search/${language}?q=${encodeURIComponent(q)}&limit=${limit}`),

  getVerbTenses: (language) =>
    request('GET', `/verbs/tenses/${language}`),

  getVerbEndings: (language) =>
    request('GET', `/verbs/endings/${language}`),

  getRandomVerbs: (language, count = 3, mode = 'random', endings = null) => {
    let url = `/verbs/random/${language}?count=${count}&mode=${mode}`
    if (endings) url += `&endings=${encodeURIComponent(endings)}`
    return request('GET', url)
  },

  getVerbTable: (language, infinitive, moods = null) => {
    let url = `/verbs/table/${language}/${encodeURIComponent(infinitive)}`
    if (moods) url += `?moods=${encodeURIComponent(moods)}`
    return request('GET', url)
  },

  // Chat
  chat: (messages) =>
    request('POST', '/chat', { messages }),

  // Conjugation exercises
  generateSentences: (language, tenses, count) =>
    request('POST', '/conjugation-exercises/sentence/generate', { language, tenses, count }),

  checkSentence: (item, userForm, userMood, userTense, language) =>
    request('POST', '/conjugation-exercises/sentence/check', {
      item, user_form: userForm, user_mood: userMood, user_tense: userTense, language,
    }),
}
