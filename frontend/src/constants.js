// The languages the app offers. Only Spanish for now: French and English keep
// their data and code (backend, conjugation utils, tense guide…) — add them back
// here to bring them back. With a single language, no page offers a choice.
export const LANGUAGES = [
  { code: 'spanish', label: 'Spanish', flag: '🇪🇸', native: 'Español'  },
]

export const isOffered = code => LANGUAGES.some(l => l.code === code)

// The language a user is learning: their choice if it's still offered, else the
// first one (so anyone who had picked French or English lands on Spanish).
export const learningLanguage = user => (isOffered(user?.target_language) ? user.target_language : LANGUAGES[0].code)

// Same 1–5 scale as the backend's Exercise.difficulty and User.level
export const LEVELS = [
  { value: 1, label: 'A1 — Beginner' },
  { value: 2, label: 'A2 — Elementary' },
  { value: 3, label: 'B1 — Intermediate' },
  { value: 4, label: 'B2 — Upper Intermediate' },
  { value: 5, label: 'C1 — Advanced' },
]
