import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import TenseGuide from '../components/conjugation/TenseGuide'
import VerbLookup from '../components/conjugation/VerbLookup'
import VerbTableExercise from '../components/conjugation/VerbTableExercise'
import SentenceCompletion from '../components/conjugation/SentenceCompletion'
import { ui } from '../theme'

export default function Conjugation() {
  const { language } = useParams()
  const navigate = useNavigate()
  const [mainTab, setMainTab]   = useState('learn')
  const [learnTab, setLearnTab] = useState('tenses')
  const [testType, setTestType] = useState(null)

  const cap = str => str.charAt(0).toUpperCase() + str.slice(1)

  return (
    <div style={s.page}>
      <div style={s.topBar}>
        <button style={s.back} onClick={() => navigate(`/practice/${language}`)}>← Practice</button>
        <h1 style={s.title}>Conjugation — {cap(language)}</h1>
      </div>

      <div style={s.tabRow}>
        <button
          style={mainTab === 'learn' ? { ...s.tab, ...s.tabOn } : s.tab}
          onClick={() => { setMainTab('learn'); setTestType(null) }}
        >Learn</button>
        <button
          style={mainTab === 'test' ? { ...s.tab, ...s.tabOn } : s.tab}
          onClick={() => setMainTab('test')}
        >Test Yourself</button>
      </div>

      <div style={s.content}>
        {mainTab === 'learn' && (
          <div>
            <div style={s.subTabRow}>
              <button style={learnTab === 'tenses' ? { ...s.subTab, ...s.subTabOn } : s.subTab} onClick={() => setLearnTab('tenses')}>
                Tense Guide
              </button>
              <button style={learnTab === 'lookup' ? { ...s.subTab, ...s.subTabOn } : s.subTab} onClick={() => setLearnTab('lookup')}>
                Verb Lookup
              </button>
            </div>
            {learnTab === 'tenses' && <TenseGuide language={language} />}
            {learnTab === 'lookup' && <VerbLookup key={language} language={language} />}
          </div>
        )}

        {mainTab === 'test' && (
          <div>
            {testType === null && (
              <div>
                <p style={s.chooseLabel}>Choose an exercise type:</p>
                <div style={s.exerciseCards}>
                  <button style={s.exCard} onClick={() => setTestType('verb-table')}>
                    <span style={s.exCardIcon}>📋</span>
                    <span style={s.exCardTitle}>Verb Table</span>
                    <span style={s.exCardDesc}>
                      Fill in a complete conjugation table. Select verbs by ending, difficulty, or manually.
                    </span>
                  </button>
                  <button style={s.exCard} onClick={() => setTestType('sentence')}>
                    <span style={s.exCardIcon}>✍️</span>
                    <span style={s.exCardTitle}>Sentence Completion</span>
                    <span style={s.exCardDesc}>
                      Complete sentences with the correct conjugated form and identify the tense.
                    </span>
                  </button>
                </div>
              </div>
            )}
            {testType === 'verb-table' && <VerbTableExercise key={language} language={language} onBack={() => setTestType(null)} />}
            {testType === 'sentence'   && <SentenceCompletion language={language} onBack={() => setTestType(null)} />}
          </div>
        )}
      </div>
    </div>
  )
}

const s = {
  page: { ...ui.page, maxWidth: 940 },
  topBar: { display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '1.5rem' },
  back: { ...ui.back, whiteSpace: 'nowrap' },
  title: { ...ui.h1, margin: 0 },
  tabRow: { display: 'flex', borderBottom: '2px solid #e5e7eb', marginBottom: '1.5rem' },
  tab: { padding: '0.6rem 1.5rem', background: 'none', border: 'none', cursor: 'pointer', fontSize: '0.95rem', fontWeight: 600, color: '#6b7280', borderBottom: '3px solid transparent', marginBottom: -2 },
  tabOn: { color: '#4f46e5', borderBottomColor: '#4f46e5' },
  content: { minHeight: 400 },
  subTabRow: { display: 'flex', gap: '0.5rem', marginBottom: '1.25rem' },
  subTab: { ...ui.chip, borderRadius: 8 },
  subTabOn: ui.chipSoftOn,
  chooseLabel: { fontWeight: 600, color: '#374151', marginBottom: '1rem' },
  exerciseCards: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '1rem' },
  exCard: { display: 'flex', flexDirection: 'column', gap: '0.5rem', background: '#fff', border: '2px solid #e5e7eb', borderRadius: 12, padding: '1.5rem', cursor: 'pointer', textAlign: 'left' },
  exCardIcon: { fontSize: '1.75rem' },
  exCardTitle: { fontWeight: 700, fontSize: '1rem', color: '#1e1b4b' },
  exCardDesc: { fontSize: '0.88rem', color: '#6b7280', lineHeight: 1.5 },
}
