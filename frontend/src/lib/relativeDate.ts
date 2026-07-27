const MINUTE = 60_000
const HOUR = 60 * MINUTE
const DAY = 24 * HOUR

/** Date d'activité en français, à la granularité utile : « il y a 3 h »,
 *  « hier », puis la date courte au-delà d'une semaine. `now` est injectable
 *  pour que le rendu soit testable sans geler l'horloge. */
export function relativeDate(iso: string, now: Date = new Date()): string {
  const then = new Date(iso)
  const diff = now.getTime() - then.getTime()
  if (Number.isNaN(diff)) return ''
  if (diff < MINUTE) return "à l'instant"
  if (diff < HOUR) return `il y a ${Math.floor(diff / MINUTE)} min`
  if (diff < DAY) return `il y a ${Math.floor(diff / HOUR)} h`
  if (diff < 2 * DAY) return 'hier'
  if (diff < 7 * DAY) return `il y a ${Math.floor(diff / DAY)} j`
  return then.toLocaleDateString('fr-FR', { day: 'numeric', month: 'short', year: 'numeric' })
}
