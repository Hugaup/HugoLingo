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

function send(method, path, body) {
  // Session cookie is httpOnly and same-origin (via the /api proxy), so fetch sends it automatically
  return fetch(`${BASE}${path}`, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
  })
}

async function throwIfFailed(res, path) {
  if (res.ok) return
  const err = await res.json().catch(() => ({ detail: res.statusText }))
  // A 401 from /auth/login just means wrong credentials, not an expired session
  if (res.status === 401 && path !== '/auth/login') onUnauthorized?.()
  throw new ApiError(errorMessage(err.detail, 'Request failed'), res.status)
}

async function request(method, path, body) {
  const res = await send(method, path, body)
  await throwIfFailed(res, path)
  if (res.status === 204) return null
  return res.json()
}

// Plain-text streaming response: onText(textSoFar) is called as each piece arrives
async function streamText(path, body, onText) {
  const res = await send('POST', path, body)
  await throwIfFailed(res, path)
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let text = ''
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    text += decoder.decode(value, { stream: true })
    onText(text)
  }
  return text
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

  // History / weak spots
  recordAttempts: (language, source, attempts) =>
    request('POST', '/history/attempts', { language, source, attempts }),

  getWeakSpots: (language, limit = 8) => request('GET', `/history/weak-spots/${language}?limit=${limit}`),

  getDrill: (language, count = 10) => request('GET', `/history/drill/${language}?count=${count}`),

  checkDrill: (language, prompt, answer) =>
    request('POST', '/history/drill/check', {
      language,
      verb_infinitive: prompt.verb_infinitive,
      mood: prompt.mood,
      tense: prompt.tense,
      person: prompt.person,
      answer,
    }),

  getStats: (language, days = 30) => {
    const tz = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
    const params = new URLSearchParams({ tz, days: String(days) })
    if (language) params.set('language', language)
    return request('GET', `/history/stats?${params}`)
  },

  getGrid: (language, verbs = 12) => request('GET', `/history/grid/${language}?verbs=${verbs}`),

  // Vocabulary
  getVocabOverview: (language) => request('GET', `/vocab/${language}/overview`),

  getVocabSession: (language, { kind, topic, count = 10 } = {}) => {
    const params = new URLSearchParams({ count: String(count) })
    if (kind) params.set('kind', kind)
    if (topic) params.set('topic', topic)
    return request('GET', `/vocab/${language}/session?${params}`)
  },

  getVocabItems: (language, { kind, topic } = {}) => {
    const params = new URLSearchParams()
    if (kind) params.set('kind', kind)
    if (topic) params.set('topic', topic)
    return request('GET', `/vocab/${language}/items?${params}`)
  },

  lookupWord: (language, word, context = '') =>
    request('POST', '/vocab/lookup', { language, word, context }),

  addMyWord: (language, { lemma, translation, pos = null, example = '' }) =>
    request('POST', '/vocab/my-words', { language, lemma, translation, pos, example }),

  removeMyWord: (itemId) => request('DELETE', `/vocab/my-words/${itemId}`),

  checkVocab: (itemId, exercise, { answer = '', knew } = {}) =>
    request('POST', '/vocab/check', { item_id: itemId, exercise, answer, ...(knew === undefined ? {} : { knew }) }),

  // Chat
  chat: (messages) =>
    request('POST', '/chat', { messages }),

  chatStream: (messages, onText) => streamText('/chat/stream', { messages }, onText),

  // Conversation practice
  getScenarios: () => request('GET', '/conversation/scenarios'),

  // The AI's next line (its opener when messages is empty), streamed
  conversationReply: (language, scenario, messages, onText) =>
    streamText('/conversation/reply', { language, scenario, messages }, onText),

  checkMessage: (language, scenario, previous, message) =>
    request('POST', '/conversation/check', { language, scenario, previous, message }),

  // Conjugation exercises
  generateSentences: (language, tenses, count) =>
    request('POST', '/conjugation-exercises/sentence/generate', { language, tenses, count }),

  checkSentence: (item, userForm, userMood, userTense, language) =>
    request('POST', '/conjugation-exercises/sentence/check', {
      item, user_form: userForm, user_mood: userMood, user_tense: userTense, language,
    }),
}
