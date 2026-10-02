// Browser copy of backend/app/services/grading.py, for the verb table (graded
// client-side). "almost" = differs only by accents; it still counts as a mistake.

export function normalize(text) {
  return text.trim().split(/\s+/).join(' ').toLowerCase()
}

export function foldAccents(text) {
  return normalize(text).normalize('NFD').replace(/\p{Mn}/gu, '')
}

// → 'correct' | 'almost' | 'wrong'
export function gradeForm(answer, correct, alternates = []) {
  const given = normalize(answer)
  if (!given) return 'wrong'
  const accepted = [correct, ...alternates]
  if (accepted.some(f => normalize(f) === given)) return 'correct'
  const folded = foldAccents(answer)
  if (accepted.some(f => foldAccents(f) === folded)) return 'almost'
  return 'wrong'
}
