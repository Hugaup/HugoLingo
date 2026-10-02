import { useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { LANGUAGES } from '../constants'

export default function Welcome() {
  const navigate = useNavigate()
  const { user } = useAuth()

  // The language picked in Settings comes first
  const languages = [...LANGUAGES].sort(
    (a, b) => (b.code === user.target_language) - (a.code === user.target_language),
  )

  return (
    <div style={s.page}>
      <div style={s.hero}>
        <h1 style={s.title}>Welcome, {user.username}</h1>
        <p style={s.subtitle}>Which language would you like to practice?</p>
      </div>
      <div style={s.grid}>
        {languages.map(l => {
          const isMine = l.code === user.target_language
          return (
            <button
              key={l.code}
              style={isMine ? { ...s.card, ...s.cardMine } : s.card}
              onClick={() => navigate(`/practice/${l.code}`)}
            >
              <span style={s.flag}>{l.flag}</span>
              <span style={s.name}>{l.label}</span>
              <span style={s.native}>{isMine ? 'Your language' : l.native}</span>
            </button>
          )
        })}
      </div>
    </div>
  )
}

const s = {
  page: { maxWidth: 580, margin: '0 auto', padding: '5rem 1.5rem 2rem', fontFamily: 'system-ui, sans-serif', textAlign: 'center' },
  hero: { marginBottom: '3rem' },
  title: { fontSize: '2.75rem', fontWeight: 800, color: '#1e1b4b', margin: '0 0 0.6rem' },
  subtitle: { fontSize: '1.15rem', color: '#6b7280', margin: 0 },
  grid: { display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1rem' },
  card: { display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '0.5rem', background: '#fff', border: '2px solid #e5e7eb', borderRadius: 16, padding: '2rem 1rem', cursor: 'pointer', fontFamily: 'inherit', transition: 'border-color 0.15s, box-shadow 0.15s' },
  cardMine: { borderColor: '#4f46e5' },
  flag: { fontSize: '2.75rem' },
  name: { fontWeight: 700, fontSize: '1.05rem', color: '#1e1b4b' },
  native: { fontSize: '0.82rem', color: '#9ca3af' },
}
