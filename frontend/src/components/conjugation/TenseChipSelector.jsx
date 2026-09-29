import { Fragment } from 'react'
import { groupTensesBySection, tenseLabel } from '../../utils/conjugationUtils'

// Renders a tense picker as a table — one section header row per mood group
// (spanning both columns) followed by two-per-row checkbox cells — mirroring a
// traditional conjugation-trainer layout instead of one flat wrapped chip row.
export default function TenseChipSelector({ language, tenses, selectedKeys, onToggle }) {
  const sections = groupTensesBySection(language, tenses)

  return (
    <table style={s.table}>
      <tbody>
        {sections.map(({ section, tenses: sectionTenses }) => {
          const rows = []
          for (let i = 0; i < sectionTenses.length; i += 2) {
            rows.push([sectionTenses[i], sectionTenses[i + 1]])
          }
          return (
            <Fragment key={section}>
              <tr key={`${section}-header`}>
                <td colSpan={2} style={s.sectionHeader}>{section}</td>
              </tr>
              {rows.map((pair, i) => (
                <tr key={`${section}-${i}`}>
                  {pair.map((t, j) => {
                    if (!t) return <td key={j} style={s.cell} />
                    const key = `${t.mood}||${t.tense}`
                    return (
                      <td key={j} style={s.cell}>
                        <label style={s.checkLabel}>
                          <input
                            type="checkbox"
                            checked={selectedKeys.includes(key)}
                            onChange={() => onToggle(key)}
                          />
                          {tenseLabel(language, t.mood, t.tense)}
                        </label>
                      </td>
                    )
                  })}
                </tr>
              ))}
            </Fragment>
          )
        })}
      </tbody>
    </table>
  )
}

const s = {
  table: { width: '100%', borderCollapse: 'collapse' },
  sectionHeader: { padding: '0.75rem 0.25rem 0.4rem', fontWeight: 700, fontSize: '0.8rem', color: '#4f46e5', textTransform: 'uppercase', letterSpacing: '0.04em', borderBottom: '2px solid #e0e7ff' },
  cell: { padding: '0.3rem 0.5rem', width: '50%' },
  checkLabel: { display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.9rem', cursor: 'pointer' },
}
