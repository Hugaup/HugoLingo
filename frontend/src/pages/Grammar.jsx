import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import StatusBadge from '../components/StatusBadge'
import { LEVEL_NAMES, sheetsDone } from '../utils/grammar'
import { checkUpLabel } from '../utils/reviewStatus'
import { color, radius, ui } from '../theme'

// The grammar section's front page, laid out like lingua.com's: the overall
// grammar score, topics to review, then every topic by level and category with
// how many of its sheets are done.
export default function Grammar() {
  const { language } = useParams()
  const navigate = useNavigate()
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.getGrammar(language).then(setData).catch(e => setError(e.message))
  }, [language])

  const cap = str => str.charAt(0).toUpperCase() + str.slice(1)

  return (
    <div style={s.page}>
      <button style={s.back} onClick={() => navigate(`/practice/${language}`)}>← Practice</button>
      <h1 style={s.title}>Grammar — {cap(language)}</h1>
      {error && <p style={s.error}>{error}</p>}
      {!data && !error && <p style={s.muted}>Loading…</p>}
      {data && <Overview data={data} language={language} />}
    </div>
  )
}

function Overview({ data, language }) {
  const navigate = useNavigate()
  const open = topic => navigate(`/practice/${language}/grammar/${topic.id}`)
  if (!data.topics.length) return <p style={s.muted}>Grammar exercises aren't available for this language yet.</p>

  const score = data.questions ? Math.round((data.correct / data.questions) * 100) : 0
  const sheets = data.topics.reduce((n, t) => n + t.sheets.length, 0)
  const done = data.topics.reduce((n, t) => n + sheetsDone(t), 0)
  const toReview = data.topics.filter(t => t.status === 'needs_work' || t.status === 'getting_there')

  // Levels in order, then the categories that have topics at that level; topics
  // spanning every level (find the mistake) go in a section of their own
  const levels = [...new Set(data.topics.filter(t => t.level).map(t => t.level))].sort()
  const titles = Object.fromEntries(data.categories.map(c => [c.id, c.title]))
  const byCategory = topics => data.categories
    .map(c => ({ ...c, topics: topics.filter(t => t.category === c.id) }))
    .filter(c => c.topics.length)

  return (
    <>
      <section style={s.score} aria-label="Grammar score">
        <div style={s.scoreTop}>
          <span style={s.scoreLabel}>Grammar score</span>
          <span style={s.scoreValue}>{score}%</span>
        </div>
        <div style={s.meter} role="meter" aria-label="Grammar score" aria-valuemin={0} aria-valuemax={100} aria-valuenow={score}>
          <div style={{ ...s.meterFill, width: `${score}%` }} />
        </div>
        <p style={s.scoreNote}>
          {data.correct} of {data.questions} questions right · {done} of {sheets} sheets completed
        </p>
      </section>

      {toReview.length > 0 && (
        <section style={s.review} aria-labelledby="to-review">
          <h2 id="to-review" style={s.h2}>To review</h2>
          <ul style={s.reviewList}>
            {toReview.map(t => (
              <li key={t.id} style={s.reviewItem}>
                <button style={s.topicLink} onClick={() => open(t)}>{t.title}</button>
                <span style={s.reviewState}>
                  {t.status === 'getting_there' && <span style={s.note}>{checkUpLabel(t.due_at)}</span>}
                  <StatusBadge status={t.status} />
                  {(t.status === 'needs_work' || t.is_due) && (
                    <button
                      style={s.reviewBtn}
                      aria-label={`Review ${t.title}`}
                      onClick={() => navigate(`/practice/${language}/grammar/${t.id}/review`)}
                    >
                      Review
                    </button>
                  )}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {levels.map(level => (
        <section key={level} style={s.level} aria-labelledby={`level-${level}`}>
          <h2 id={`level-${level}`} style={s.levelTitle}>{LEVEL_NAMES[level]}</h2>
          {byCategory(data.topics.filter(t => t.level === level)).map(c => (
            <CategoryGroup key={c.id} title={c.title} topics={c.topics} onOpen={open} />
          ))}
        </section>
      ))}

      {data.topics.some(t => !t.level) && (
        <section style={s.level} aria-labelledby="level-mixed">
          <h2 id="level-mixed" style={s.levelTitle}>{titles.mixed ?? 'Mixed practice'}</h2>
          <CategoryGroup topics={data.topics.filter(t => !t.level)} onOpen={open} />
        </section>
      )}
    </>
  )
}

function CategoryGroup({ title, topics, onOpen }) {
  return (
    <div style={s.category}>
      {title && <h3 style={s.categoryTitle}>{title}</h3>}
      <ul style={s.list}>
        {topics.map(t => {
          const done = sheetsDone(t)
          return (
            <li key={t.id}>
              <button className="hl-tile" style={s.topic} onClick={() => onOpen(t)}>
                <span style={s.topicNames}>
                  <span style={s.topicTitle}>{t.title}</span>
                  <span style={s.topicSpanish}>{t.spanish}</span>
                </span>
                <span style={s.topicProgress}>
                  <StatusBadge status={t.status} />
                  <span style={done === t.sheets.length ? s.doneText : s.progressText}>
                    {done} of {t.sheets.length} {t.sheets.length === 1 ? 'sheet' : 'sheets'}
                  </span>
                </span>
              </button>
            </li>
          )
        })}
      </ul>
    </div>
  )
}

const s = {
  page: { ...ui.page, maxWidth: 760 },
  back: ui.back,
  title: ui.h1,
  muted: { color: color.muted },
  error: ui.error,
  h2: ui.h2,
  score: { ...ui.panel, padding: '1.1rem 1.25rem', marginBottom: '1.25rem' },
  scoreTop: { display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: '0.5rem' },
  scoreLabel: { fontWeight: 700, color: color.ink },
  scoreValue: { fontSize: '1.6rem', fontWeight: 800, color: color.primary },
  meter: { height: 8, borderRadius: 4, background: color.primaryBorder, overflow: 'hidden' },
  meterFill: { height: '100%', background: color.primary, borderRadius: 4 },
  scoreNote: { fontSize: '0.85rem', color: color.muted, margin: '0.5rem 0 0' },
  review: { borderWidth: 1, borderStyle: 'solid', borderColor: color.border, borderRadius: radius.md, padding: '1rem 1.25rem', marginBottom: '1.5rem' },
  reviewList: { listStyle: 'none', padding: 0, margin: 0 },
  reviewItem: { display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: '0.35rem 0.75rem', padding: '0.4rem 0', borderBottom: '1px solid #eceef1' },
  reviewState: { display: 'flex', alignItems: 'center', gap: '0.5rem', marginLeft: 'auto' },
  reviewBtn: { ...ui.secondary, padding: '0.3rem 0.8rem', fontSize: '0.82rem' },
  topicLink: { ...ui.link, fontSize: '0.95rem', fontWeight: 600, textAlign: 'left' },
  note: { color: color.muted, fontSize: '0.8rem' },
  level: { marginBottom: '1.75rem' },
  levelTitle: { fontSize: '1.2rem', fontWeight: 800, color: color.ink, margin: '0 0 0.75rem', paddingBottom: '0.4rem', borderBottom: `2px solid ${color.primaryBorder}` },
  category: { marginBottom: '1rem' },
  categoryTitle: { fontSize: '0.8rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', color: color.muted, margin: '0 0 0.4rem' },
  list: { listStyle: 'none', padding: 0, margin: 0, display: 'grid', gap: '0.4rem' },
  topic: { ...ui.tile, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.35rem 1rem', width: '100%', padding: '0.7rem 0.9rem', borderRadius: radius.sm },
  topicNames: { display: 'flex', flexDirection: 'column', minWidth: 0 },
  topicTitle: { fontWeight: 700, color: color.ink },
  topicSpanish: { fontSize: '0.82rem', color: color.muted },
  topicProgress: { display: 'flex', alignItems: 'center', gap: '0.6rem', marginLeft: 'auto' },
  progressText: { fontSize: '0.82rem', color: color.muted, whiteSpace: 'nowrap' },
  doneText: { fontSize: '0.82rem', color: color.success, fontWeight: 600, whiteSpace: 'nowrap' },
}
