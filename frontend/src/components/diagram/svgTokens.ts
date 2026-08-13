/** Références (chaînes) des tokens `--diagram-*` pour usage dans les attributs
 *  SVG (fill/stroke/font-family). Source unique : styles/tokens-diagram.css.
 *  Aucune primitive ne code un hex ni un nom de police en dur. */
export const DIAGRAM = {
  paper: 'var(--diagram-paper)',
  paper2: 'var(--diagram-paper-2)',
  ink: 'var(--diagram-ink)',
  muted: 'var(--diagram-muted)',
  accent: 'var(--diagram-accent)',
  hairlineColor: 'var(--diagram-hairline-color)',
  hairlineWidth: 'var(--diagram-hairline-width)',
  fontTitle: 'var(--diagram-font-title)',
  fontNode: 'var(--diagram-font-node)',
  fontMono: 'var(--diagram-font-mono)',
  radius: 'var(--diagram-radius)',
} as const
