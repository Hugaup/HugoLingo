import { useState } from 'react'
import ChatPanel from './ChatPanel'
import { groupTensesBySection, tenseLabel } from '../../utils/conjugationUtils'

// Mood-level orientation: read this before diving into individual tenses.
const MOOD_GUIDES = {
  spanish: [
    {
      mood: 'Indicativo',
      accent: '#2563eb',
      summary: 'The mood of reality — facts, certainties, and things presented as objectively true.',
      when: 'Use indicativo for statements you consider true or definite: descriptions, narration, habits, plans, predictions. It\'s the default mood — if nothing specifically triggers subjuntivo or imperativo, you\'re in indicativo.',
      examples: ['Sé que ella vive en Madrid. (I know she lives in Madrid — stated as fact)', 'Creo que va a llover. (I think it\'s going to rain — a belief stated as likely fact)'],
    },
    {
      mood: 'Subjuntivo',
      accent: '#7c3aed',
      summary: 'The mood of subjectivity — doubt, emotion, desire, necessity, and things that aren\'t (yet) confirmed reality.',
      when: 'Triggered by specific verbs/expressions — remember W.E.I.R.D.O.: Wishes, Emotions, Impersonal expressions, Recommendations, Doubt/denial, Ojalá — almost always with a change of subject across the "que". The same verb can flip mood with meaning: "Creo que es verdad" (indicativo — stated as fact) vs "No creo que sea verdad" (subjuntivo — denial flips it).',
      triggers: ['querer que', 'esperar que', 'alegrarse de que', 'es importante que', 'dudar que / no creer que', 'ojalá', 'para que / antes de que'],
      examples: ['Quiero que vengas. (I want you to come — wish, different subjects)', 'Es posible que llueva. (It might rain — impersonal expression of possibility)', 'Ojalá tengas suerte. (I hope you have luck)'],
    },
    {
      mood: 'Imperativo',
      accent: '#ea580c',
      summary: 'The mood of direct commands — telling someone to do, or not do, something.',
      when: 'Affirmative commands (¡Ven! ¡Comed!) have their own dedicated forms. Negative commands (¡No vengas! ¡No comáis!) always borrow the present subjunctive instead — for every person, tú and vosotros included.',
      examples: ['Habla más despacio. (Speak more slowly — affirmative, tú)', 'No hables tan rápido. (Don\'t speak so fast — negative, uses subjuntivo presente "hables")'],
    },
  ],
}

