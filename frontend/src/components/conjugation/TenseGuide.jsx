import { useState } from 'react'
import ChatPanel from './ChatPanel'

const TENSES = {
  french: [
    {
      name: 'Présent de l\'indicatif',
      mood: 'Indicatif', tense: 'Présent',
      when: 'Current actions, habits, general truths, and near-future intentions.',
      examples: ['Je mange une pomme. (I\'m eating an apple)', 'Elle parle français. (She speaks French)', 'Je pars demain. (I\'m leaving tomorrow)'],
      tip: 'Most versatile tense — used far more broadly than the English simple present.',
    },
    {
      name: 'Imparfait',
      mood: 'Indicatif', tense: 'Imparfait',
      when: 'Ongoing or habitual past actions, background descriptions, and states. "Used to" or "was/were -ing" in English.',
      examples: ['Quand j\'étais enfant, je jouais au foot. (When I was a child I played football)', 'Il faisait beau. (The weather was nice)'],
      tip: 'Imparfait = backdrop/ongoing action. Passé composé = the event that happens in that backdrop.',
    },
    {
      name: 'Passé simple',
      mood: 'Indicatif', tense: 'Passé Simple',
      when: 'Completed past events in literary writing and formal narration.',
      examples: ['Il parla longuement. (He spoke at length)', 'Elle naquit en 1850. (She was born in 1850)'],
      tip: 'Mostly written French — in conversation, use passé composé instead.',
    },
    {
      name: 'Futur simple',
      mood: 'Indicatif', tense: 'Futur',
      when: 'Future actions, predictions, and expressing certainty about what will happen.',
      examples: ['Je partirai demain. (I will leave tomorrow)', 'Il fera beau ce week-end. (It will be nice this weekend)'],
      tip: 'Formed by adding endings to the infinitive: -ai, -as, -a, -ons, -ez, -ont.',
    },
    {
      name: 'Conditionnel présent',
      mood: 'Conditionnel', tense: 'Présent',
      when: 'Hypothetical situations ("would"), polite requests, and the result clause of si + imparfait.',
      examples: ['Je voudrais un café. (I would like a coffee)', 'Si j\'avais le temps, j\'irais. (If I had time, I would go)'],
      tip: 'Identical endings to imparfait (-ais, -ais, -ait, -ions, -iez, -aient) but on the future stem.',
    },
    {
      name: 'Subjonctif présent',
      mood: 'Subjonctif', tense: 'Présent',
      when: 'After expressions of doubt, emotion, desire, necessity, and specific conjunctions (bien que, pour que, avant que…).',
      examples: ['Il faut que tu viennes. (You must come)', 'Je veux qu\'elle soit heureuse. (I want her to be happy)'],
      tip: 'Triggered by a change of subject after verbs like vouloir, falloir, craindre, regretter.',
    },
    {
      name: 'Subjonctif imparfait',
      mood: 'Subjonctif', tense: 'Imparfait',
      when: 'Literary/formal past subjunctive, used after si or in formal written French.',
      examples: ['Il fallait qu\'il parlât. (It was necessary that he speak — formal)', 'Bien qu\'elle fût malade… (Although she was ill…)'],
      tip: 'Rarely used in modern spoken French. Recognise it, but use subjonctif présent in speech.',
    },
  ],
  spanish: [
    {
      name: 'Presente de indicativo',
      mood: 'Indicativo', tense: 'Indicativo Presente',
      when: 'Current actions, habits, general truths, and near-future events.',
      examples: ['Hablo español. (I speak Spanish)', 'El tren sale a las ocho. (The train leaves at eight)'],
      tip: 'Also used for dramatic narration of past events (present histórico).',
    },
    {
      name: 'Pretérito indefinido',
      mood: 'Indicativo', tense: 'Indicativo pretérito perfecto simple',
      when: 'Completed past actions at a specific or implied moment in time.',
      examples: ['Ayer comí pizza. (Yesterday I ate pizza)', 'Columbus llegó en 1492. (Columbus arrived in 1492)'],
      tip: 'Used for finished events. In Spain, pretérito perfecto compuesto (he comido) is preferred for recent actions.',
    },
    {
      name: 'Pretérito imperfecto',
      mood: 'Indicativo', tense: 'Indicativo pretérito imperfecto',
      when: 'Habitual or ongoing past actions, descriptions, and background context.',
      examples: ['Cuando era niño, jugaba al fútbol. (When I was a child, I used to play football)', 'Llovía mucho. (It was raining a lot)'],
      tip: 'Imperfecto = background/state/habit. Indefinido = the event that interrupts it.',
    },
    {
      name: 'Futuro simple',
      mood: 'Indicativo', tense: 'Indicativo futuro',
      when: 'Future actions, predictions, and conjecture about present facts.',
      examples: ['Mañana iré al mercado. (Tomorrow I will go to the market)', '¿Qué hora será? (What time might it be?)'],
      tip: 'Regular verbs use the infinitive + endings: -é, -ás, -á, -emos, -éis, -án.',
    },
    {
      name: 'Condicional simple',
      mood: 'Condicional', tense: 'Condicional',
      when: 'Hypothetical situations ("would"), polite requests, and the result clause of si + imperfecto.',
      examples: ['Me gustaría un café. (I would like a coffee)', 'Si tuviera dinero, viajaría. (If I had money, I would travel)'],
      tip: 'Same stems as futuro — irregular stems are identical for both tenses.',
    },
    {
      name: 'Subjuntivo presente',
      mood: 'Subjuntivo', tense: 'Subjuntivo Presente',
      when: 'After expressions of desire, emotion, doubt, and necessity, and with certain conjunctions.',
      examples: ['Quiero que vengas. (I want you to come)', 'Es importante que estudies. (It\'s important that you study)'],
      tip: 'Key trigger: a change of subject after querer que, esperar que, dudar que, para que, etc.',
    },
  ],
  english: [
    {
      name: 'Simple Present',
      mood: 'indicative', tense: 'indicative present',
      when: 'Habits, routines, general truths, and scheduled future events.',
      examples: ['I eat breakfast every day.', 'The sun rises in the east.', 'The train leaves at 9 a.m.'],
      tip: 'Add -s/-es for third person singular: "He works", "She watches".',
    },
    {
      name: 'Present Continuous',
      mood: 'indicative', tense: 'indicative present continuous',
      when: 'Actions happening right now, temporary situations, and definite near-future plans.',
      examples: ['I am reading a book.', 'She is staying with friends this week.', 'We are meeting tomorrow.'],
      tip: 'Formed with am/is/are + -ing. Not used with stative verbs like know, like, want.',
    },
    {
      name: 'Simple Past',
      mood: 'indicative', tense: 'indicative past tense',
      when: 'Completed actions at a specific time in the past.',
      examples: ['I went to the store yesterday.', 'She called me last night.', 'They finished the project.'],
      tip: 'Regular verbs add -ed. English has ~200 common irregular past forms to memorise.',
    },
    {
      name: 'Present Perfect',
      mood: 'indicative', tense: 'indicative present perfect',
      when: 'Past actions with present relevance, life experience, and recently completed actions.',
      examples: ['I have eaten already.', 'She has lived here for five years.', 'Have you ever been to Paris?'],
      tip: 'Use with "already", "yet", "ever", "just", "since", "for". Never with a specific past time.',
    },
  ],
}

