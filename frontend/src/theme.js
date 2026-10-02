// Design tokens and the shared building blocks every page uses, so buttons,
// chips, cards and headings look the same everywhere. Pages still keep their
// own `const s = {...}` for layout; spread these in for the common pieces.

export const color = {
  primary: '#4f46e5',
  primarySoft: '#eef2ff',
  primaryBorder: '#c7d2fe',
  ink: '#1e1b4b',        // headings
  text: '#1f2937',
  body: '#374151',
  muted: '#6b7280',
  faint: '#9ca3af',
  border: '#e5e7eb',
  borderStrong: '#d1d5db',
  surface: '#f8f9fa',    // cards and panels
  bg: '#ffffff',
  success: '#15803d',
  successSoft: '#dcfce7',
  warning: '#92400e',
  warningSoft: '#fef3c7',
  danger: '#b91c1c',
  dangerSoft: '#fee2e2',
}

export const radius = { sm: 8, md: 12, lg: 16, pill: 999 }

export const font = "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif"

// Borders are always written as longhands: mixing `border` with a `borderColor`
// override (e.g. a chip turning active) makes React warn and can leave stale styles.
const outline = c => ({ borderWidth: 1, borderStyle: 'solid', borderColor: c })

const button = {
  borderRadius: radius.sm,
  padding: '0.6rem 1.1rem',
  fontSize: '0.95rem',
  lineHeight: 1.2,
  cursor: 'pointer',
  fontFamily: 'inherit',
  whiteSpace: 'nowrap',
}

export const ui = {
  // 16px side gutter so nothing touches the edge on a phone
  page: { maxWidth: 820, margin: '0 auto', padding: '1.75rem 1rem 3rem', fontFamily: font },
  back: { background: 'none', border: 'none', color: color.muted, cursor: 'pointer', padding: 0, fontSize: '0.9rem', fontFamily: 'inherit' },
  h1: { fontSize: '1.7rem', fontWeight: 800, color: color.ink, margin: '0.75rem 0 1.25rem', lineHeight: 1.2 },
  h2: { fontSize: '1.05rem', fontWeight: 700, color: color.ink, margin: '0 0 0.75rem' },

  primary: { ...button, ...outline(color.primary), background: color.primary, color: '#fff', fontWeight: 600 },
  secondary: { ...button, ...outline(color.borderStrong), background: '#fff', color: color.body },
  link: { background: 'none', border: 'none', color: color.primary, cursor: 'pointer', padding: 0, fontSize: '0.88rem', fontFamily: 'inherit' },

  // Toggle buttons: spread chipOn over chip for the selected one
  chip: { ...outline(color.borderStrong), padding: '0.4rem 0.95rem', borderRadius: radius.pill, background: '#fff', color: color.body, cursor: 'pointer', fontSize: '0.88rem', fontFamily: 'inherit' },
  chipOn: { borderColor: color.primary, background: color.primary, color: '#fff' },
  // A quieter selected state, for tabs
  chipSoftOn: { borderColor: color.primary, background: color.primarySoft, color: color.primary, fontWeight: 600 },

  panel: { background: color.surface, borderRadius: radius.md, padding: '1.5rem' },
  // A clickable card (e.g. a menu tile)
  tile: { ...outline(color.border), display: 'flex', flexDirection: 'column', gap: '0.35rem', textAlign: 'left', background: '#fff', borderRadius: radius.md, padding: '1rem 1.1rem', cursor: 'pointer', fontFamily: 'inherit', color: color.text },

  muted: { color: color.muted },
  error: { color: color.danger },
}
