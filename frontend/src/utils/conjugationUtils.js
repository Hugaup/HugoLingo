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
      'indicativo pretérito imperfecto',
      'indicativo pretérito perfecto simple',
      'indicativo futuro',
      'indicativo pretérito perfecto compuesto',
      'indicativo pretérito pluscuamperfecto',
      'indicativo pretérito anterior',
      'indicativo futuro perfecto',
    ],
    condicional: ['condicional', 'condicional perfecto'],
    subjuntivo: [
      'subjuntivo presente',
      'subjuntivo pretérito imperfecto',
      'subjuntivo futuro',
      'subjuntivo pretérito perfecto',
      'subjuntivo pretérito pluscuamperfecto',
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

// Which moods belong under which table section header, in section display order.
// A mood not listed here (Spanish: gerundio/infinitivo/participio — forms with a
// single spelling, not conjugated per person) falls into a trailing "Other" section.
const SECTION_MOODS = {
  spanish: [
    ['Indicativo', ['indicativo', 'condicional']],
    ['Subjuntivo', ['subjuntivo']],
    ['Imperativo', ['imperativo']],
  ],
  french: [
    ['Indicatif', ['indicatif']],
    ['Conditionnel', ['conditionnel']],
    ['Subjonctif', ['subjonctif']],
    ['Imperatif', ['imperatif']],
  ],
  english: [
    ['Indicative', ['indicative']],
    ['Imperative', ['imperative']],
  ],
}

// Explicit combined ordering for sections that merge multiple moods, to mirror a
// specific reference layout (Spanish: condicional interleaved into Indicativo,
// matching scholingua's conjugation trainer) instead of the generic per-mood sort.
const SECTION_ORDER_OVERRIDE = {
  spanish: {
    Indicativo: [
      'indicativo||indicativo presente',
      'indicativo||indicativo pretérito imperfecto',
      'indicativo||indicativo pretérito perfecto simple',
      'indicativo||indicativo futuro',
      'condicional||condicional',
      'indicativo||indicativo pretérito perfecto compuesto',
      'indicativo||indicativo pretérito pluscuamperfecto',
      'indicativo||indicativo pretérito anterior',
      'indicativo||indicativo futuro perfecto',
      'condicional||condicional perfecto',
    ],
  },
}

// Cosmetic per-tense display-name overrides for cases where the raw DB tense
// name reads awkwardly (Spanish imperativo's tense field literally repeats the
// mood name instead of naming the two moods afirmativo/negativo).
const TENSE_LABEL_OVERRIDES = {
  spanish: {
    'imperativo||imperativo': 'afirmativo',
    'imperativo||imperativo non': 'negativo',
    // These moods' tense field just repeats the mood name (no " descriptive name"
    // suffix for displayTenseName to strip), so state the label explicitly instead.
    'condicional||condicional': 'condicional',
    'condicional||condicional perfecto': 'condicional perfecto',
    'gerundio||gerundio': 'gerundio',
    'infinitivo||infinitivo': 'infinitivo',
    'participo||participo': 'participio', // DB mood is spelled "Participo"; correct Spanish is "participio"
  },
}

export function tenseLabel(language, mood, tense) {
  const override = TENSE_LABEL_OVERRIDES[language]?.[`${mood.toLowerCase()}||${tense.toLowerCase()}`]
  return override || displayTenseName(mood, tense)
}

// Returns [{ section, tenses: [{ mood, tense }] }, ...] grouped into the
// language's grammatical sections, with non-personal-form moods trailing in "Other".
export function groupTensesBySection(language, tenseList) {
  const sectionDefs = SECTION_MOODS[language] || []
  const sorted = sortTenses(language, tenseList)

  const buckets = sectionDefs.map(([title]) => ({ section: title, tenses: [] }))
  const other = { section: 'Other', tenses: [] }
  for (const t of sorted) {
    const idx = sectionDefs.findIndex(([, moods]) => moods.includes(t.mood.toLowerCase()))
    ;(idx === -1 ? other : buckets[idx]).tenses.push(t)
  }

  const overrides = SECTION_ORDER_OVERRIDE[language] || {}
  for (const bucket of buckets) {
    const order = overrides[bucket.section]
    if (!order) continue
    bucket.tenses.sort((a, b) => {
      const ia = order.indexOf(`${a.mood.toLowerCase()}||${a.tense.toLowerCase()}`)
      const ib = order.indexOf(`${b.mood.toLowerCase()}||${b.tense.toLowerCase()}`)
      return (ia === -1 ? 999 : ia) - (ib === -1 ? 999 : ib)
    })
  }

  return other.tenses.length ? [...buckets, other] : buckets
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
