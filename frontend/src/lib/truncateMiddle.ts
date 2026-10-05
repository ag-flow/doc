/** Tronque en son MILIEU (et non à la fin) : sur un titre long, la fin porte
 *  souvent la partie distinctive (« … — v2 », « … (archivé) »). Jamais de
 *  retour à la ligne dans le fil d'Ariane, donc on coupe. */
export function truncateMiddle(text: string, max = 34, ellipsis = '…'): string {
  if (max <= ellipsis.length) return ellipsis
  if (text.length <= max) return text
  const keep = max - ellipsis.length
  const head = Math.ceil(keep / 2)
  const tail = keep - head
  return text.slice(0, head) + ellipsis + (tail > 0 ? text.slice(-tail) : '')
}