export default function TenseGuide({ language }) {
  const [open, setOpen] = useState(null)
  const tenses = TENSES[language] || []

  const systemPrompt = `You are a helpful language teacher specialising in ${language} grammar.
Answer questions clearly and concisely, always providing examples in ${language} with translations.`

  return (
    <div>
      <div style={s.grid}>
        {tenses.map((t, i) => (
          <div key={i} style={s.card} onClick={() => setOpen(open === i ? null : i)}>
            <div style={s.cardHeader}>
              <span style={s.tenseName}>{t.name}</span>
              <span style={s.arrow}>{open === i ? '▲' : '▼'}</span>
            </div>
            <p style={s.preview}>{t.when}</p>
            {open === i && (
              <div style={s.detail}>
                <div style={s.examples}>
                  {t.examples.map((ex, j) => (
                    <p key={j} style={s.example}>{ex}</p>
                  ))}
                </div>
                {t.tip && <p style={s.tip}>💡 {t.tip}</p>}
              </div>
            )}
          </div>
        ))}
      </div>

      <div style={{ marginTop: '2rem' }}>
        <h3 style={s.chatTitle}>Chat with the AI about any tense</h3>
        <ChatPanel
          systemPrompt={systemPrompt}
          placeholder={`Ask about ${language} tenses, conjugation rules, exceptions…`}
        />
      </div>
    </div>
  )
}

const s = {
  grid: { display: 'flex', flexDirection: 'column', gap: '0.75rem' },
  card: { background: '#fff', border: '1px solid #e5e7eb', borderRadius: 10, padding: '1rem 1.25rem', cursor: 'pointer', transition: 'box-shadow 0.15s' },
  cardHeader: { display: 'flex', justifyContent: 'space-between', alignItems: 'center' },
  tenseName: { fontWeight: 700, fontSize: '1rem', color: '#1e1b4b' },
  arrow: { color: '#6b7280', fontSize: '0.75rem' },
  preview: { margin: '0.35rem 0 0', fontSize: '0.88rem', color: '#6b7280' },
  detail: { marginTop: '0.75rem', borderTop: '1px solid #f3f4f6', paddingTop: '0.75rem' },
  examples: { display: 'flex', flexDirection: 'column', gap: '0.25rem' },
  example: { margin: 0, fontSize: '0.9rem', fontStyle: 'italic', color: '#374151' },
  tip: { margin: '0.75rem 0 0', fontSize: '0.88rem', background: '#eff6ff', color: '#1e40af', padding: '0.5rem 0.75rem', borderRadius: 6 },
  chatTitle: { fontSize: '1rem', fontWeight: 600, marginBottom: '0.75rem', color: '#374151' },
}
