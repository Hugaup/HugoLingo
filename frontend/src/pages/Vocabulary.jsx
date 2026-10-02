import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import VocabSession from '../components/vocab/VocabSession'
import VocabBrowse from '../components/vocab/VocabBrowse'
import { canSpeak } from '../utils/speech'
import { MODES, byTopicOrder, topicLabel } from '../utils/vocab'
import { ui } from '../theme'

const SESSION_LENGTH = 10

export default function Vocabulary() {
  const { language } = useParams()
  const navigate = useNavigate()
  const [overview, setOverview] = useState(null)
  const [error, setError] = useState(null)
  const [mode, setMode] = useState('mixed')
  // { name: 'home' } | { name: 'session', items, scope } | { name: 'browse', scope }
  const [view, setView] = useState({ name: 'home' })
  const [round, setRound] = useState(0)
  const cap = str => str.charAt(0).toUpperCase() + str.slice(1)

  useEffect(() => {
    api.getVocabOverview(language).then(setOverview).catch(e => setError(e.message))
  }, [language, view.name])

  async function start(scope) {
    setError(null)
    try {
      const items = await api.getVocabSession(language, { ...scope, count: SESSION_LENGTH })
      setRound(r => r + 1)
      setView({ name: 'session', items, scope })
    } catch (e) {
      setError(e.message)
    }
  }

  const home = () => setView({ name: 'home' })

  let body
  if (error) body = <p style={s.error}>{error}</p>
  else if (!overview) body = <p style={s.muted}>Loading…</p>
  else if (!overview.available) {
    body = <p style={s.muted}>Vocabulary isn't available for {cap(language)} yet.</p>
  } else if (view.name === 'session') {
    body = (
      <>
        <button style={s.back} onClick={home}>← All topics</button>
        <div style={{ marginTop: '0.75rem' }}>
          <VocabSession
            key={round}
            language={language}
            items={view.items}
            mode={mode}
            onRestart={() => start(view.scope)}
          />
        </div>
      </>
    )
  } else if (view.name === 'browse') {
    body = <VocabBrowse language={language} {...view.scope} onBack={home} onPractise={() => start(view.scope)} />
  } else {
    body = <Home overview={overview} mode={mode} setMode={setMode} start={start} browse={scope => setView({ name: 'browse', scope })} />
  }

  return (
    <div style={s.page}>
      <button style={s.back} onClick={() => navigate(`/practice/${language}`)}>← Practice</button>
      <h1 style={s.title}>Vocabulary — {cap(language)}</h1>
      {body}
    </div>
  )
}

