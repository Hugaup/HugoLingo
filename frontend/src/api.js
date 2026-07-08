const BASE = '/api'

async function request(method, path, body) {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'Request failed')
  }
  return res.json()
}

export const api = {
  generateExercise: (type, language, difficulty) =>
    request('POST', '/exercises/generate', { type, language, difficulty }),

  checkAnswer: (exerciseId, userAnswer, userId = 1) =>
    request('POST', '/exercises/check', {
      exercise_id: exerciseId,
      user_answer: userAnswer,
      user_id: userId,
    }),

  getProgress: (userId = 1) => request('GET', `/progress/${userId}`),

  createUser: (username, nativeLanguage = 'english') =>
    request('POST', '/users', { username, native_language: nativeLanguage }),

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
