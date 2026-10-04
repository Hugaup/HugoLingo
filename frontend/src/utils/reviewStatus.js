// Where something you got wrong stands (see services/history.review_status):
// needs work → getting there (right since, check-ups pending) → fixed.

export const STATUS_LABELS = {
  needs_work: 'Needs work',
  getting_there: 'Getting there',
  fixed: 'Fixed',
}

const DAY = 24 * 60 * 60 * 1000
// Same as the backend's DUE_SLACK: a check-up opens 8 hours before its due time
const DUE_SLACK = 8 * 60 * 60 * 1000

// "check-up due" | "check-up tomorrow" | "check-up in 3 days", counted in the
// browser's calendar days from when the check-up opens.
export function checkUpLabel(dueAt, now = new Date()) {
  const opens = new Date(new Date(dueAt).getTime() - DUE_SLACK)
  if (opens <= now) return 'check-up due'
  const startOfDay = d => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()
  const days = Math.max(1, Math.round((startOfDay(opens) - startOfDay(now)) / DAY))
  return days === 1 ? 'check-up tomorrow' : `check-up in ${days} days`
}
