export const PERSONS = ['1s', '2s', '3s', '1p', '2p', '3p']

export function isFormCorrect(userAnswer, correct, alternates = []) {
  const u = userAnswer.trim().toLowerCase()
  const c = correct.trim().toLowerCase()
  return u === c || alternates.map(a => a.toLowerCase()).includes(u)
}

export const PERSON_LABELS = {
  french:   { '1s': 'je', '2s': 'tu', '3s': 'il/elle', '1p': 'nous', '2p': 'vous', '3p': 'ils/elles' },
  spanish:  { '1s': 'yo', '2s': 'tú', '3s': 'él/ella', '1p': 'nosotros', '2p': 'vosotros', '3p': 'ellos/ellas' },
  english:  { '1s': 'I', '2s': 'you', '3s': 'he/she/it', '1p': 'we', '2p': 'you (pl)', '3p': 'they' },
  norwegian:{ '1s': 'jeg', '2s': 'du', '3s': 'han/hun', '1p': 'vi', '2p': 'dere', '3p': 'de' },
  galician: { '1s': 'eu', '2s': 'ti', '3s': 'el/ela', '1p': 'nós', '2p': 'vós', '3p': 'eles/elas' },
}

const MOOD_ORDER = {
  spanish: ['indicativo', 'condicional', 'subjuntivo', 'imperativo', 'gerundio', 'participo', 'infinitivo'],
  french:  ['indicatif', 'conditionnel', 'subjonctif', 'imperatif', 'participe', 'infinitif'],
  english: ['indicative', 'imperative', 'infinitive'],
}

const TENSE_ORDER_IN_MOOD = {
  spanish: {
    indicativo: [
      'indicativo presente',
      'indicativo pretérito perfecto simple',
      'indicativo pretérito imperfecto',
      'indicativo futuro',
      'indicativo pretérito perfecto compuesto',
      'indicativo pretérito pluscuamperfecto',
      'indicativo pretérito anterior',
      'indicativo futuro perfecto',
    ],
    condicional: ['condicional', 'condicional perfecto'],
    subjuntivo: [
      'subjuntivo presente',
      'subjuntivo pretérito imperfecto (1)',
      'subjuntivo pretérito imperfecto (2)',
      'subjuntivo futuro',
      'subjuntivo pretérito perfecto',
      'subjuntivo pretérito pluscuamperfecto (1)',
      'subjuntivo pretérito pluscuamperfecto (2)',
      'subjuntivo futuro perfecto',
    ],
  },
  french: {
    indicatif: ['présent', 'imparfait', 'passé simple', 'futur'],
    conditionnel: ['présent'],
    subjonctif: ['présent', 'imparfait'],
  },
  english: {
    indicative: [
      'indicative present',
      'indicative present continuous',
      'indicative past tense',
      'indicative present perfect',
    ],
  },
}

function moodIndex(language, mood) {
  const order = MOOD_ORDER[language] || []
  const idx = order.findIndex(m => m === mood.toLowerCase())
  return idx === -1 ? 999 : idx
}

function tenseInMoodIndex(language, mood, tense) {
  const order = TENSE_ORDER_IN_MOOD[language]?.[mood.toLowerCase()] || []
  const idx = order.findIndex(t => t === tense.toLowerCase())
  return idx === -1 ? 999 : idx
}

export function sortTenses(language, tenseList) {
  return [...tenseList].sort((a, b) => {
    const mA = moodIndex(language, a.mood)
    const mB = moodIndex(language, b.mood)
    if (mA !== mB) return mA - mB
    return tenseInMoodIndex(language, a.mood, a.tense) - tenseInMoodIndex(language, b.mood, b.tense)
  })
}

export function sortForms(forms) {
  return [...forms].sort((a, b) => PERSONS.indexOf(a.person) - PERSONS.indexOf(b.person))
}

// Returns sorted array of { mood, tenses: [{ tense, forms }] }
export function sortedTable(language, table) {
  const pairs = []
  for (const [mood, tenses] of Object.entries(table)) {
    for (const [tense, forms] of Object.entries(tenses)) {
      pairs.push({
        mood, tense,
        forms: sortForms(forms),
        mOrd: moodIndex(language, mood),
        tOrd: tenseInMoodIndex(language, mood, tense),
      })
    }
  }
  pairs.sort((a, b) => a.mOrd !== b.mOrd ? a.mOrd - b.mOrd : a.tOrd - b.tOrd)

  const result = []
  for (const { mood, tense, forms } of pairs) {
    const last = result[result.length - 1]
    if (last && last.mood === mood) {
      last.tenses.push({ tense, forms })
    } else {
      result.push({ mood, tenses: [{ tense, forms }] })
    }
  }
  return result
}

// Strip mood prefix from tense name for compact display (Spanish quirk)
export function displayTenseName(mood, tense) {
  const prefix = mood.toLowerCase() + ' '
  if (tense.toLowerCase().startsWith(prefix)) {
    return tense.slice(prefix.length)
  }
  return tense
}
