import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import ConversationChat from '../components/conversation/ConversationChat'
import { ui } from '../theme'

// Pick a role-play scenario, then chat with the AI in the target language.
export default function Conversation() {
  const { language } = useParams()
  const navigate = useNavigate()
  const [scenarios, setScenarios] = useState(null)
  const [error, setError] = useState(null)
  const [active, setActive] = useState(null)
  const [round, setRound] = useState(0)
  const cap = str => str.charAt(0).toUpperCase() + str.slice(1)

  useEffect(() => {
    api.getScenarios().then(setScenarios).catch(e => setError(e.message))
  }, [])

  let body
  if (error) body = <p style={s.error}>{error}</p>
  else if (!scenarios) body = <p style={s.muted}>Loading…</p>
  else if (active) {
    body = (
      <>
        <div style={s.chatHeader}>
          <button style={s.back} onClick={() => setActive(null)}>← Scenarios</button>
          <h2 style={s.scenarioTitle}>{active.title}</h2>
        </div>
        <ConversationChat key={round} language={language} scenario={active} onRestart={() => setRound(r => r + 1)} />
      </>
    )
  } else {
    body = (
      <>
        <p style={s.intro}>
          Pick a situation and chat with the AI in {cap(language)}. Each message you send is checked,
          and corrections appear right under it. Click any word the AI writes to see what it means.
        </p>
        <div style={s.grid}>
          {scenarios.map(sc => (
            <button key={sc.id} className="hl-tile" style={s.card} onClick={() => { setActive(sc); setRound(r => r + 1) }}>
              <span style={s.cardTitle}>{sc.title}</span>
              <span style={s.cardDesc}>{sc.description}</span>
            </button>
          ))}
        </div>
      </>
    )
  }

  return (
    <div style={s.page}>
      <button style={s.back} onClick={() => navigate(`/practice/${language}`)}>← Practice</button>
      <h1 style={s.title}>Conversation — {cap(language)}</h1>
      {body}
    </div>
  )
}

const s = {
  page: { ...ui.page, maxWidth: 760 },
  back: ui.back,
  title: ui.h1,
  intro: { color: '#4b5563', fontSize: '0.95rem', lineHeight: 1.5, margin: '0 0 1.25rem' },
  grid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(210px, 1fr))', gap: '0.75rem' },
  card: ui.tile,
  cardTitle: { fontWeight: 700, color: '#1e1b4b', fontSize: '1rem' },
  cardDesc: { color: '#6b7280', fontSize: '0.85rem' },
  chatHeader: { display: 'flex', alignItems: 'baseline', gap: '1rem', marginBottom: '0.75rem' },
  scenarioTitle: { fontSize: '1.15rem', fontWeight: 700, color: '#1e1b4b', margin: 0 },
  muted: { color: '#6b7280' },
  error: { color: '#b91c1c' },
}
