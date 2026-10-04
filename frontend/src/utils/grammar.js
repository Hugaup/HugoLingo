// Shared by the grammar pages (pages/Grammar*.jsx)

export const LEVEL_NAMES = {
  1: 'A1 · Beginner',
  2: 'A2 · Elementary',
  3: 'B1 · Intermediate',
  4: 'B2 · Upper intermediate',
  5: 'C1 · Advanced',
}

export const LEVEL_SHORT = { 1: 'A1', 2: 'A2', 3: 'B1', 4: 'B2', 5: 'C1' }

// A sheet is done once every question on it has been answered
export const sheetsDone = topic => topic.sheets.filter(s => s.answered === s.questions).length

export const BLANK = '___'