const TENSES = {
  spanish: [
    // ── Indicativo (+ Condicional, grouped together like the rest of the app) ──
    {
      name: 'Presente', mood: 'Indicativo', tense: 'Indicativo presente',
      when: 'Habitual actions, general truths, near-future plans, and (informally) vivid narration of past events.',
      examples: ['Hablo español. (I speak Spanish — habit)', 'El tren sale a las ocho. (The train leaves at eight — scheduled near future)', 'Colón llega a América en 1492. (Colón arrives in America in 1492 — historical present, for effect)'],
      tip: 'Spoken Spanish often prefers "ir a + infinitivo" for near-future plans ("voy a salir"), but presente works too for scheduled/certain events.',
    },
    {
      name: 'Pretérito imperfecto', mood: 'Indicativo', tense: 'Indicativo pretérito imperfecto',
      when: 'Ongoing, habitual, or repeated past actions with no clear end — descriptions, background scenery, ages, times, weather, "used to" / "was -ing".',
      examples: ['Cuando era niño, jugaba al fútbol todos los días. (When I was a child, I used to play football every day)', 'Llovía mucho y hacía frío. (It was raining a lot and it was cold — background)'],
      tip: 'Quick test: can you replace the English verb with "was/were -ing" or "used to"? If yes, imperfecto.',
      vs: { tense: 'Pretérito perfecto simple', note: 'Imperfecto paints the ongoing background; indefinido names the one-off event that happens inside it. "Llovía (imperfecto) cuando salí (indefinido) de casa" — it was raining (ongoing) when I left (a single completed action).' },
    },
    {
      name: 'Pretérito perfecto simple', mood: 'Indicativo', tense: 'Indicativo pretérito perfecto simple',
      when: 'A completed action with a clear beginning and end at a specific point in the past — a one-off event, or a sequence of finished events.',
      examples: ['Ayer fui al cine. (Yesterday I went to the cinema — one finished event)', 'Nací en 1990. (I was born in 1990)'],
      tip: 'Also called pretérito or pretérito indefinido. If the action is a single, closed event rather than a background state, this is the one — not imperfecto.',
      vs: { tense: 'Pretérito perfecto compuesto', note: 'In Spain, indefinido is for closed time periods (ayer, el año pasado) while pretérito perfecto compuesto is for periods still open (hoy, esta semana). Many Latin American varieties use indefinido for both — "Hoy fui al gimnasio" is standard there, but is considered incorrect in Peninsular Spanish, which requires "Hoy he ido al gimnasio."' },
    },
    {
      name: 'Futuro', mood: 'Indicativo', tense: 'Indicativo futuro',
      when: 'Predictions and future actions, and conjecture/probability about the present.',
      examples: ['Iré a la fiesta. (I will go to the party)', '¿Qué hora será? (I wonder what time it is — conjecture about now, not the future)'],
      tip: 'Everyday speech often prefers "ir a + infinitivo" for near-future plans, saving futuro simple for more formal predictions, promises, or guesses.',
      vs: { tense: 'Condicional', note: 'Futuro states what will happen; condicional states what would happen. They share the same irregular stems: tendré/tendría, podré/podría, haré/haría.' },
    },
    {
      name: 'Condicional', mood: 'Condicional', tense: 'Condicional',
      when: 'Hypothetical actions ("would"), polite requests, and conjecture about the past.',
      examples: ['Me gustaría un café. (I would like a coffee — polite request)', 'Si tuviera tiempo, viajaría más. (If I had time, I would travel more)', 'Serían las tres cuando llegó. (It must have been three when he arrived — conjecture about the past)'],
      tip: 'Pairs with the imperfect subjunctive in "si" clauses: si + subjuntivo imperfecto, … + condicional.',
    },
    {
      name: 'Pretérito perfecto compuesto', mood: 'Indicativo', tense: 'Indicativo pretérito perfecto compuesto',
      when: 'A past action within a time period that\'s still open (today, this week, this year) or with present relevance/consequence — roughly like English present perfect.',
      examples: ['He comido ya. (I have already eaten)', 'Esta semana he trabajado mucho. (I\'ve worked a lot this week — the week isn\'t over)'],
      tip: 'In much of Latin America, indefinido often replaces this even within an open period ("Hoy comí" instead of "Hoy he comido"). Spain keeps the distinction strict in speech.',
    },
    {
      name: 'Pretérito pluscuamperfecto', mood: 'Indicativo', tense: 'Indicativo pretérito pluscuamperfecto',
      when: '"Had done" — an action completed before another point in the past.',
      examples: ['Cuando llegué, ella ya había salido. (When I arrived, she had already left)'],
      tip: 'Same logic as English past perfect: it sets up a "past before the past."',
    },
    {
      name: 'Pretérito anterior', mood: 'Indicativo', tense: 'Indicativo pretérito anterior',
      when: '"Had just done", immediately before another past action — formal/literary, right after time conjunctions like cuando, en cuanto, apenas.',
      examples: ['Apenas hubo terminado, se marchó. (As soon as he had finished, he left.)'],
      tip: 'Very rare in speech — pluscuamperfecto has replaced it almost everywhere except formal literary writing. Recognise it; you won\'t often need to produce it.',
    },
    {
      name: 'Futuro perfecto', mood: 'Indicativo', tense: 'Indicativo futuro perfecto',
      when: '"Will have done" by some future point, or conjecture about something already completed.',
      examples: ['Para las diez, habré terminado. (By ten, I will have finished)', 'Ya habrán llegado. (They must have arrived by now — conjecture)'],
    },
    {
      name: 'Condicional perfecto', mood: 'Condicional', tense: 'Condicional perfecto',
      when: '"Would have done" — the hypothetical past, as the result clause of "si + pluscuamperfecto de subjuntivo".',
      examples: ['Si hubiera sabido, habría venido. (If I had known, I would have come)'],
      tip: 'The classic past-hypothetical pair: "Si + hubiera + participio, … habría + participio" — "if X had happened, Y would have happened."',
      vs: { tense: 'Subjuntivo pretérito pluscuamperfecto', note: 'This is the "then" half of the hypothetical-past sentence; subjuntivo pretérito pluscuamperfecto is the "if" half.' },
    },

    // ── Subjuntivo ──────────────────────────────────────────────────────────────
    {
      name: 'Subjuntivo presente', mood: 'Subjuntivo', tense: 'Subjuntivo presente',
      when: 'After W.E.I.R.D.O. triggers (see the mood guide above) when the main clause is present or future.',
      examples: ['Quiero que estudies. (I want you to study)', 'Es importante que lleguemos a tiempo. (It\'s important that we arrive on time)'],
    },
    {
      name: 'Subjuntivo pretérito imperfecto', mood: 'Subjuntivo', tense: 'Subjuntivo pretérito imperfecto',
      when: 'Same W.E.I.R.D.O. triggers as subjuntivo presente, but with a past or conditional main clause — plus "si" clauses for hypotheticals contrary to fact.',
      examples: ['Quería que estudiaras. (I wanted you to study)', 'Si tuviera dinero, viajaría. (If I had money, I would travel)', 'Ojalá pudiera ayudarte. (I wish I could help you)'],
      tip: 'Two spellings exist for every form and are fully interchangeable: -ra (hablara, more common) and -se (hablase, more literary/formal).',
    },
    {
      name: 'Subjuntivo futuro', mood: 'Subjuntivo', tense: 'Subjuntivo futuro',
      when: 'Archaic — survives only in legal/formal language and a handful of fixed expressions.',
      examples: ['Sea lo que fuere. (Be that as it may.)', 'Adonde fueres, haz lo que vieres. (When in Rome... — proverb)'],
      tip: 'For recognition only — modern speech uses subjuntivo presente instead. You\'ll basically never need to produce this.',
    },
    {
      name: 'Subjuntivo pretérito perfecto', mood: 'Subjuntivo', tense: 'Subjuntivo pretérito perfecto',
      when: 'Like a present-perfect version of subjuntivo presente — a completed action, viewed subjectively, with present relevance.',
      examples: ['Espero que hayas dormido bien. (I hope you\'ve slept well)', 'No creo que haya llegado todavía. (I don\'t think he\'s arrived yet)'],
    },
    {
      name: 'Subjuntivo pretérito pluscuamperfecto', mood: 'Subjuntivo', tense: 'Subjuntivo pretérito pluscuamperfecto',
      when: 'The hypothetical past — "si" clauses about things that didn\'t happen, and "ojalá" about missed chances.',
      examples: ['Si hubiera estudiado, habría aprobado. (If I had studied, I would have passed)', 'Ojalá hubieras venido a la fiesta. (I wish you had come to the party)'],
      tip: 'Same -ra/-se alternation as the imperfect subjunctive: hubiera/hubiese, both correct.',
      vs: { tense: 'Condicional perfecto', note: 'This is the "if" half of the hypothetical-past sentence; condicional perfecto is the "then" half.' },
    },
    {
      name: 'Subjuntivo futuro perfecto', mood: 'Subjuntivo', tense: 'Subjuntivo futuro perfecto',
      when: 'Archaic, like subjuntivo futuro — legal/literary language only.',
      examples: ['Si para entonces no hubiere llegado… (If by then he shall not have arrived…)'],
      tip: 'Purely for recognition — essentially never used today.',
    },

    // ── Imperativo ──────────────────────────────────────────────────────────────
    {
      name: 'Imperativo afirmativo', mood: 'Imperativo', tense: 'Imperativo',
      when: 'Direct positive commands, each person with its own dedicated form.',
      examples: ['¡Habla! (Speak! — tú)', '¡Hablad! (Speak! — vosotros)', '¡Hablemos! (Let\'s speak! — nosotros)'],
      vs: { tense: 'Imperativo negativo', note: 'Affirmative uses genuine imperative forms for tú/vosotros; negative always borrows subjuntivo presente instead, for every person.' },
    },
    {
      name: 'Imperativo negativo', mood: 'Imperativo', tense: 'Imperativo non',
      when: 'Direct negative commands ("don\'t do X") — always built from the present subjunctive, for every person, tú and vosotros included.',
      examples: ['¡No hables tan alto! (Don\'t speak so loud!)', '¡No comáis eso! (Don\'t eat that!)'],
      tip: 'This is why "habla" (affirmative, tú) becomes "no hables" (negative) — the whole form switches to subjuntivo presente, not just "no" + the affirmative form.',
    },

    // ── Other: non-personal forms (no subject, one form regardless of person) ──
    {
      name: 'Gerundio', mood: 'Gerundio', tense: 'Gerundio',
      when: 'The "-ing" form — with estar for progressive actions ("estoy hablando"), or alone for simultaneous/manner actions.',
      examples: ['Estoy hablando por teléfono. (I\'m talking on the phone)', 'Trabajando, aprendo. (By working, I learn)'],
    },
    {
      name: 'Infinitivo', mood: 'Infinitivo', tense: 'Infinitivo',
      when: 'The dictionary form — after prepositions, as a verbal noun, and in verb periphrases.',
      examples: ['Antes de salir, cierra la puerta. (Before leaving, close the door)', 'Fumar es malo. (Smoking is bad)', 'Voy a comer. (I\'m going to eat)'],
    },
    {
      name: 'Participio', mood: 'Participo', tense: 'Participo',
      when: 'The "-ed/-en" form — with haber for every compound tense, and with ser for the passive voice.',
      examples: ['He hablado. (I have spoken)', 'Fue escrito por ella. (It was written by her — passive)'],
      tip: 'Shown here in its base (masculine singular) form; it agrees in gender/number only in the passive voice and a few fixed constructions, not in ordinary compound tenses.',
    },
  ],
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
  const moodGuides = MOOD_GUIDES[language] || []
  const sections = groupTensesBySection(language, tenses)

  const systemPrompt = `You are a helpful language teacher specialising in ${language} grammar.
Answer questions clearly and concisely, always providing examples in ${language} with translations.`

  return (
    <div>
      {moodGuides.length > 0 && (
        <div style={s.moodGuides}>
          <h3 style={s.moodGuidesTitle}>Moods at a glance</h3>
          <div style={s.moodGrid}>
            {moodGuides.map(g => (
              <div key={g.mood} style={{ ...s.moodCard, borderLeftColor: g.accent }}>
                <p style={{ ...s.moodName, color: g.accent }}>{g.mood}</p>
                <p style={s.moodSummary}>{g.summary}</p>
                <p style={s.moodWhen}>{g.when}</p>
                {g.triggers && (
                  <div style={s.triggerRow}>
                    {g.triggers.map(t => <span key={t} style={s.triggerChip}>{t}</span>)}
                  </div>
                )}
                <div style={s.moodExamples}>
                  {g.examples.map(ex => <p key={ex} style={s.example}>{ex}</p>)}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {sections.map(({ section, tenses: sectionTenses }) => (
        <div key={section} style={s.section}>
          <h4 style={s.sectionTitle}>{section}</h4>
          <div style={s.grid}>
            {sectionTenses.map(t => {
              const entry = tenses.find(e => e.mood === t.mood && e.tense === t.tense)
              if (!entry) return null
              const key = `${t.mood}||${t.tense}`
              const isOpen = open === key
              return (
                <div key={key} style={s.card} onClick={() => setOpen(isOpen ? null : key)}>
                  <div style={s.cardHeader}>
                    <span style={s.tenseName}>{entry.name || tenseLabel(language, t.mood, t.tense)}</span>
                    <span style={s.arrow}>{isOpen ? '▲' : '▼'}</span>
                  </div>
                  <p style={s.preview}>{entry.when}</p>
                  {isOpen && (
                    <div style={s.detail}>
                      <div style={s.examples}>
                        {entry.examples.map((ex, j) => (
                          <p key={j} style={s.example}>{ex}</p>
                        ))}
                      </div>
                      {entry.tip && <p style={s.tip}>💡 {entry.tip}</p>}
                      {entry.vs && (
                        <p style={s.vsBox}>
                          <strong>⚖️ vs {entry.vs.tense}:</strong> {entry.vs.note}
                        </p>
                      )}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      ))}

      <div style={{ marginTop: '2rem' }}>
        <h3 style={s.chatTitle}>Chat with the AI about any tense</h3>
        <ChatPanel
          systemPrompt={systemPrompt}
          placeholder={`Ask about ${language} tenses, conjugation rules, exceptions…`}
          language={language}
        />
      </div>
    </div>
  )
}

const s = {
  moodGuides: { marginBottom: '2rem' },
  moodGuidesTitle: { fontSize: '1.05rem', fontWeight: 700, color: '#1e1b4b', marginBottom: '0.75rem' },
  moodGrid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '0.85rem' },
  moodCard: { background: '#f8f9fa', border: '1px solid #e5e7eb', borderLeft: '4px solid', borderRadius: 10, padding: '1rem 1.1rem' },
  moodName: { margin: '0 0 0.35rem', fontWeight: 700, fontSize: '0.95rem', textTransform: 'uppercase', letterSpacing: '0.03em' },
  moodSummary: { margin: '0 0 0.5rem', fontSize: '0.9rem', fontWeight: 600, color: '#374151' },
  moodWhen: { margin: '0 0 0.6rem', fontSize: '0.87rem', color: '#4b5563', lineHeight: 1.5 },
  triggerRow: { display: 'flex', flexWrap: 'wrap', gap: '0.35rem', marginBottom: '0.6rem' },
  triggerChip: { fontSize: '0.75rem', color: '#4f46e5', background: '#eef2ff', padding: '0.15rem 0.5rem', borderRadius: 10 },
  moodExamples: { display: 'flex', flexDirection: 'column', gap: '0.2rem' },
  section: { marginBottom: '1.5rem' },
  sectionTitle: { fontSize: '0.85rem', fontWeight: 700, color: '#4f46e5', textTransform: 'uppercase', letterSpacing: '0.04em', borderBottom: '2px solid #e0e7ff', paddingBottom: '0.3rem', marginBottom: '0.75rem' },
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
  vsBox: { margin: '0.6rem 0 0', fontSize: '0.88rem', background: '#fff7ed', color: '#9a3412', padding: '0.5rem 0.75rem', borderRadius: 6, lineHeight: 1.5 },
  chatTitle: { fontSize: '1rem', fontWeight: 600, marginBottom: '0.75rem', color: '#374151' },
}
