import { useState } from 'react'
import { sortTenses, tenseLabel } from '../../utils/conjugationUtils'

// Accuracy is a magnitude → one-hue ordinal ramp, darker = stronger. Five bins,
// validated with the dataviz checker (monotone, distinct steps, light end ≥2:1
// on white so a 0% cell never fades into the page). Each cell also prints its
// percentage, so the colour never carries the meaning alone.
const RAMP = ['#86b6ef', '#5598e7', '#2a78d6', '#1c5cab', '#104281']
const INK  = ['#0b0b0b', '#0b0b0b', '#ffffff', '#ffffff', '#ffffff']
const BIN_LABELS = ['0–19%', '20–39%', '40–59%', '60–79%', '80–100%']

const binOf = accuracy => Math.min(RAMP.length - 1, Math.floor(accuracy * RAMP.length))

// Verbs × tenses heatmap of the user's accuracy.
export default function AccuracyGrid({ language, grid }) {
  const [active, setActive] = useState(null)
  const tenses = sortTenses(language, grid.tenses)

  const describe = (verb, t, cell) => {
    const label = `${verb} · ${tenseLabel(language, t.mood, t.tense)} (${t.mood.toLowerCase()})`
    return cell
      ? `${label}: ${cell.correct} of ${cell.attempts} correct (${Math.round((cell.correct / cell.attempts) * 100)}%)`
      : `${label}: not practised yet`
  }

  return (
    <div>
      <div style={s.scroll}>
        <table style={s.table} onMouseLeave={() => setActive(null)}>
          <thead>
            <tr>
              <th style={s.corner} scope="col"><span style={s.srOnly}>Verb</span></th>
              {tenses.map(t => (
                <th key={`${t.mood}||${t.tense}`} style={s.colHead} scope="col">
                  <span style={s.colMood}>{t.mood.toLowerCase()}</span>
                  {tenseLabel(language, t.mood, t.tense)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {grid.rows.map(row => (
              <tr key={row.verb_infinitive}>
                <th style={s.rowHead} scope="row">{row.verb_infinitive}</th>
                {tenses.map(t => {
                  const cell = row.cells[`${t.mood}||${t.tense}`]
                  const text = describe(row.verb_infinitive, t, cell)
                  const show = () => setActive(text)
                  if (!cell) {
                    return <td key={t.tense} style={s.emptyCell} onMouseEnter={show} aria-label={text}>·</td>
                  }
                  const accuracy = cell.correct / cell.attempts
                  const bin = binOf(accuracy)
                  return (
                    <td
                      key={t.tense}
                      tabIndex={0}
                      style={{ ...s.cell, background: RAMP[bin], color: INK[bin] }}
                      onMouseEnter={show}
                      onFocus={show}
                      aria-label={text}
                    >
                      {Math.round(accuracy * 100)}%
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p style={s.detail} aria-live="polite">{active ?? 'Hover or tab to a cell for details.'}</p>

      <div style={s.legend} aria-label="Accuracy colour scale">
        <span style={s.legendTitle}>Accuracy</span>
        {RAMP.map((color, i) => (
          <span key={color} style={s.legendItem}>
            <span style={{ ...s.swatch, background: color }} />
            {BIN_LABELS[i]}
          </span>
        ))}
      </div>
    </div>
  )
}

const s = {
  scroll: { overflowX: 'auto' },
  table: { borderCollapse: 'separate', borderSpacing: 2, fontSize: '0.82rem' },
  corner: { minWidth: 80 },
  colHead: { fontWeight: 600, color: '#52514e', textAlign: 'center', padding: '0 0.3rem 0.3rem', verticalAlign: 'bottom', minWidth: 64, maxWidth: 110 },
  colMood: { display: 'block', fontWeight: 400, fontSize: '0.68rem', color: '#898781' },
  rowHead: { textAlign: 'left', fontWeight: 700, color: '#1e1b4b', paddingRight: '0.6rem', whiteSpace: 'nowrap' },
  cell: { textAlign: 'center', borderRadius: 4, padding: '0.45rem 0.3rem', fontWeight: 600, fontVariantNumeric: 'tabular-nums', cursor: 'default' },
  emptyCell: { textAlign: 'center', color: '#c3c2b7', background: '#f3f4f6', borderRadius: 4 },
  detail: { fontSize: '0.8rem', color: '#52514e', minHeight: '1.2em', margin: '0.5rem 0' },
  legend: { display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '0.75rem', fontSize: '0.75rem', color: '#52514e' },
  legendTitle: { fontWeight: 600 },
  legendItem: { display: 'inline-flex', alignItems: 'center', gap: 4 },
  swatch: { width: 12, height: 12, borderRadius: 3, display: 'inline-block' },
  srOnly: { position: 'absolute', width: 1, height: 1, overflow: 'hidden', clip: 'rect(0 0 0 0)' },
}
