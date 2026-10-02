const bare = word => word.toLowerCase().replace(/[^\p{L}\p{N}'’]/gu, '')

// The corrected message word by word, with the words the learner didn't write
// marked (so "Yo quiero un café" shows "quiero" as the fix)
export function markChanges(original, corrected) {
  const left = new Map()
  for (const w of original.split(/\s+/).map(bare).filter(Boolean)) left.set(w, (left.get(w) ?? 0) + 1)
  return corrected.split(/\s+/).filter(Boolean).map(word => {
    const key = bare(word)
    const n = left.get(key) ?? 0
    if (!key || n > 0) {
      left.set(key, n - 1)
      return { word, changed: false }
    }
    return { word, changed: true }
  })
}
