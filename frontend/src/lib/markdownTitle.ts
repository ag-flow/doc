/** Retire un « # <titre> » de tête strictement égal au titre du document —
 *  le shell (lecture, impression) affiche déjà ce titre, on ne le double pas.
 *  Même règle que l'export serveur (backend export/pdf.py). */
export function stripTitleHeading(content: string, title: string): string {
  const m = /^\s*#\s+(.+?)\s*\n/.exec(content)
  if (m && m[1].trim() === title.trim()) {
    return content.slice(m.index + m[0].length).replace(/^\s*\n/, '')
  }
  return content
}