function Home({ overview, mode, setMode, start, browse }) {
  const words = overview.groups.filter(g => g.kind === 'word').sort((a, b) => byTopicOrder(a.topic, b.topic))
  const phrases = overview.groups.filter(g => g.kind === 'phrase')
  const mine = overview.groups.find(g => g.kind === 'personal')
  const sum = (groups, key) => groups.reduce((n, g) => n + g[key], 0)

  return (
    <>
      <div style={s.modes} role="radiogroup" aria-label="Exercise type">
        {MODES.filter(m => !m.needsSpeech || canSpeak()).map(m => (
          <button
            key={m.id}
            role="radio"
            aria-checked={mode === m.id}
            style={mode === m.id ? { ...s.chip, ...s.chipActive } : s.chip}
            onClick={() => setMode(m.id)}
          >
            {m.label}
          </button>
        ))}
      </div>

      {overview.due > 0 && (
        <div style={s.review}>
          <span><strong>{overview.due}</strong> {overview.due === 1 ? 'item is' : 'items are'} due for review</span>
          <button style={s.primary} onClick={() => start({})}>Review now</button>
        </div>
      )}

      <section style={{ ...s.card, ...s.phrases }} aria-label="Everyday phrases">
        <div>
          <h2 style={s.cardTitle}>Everyday phrases</h2>
          <p style={s.cardSub}>Hello, thank you, please, sorry, how much is it?…</p>
          <Progress learned={sum(phrases, 'learned')} total={sum(phrases, 'total')} />
        </div>
        <div style={s.cardActions}>
          <button style={s.primary} onClick={() => start({ kind: 'phrase' })}>Practise</button>
          <button style={s.link} onClick={() => browse({ kind: 'phrase' })}>See all</button>
        </div>
      </section>

      {mine && (
        <section style={{ ...s.card, ...s.phrases }} aria-label="My words">
          <div>
            <h2 style={s.cardTitle}>My words</h2>
            <p style={s.cardSub}>Words you saved while reading</p>
            <Progress learned={mine.learned} total={mine.total} />
          </div>
          <div style={s.cardActions}>
            <button style={s.primary} onClick={() => start({ kind: 'personal' })}>Practise</button>
            <button style={s.link} onClick={() => browse({ kind: 'personal' })}>See all</button>
          </div>
        </section>
      )}

      <h2 style={s.sectionTitle}>Words by topic</h2>
      <div style={s.grid}>
        {words.map(g => (
          <section key={g.topic} style={s.card} aria-label={topicLabel(g.topic)}>
            <h3 style={s.cardTitle}>{topicLabel(g.topic)}</h3>
            <Progress learned={g.learned} total={g.total} />
            {g.due > 0 && <span style={s.due}>{g.due} due</span>}
            <div style={s.cardActions}>
              <button style={s.primary} onClick={() => start({ kind: 'word', topic: g.topic })}>Practise</button>
              <button style={s.link} onClick={() => browse({ kind: 'word', topic: g.topic })}>See words</button>
            </div>
          </section>
        ))}
      </div>
    </>
  )
}

function Progress({ learned, total }) {
  return (
    <div style={s.progressWrap}>
      <div
        style={s.bar}
        role="progressbar"
        aria-label="Learned"
        aria-valuemin={0}
        aria-valuemax={total}
        aria-valuenow={learned}
      >
        <div style={{ ...s.fill, width: `${total ? (learned / total) * 100 : 0}%` }} />
      </div>
      <span style={s.count}>{learned} / {total} learned</span>
    </div>
  )
}

const s = {
  page: ui.page,
  back: ui.back,
  title: ui.h1,
  modes: { display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginBottom: '1.25rem' },
  chip: ui.chip,
  chipActive: ui.chipOn,
  review: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '1rem', background: '#eef2ff', borderRadius: 12, padding: '0.9rem 1.1rem', marginBottom: '1rem', color: '#1e1b4b' },
  card: { display: 'flex', flexDirection: 'column', gap: '0.5rem', background: '#f8f9fa', borderRadius: 12, padding: '1rem 1.1rem' },
  phrases: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: '1rem', flexWrap: 'wrap', marginBottom: '1.5rem' },
  cardTitle: { fontSize: '1rem', fontWeight: 700, color: '#1e1b4b', margin: 0 },
  cardSub: { fontSize: '0.85rem', color: '#6b7280', margin: '0.2rem 0 0.5rem' },
  cardActions: { display: 'flex', gap: '0.75rem', alignItems: 'center', marginTop: 'auto' },
  sectionTitle: { fontSize: '1.05rem', fontWeight: 700, color: '#1e1b4b', margin: '0 0 0.75rem' },
  grid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: '0.75rem' },
  progressWrap: { display: 'flex', alignItems: 'center', gap: '0.6rem' },
  bar: { flex: 1, height: 6, borderRadius: 3, background: '#e0e7ff', overflow: 'hidden', minWidth: 80 },
  fill: { height: '100%', background: '#4f46e5', borderRadius: 3 },
  count: { fontSize: '0.75rem', color: '#6b7280', whiteSpace: 'nowrap' },
  due: { fontSize: '0.75rem', color: '#4f46e5', fontWeight: 600 },
  primary: { ...ui.primary, padding: '0.45rem 0.95rem', fontSize: '0.88rem' },
  link: ui.link,
  muted: { color: '#6b7280' },
  error: { color: '#b91c1c' },
}
