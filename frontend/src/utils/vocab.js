export const TOPIC_LABELS = {
  people: 'People & family',
  home: 'Home',
  food: 'Food & drink',
  time: 'Time',
  places: 'Places & travel',
  work_school: 'Work & school',
  body_health: 'Body & health',
  feelings: 'Feelings',
  nature: 'Nature & weather',
  describing: 'Describing things',
  verbs: 'Everyday verbs',
  // Everyday phrases
  greetings: 'Greetings',
  politeness: 'Politeness',
  basics: 'Basics',
  out_and_about: 'Out and about',
  social: 'Social',
}

export const topicLabel = topic => TOPIC_LABELS[topic] ?? topic

// Topics in the order above (unknown topics last)
const TOPIC_ORDER = Object.keys(TOPIC_LABELS)
export const byTopicOrder = (a, b) =>
  (TOPIC_ORDER.indexOf(a) + 1 || 999) - (TOPIC_ORDER.indexOf(b) + 1 || 999)

// "more slowly, please; slower, please" → "more slowly, please / slower, please"
// (alternatives can contain commas themselves, so they're joined with a slash)
export const allTranslations = item => item.translation.split(';').map(t => t.trim()).join(' / ')

export const MODES = [
  { id: 'mixed', label: 'Mixed' },
  { id: 'flashcards', label: 'Flashcards' },
  { id: 'choice', label: 'Multiple choice' },
  { id: 'typing', label: 'Typing' },
  { id: 'cloze', label: 'Fill the gap' },
]

// The first of the "a; b; c" alternatives, for prompts and options
export const mainTranslation = item => item.translation.split(';')[0].trim()

// Which exercise to show for an item. In "mixed" mode it gets harder as the
// item climbs the review boxes: see it → recognise it → recall it → use it.
export function pickExercise(item, mode, index) {
  const alternate = (a, b) => (index % 2 === 0 ? a : b)
  const gap = item.cloze && item.kind === 'word' ? 'cloze' : 'type_to_target'
  switch (mode) {
    case 'flashcards': return 'flashcard'
    case 'choice': return alternate('choice_to_native', 'choice_to_target')
    case 'typing': return alternate('type_to_target', 'type_to_native')
    case 'cloze': return gap
    default:
      if (item.is_new) return 'flashcard'
      if (item.box <= 1) return alternate('choice_to_native', 'choice_to_target')
      if (item.box === 2) return 'type_to_target'
      return gap
  }
}

// The right answer slotted in among the wrong ones, at a position that's
// stable for the item (no reshuffling on re-render)
export function orderedOptions(item) {
  const options = [...item.options]
  options.splice(item.id % (options.length + 1), 0, item)
  return options
}
