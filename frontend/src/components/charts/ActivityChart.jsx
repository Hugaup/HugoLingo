import { useState } from 'react'

// Single series → one brand hue, no legend (the section title names it).
// Validated ≥3:1 against the white page with the dataviz palette checker.
const BAR = '#4f46e5'
const PLOT_HEIGHT = 120

function formatDay(iso) {
  return new Date(`${iso}T00:00`).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

// Centre the tooltip over its column, but pin it to the plot's edge for the first
// and last few days so it never spills outside the card.
function tooltipPosition(index, count) {
  const share = (index + 0.5) / count
  if (share > 0.85) return { right: 0, transform: 'none' }
  if (share < 0.15) return { left: '2rem', transform: 'none' }
  return { left: `calc(2rem + (100% - 2rem) * ${share})` }
}

// Answers per day as columns, with a hover/focus tooltip per day and a table view.
export default function ActivityChart({ daily }) {
  const [active, setActive] = useState(null)
  const max = Math.max(1, ...daily.map(d => d.total))
  const sum = daily.reduce((n, d) => n + d.total, 0)
  const activeDay = active === null ? null : daily[active]

  return (
    <figure style={s.figure}>
      <div
        style={s.plot}
        role="img"
        aria-label={`Answers per day over the last ${daily.length} days: ${sum} in total, at most ${max} in one day.`}
      >
        <span style={s.axisMax}>{max}</span>
        <div style={s.gridline} />
        <div style={s.bars} onMouseLeave={() => setActive(null)}>
          {daily.map((d, i) => (
            // The whole column is the hit target, not just the (possibly tiny) bar
            <div
              key={d.date}
              style={s.slot}
              onMouseEnter={() => setActive(i)}
              onFocus={() => setActive(i)}
              onBlur={() => setActive(null)}
              tabIndex={0}
              aria-label={`${formatDay(d.date)}: ${d.total} answers, ${d.correct} correct`}
            >
              <div
                style={{
                  ...s.bar,
                  height: d.total ? Math.max(3, (d.total / max) * PLOT_HEIGHT) : 0,
                  opacity: active === null || active === i ? 1 : 0.45,
                }}
              />
            </div>
          ))}
        </div>
        {activeDay && (
          <div
            role="tooltip"
            style={{ ...s.tooltip, ...tooltipPosition(active, daily.length) }}
          >
            <strong>{formatDay(activeDay.date)}</strong>
            <span>{activeDay.total} answers · {activeDay.correct} correct</span>
          </div>
        )}
      </div>
      <div style={s.xLabels}>
        <span>{formatDay(daily[0].date)}</span>
        <span>Today</span>
      </div>
      <details style={s.details}>
        <summary style={s.summary}>Show as table</summary>
        <table style={s.table}>
          <thead><tr><th style={s.th}>Day</th><th style={s.thNum}>Answers</th><th style={s.thNum}>Correct</th></tr></thead>
          <tbody>
            {daily.filter(d => d.total).map(d => (
              <tr key={d.date}>
                <td style={s.td}>{formatDay(d.date)}</td>
                <td style={s.tdNum}>{d.total}</td>
                <td style={s.tdNum}>{d.correct}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </figure>
  )
}

const s = {
  figure: { margin: 0 },
  plot: { position: 'relative', height: PLOT_HEIGHT, paddingLeft: '2rem' },
  axisMax: { position: 'absolute', left: 0, top: -6, fontSize: '0.7rem', color: '#898781', fontVariantNumeric: 'tabular-nums' },
  gridline: { position: 'absolute', left: '2rem', right: 0, top: 0, borderTop: '1px solid #e1e0d9' },
  bars: { display: 'flex', alignItems: 'flex-end', height: '100%', borderBottom: '1px solid #c3c2b7' },
  slot: { flex: 1, height: '100%', display: 'flex', alignItems: 'flex-end', padding: '0 1px', cursor: 'default', outline: 'none' },
  bar: { width: '100%', background: BAR, borderRadius: '4px 4px 0 0', transition: 'opacity 0.1s' },
  tooltip: {
    position: 'absolute', bottom: PLOT_HEIGHT + 8, transform: 'translateX(-50%)',
    display: 'flex', flexDirection: 'column', gap: 2, whiteSpace: 'nowrap',
    background: '#fff', border: '1px solid rgba(11,11,11,0.10)', boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
    borderRadius: 8, padding: '0.35rem 0.6rem', fontSize: '0.78rem', color: '#0b0b0b', pointerEvents: 'none',
  },
  xLabels: { display: 'flex', justifyContent: 'space-between', paddingLeft: '2rem', marginTop: 4, fontSize: '0.72rem', color: '#898781' },
  details: { marginTop: '0.5rem', fontSize: '0.8rem', color: '#52514e' },
  summary: { cursor: 'pointer' },
  table: { borderCollapse: 'collapse', marginTop: '0.4rem' },
  th: { textAlign: 'left', padding: '0.2rem 0.8rem 0.2rem 0', fontWeight: 600 },
  thNum: { textAlign: 'right', padding: '0.2rem 0 0.2rem 0.8rem', fontWeight: 600 },
  td: { padding: '0.15rem 0.8rem 0.15rem 0' },
  tdNum: { textAlign: 'right', padding: '0.15rem 0 0.15rem 0.8rem', fontVariantNumeric: 'tabular-nums' },
}
