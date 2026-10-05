/**
 * Parseur du corps `df-conversation` — TROIS formats d'entrée, détectés
 * automatiquement (surchargeable par l'attribut `format`) :
 *
 * 1. `records` (canonique)   : `Interlocuteur | message`, une ligne par message.
 * 2. `transcript`            : en-tête `Interlocuteur • 0:32 \` puis le texte
 *    sur les lignes suivantes (export d'outils de transcription).
 * 3. `vtt` (WebVTT, Teams)   : cues `hh:mm:ss.mmm --> …` + `<v Nom>texte</v>` ;
 *    les cues consécutives du même interlocuteur fusionnent en un message.
 */
import { parseRecords } from './records'

export interface ConversationMessage {
  speaker: string
  text: string
  /** Horodatage du début de prise de parole, si le format en fournit. */
  time?: string
}

export interface ParsedConversation {
  messages: ConversationMessage[]
  ignored: number
  format: 'records' | 'transcript' | 'vtt'
}

// `Nom • 0:32` (backslash de fin de ligne toléré — copies markdown).
const TRANSCRIPT_HEAD = /^(.+?)\s*[•·]\s*([\d:]+)\s*\\?\s*$/

// Ligne de timing WebVTT complète (`00:00:03.400 --> 00:00:06.000`) — un
// simple `-->` dans un message ne suffit pas à basculer en vtt.
const VTT_TIMING = /^[\d:.]+\s+-->\s+[\d:.]+/

export function detectFormat(body: string): ParsedConversation['format'] {
  const lines = body.split('\n').map((l) => l.trim())
  if (lines.some((l) => l.toUpperCase().startsWith('WEBVTT') || VTT_TIMING.test(l))) {
    return 'vtt'
  }
  if (lines.some((l) => TRANSCRIPT_HEAD.test(l))) return 'transcript'
  return 'records'
}

function parseRecordsFormat(body: string): ParsedConversation {
  const records = parseRecords(body, { fields: 2 })
  const messages: ConversationMessage[] = []
  let ignored = 0
  for (const row of records.rows) {
    const [speaker, text] = [row[0] ?? '', row[1] ?? '']
    if (speaker.trim() && text.trim()) messages.push({ speaker: speaker.trim(), text: text.trim() })
    else ignored++
  }
  return { messages, ignored, format: 'records' }
}

function parseTranscript(body: string): ParsedConversation {
  const messages: ConversationMessage[] = []
  let ignored = 0
  let current: ConversationMessage | null = null
  for (const raw of body.split('\n')) {
    const line = raw.trim()
    const head = TRANSCRIPT_HEAD.exec(line)
    if (head) {
      if (current) messages.push(current)
      current = { speaker: head[1].trim(), text: '', time: head[2] }
    } else if (line) {
      if (current) current.text += (current.text ? '\n' : '') + line
      else ignored++ // texte avant tout en-tête d'interlocuteur
    }
  }
  if (current) messages.push(current)
  const kept = messages.filter((m) => m.text.trim())
  ignored += messages.length - kept.length
  return { messages: kept, ignored, format: 'transcript' }
}

/** `00:01:23.456` → `1:23` (les heures n'apparaissent que si non nulles). */
function vttTime(t: string): string {
  const m = /^(\d+):(\d+):(\d+)/.exec(t)
  if (!m) return t
  const [h, min, s] = [Number(m[1]), m[2], m[3]]
  return h > 0 ? `${h}:${min}:${s}` : `${Number(min)}:${s}`
}

const VTT_VOICE = /<v\s+([^>]+)>/i

function parseVtt(body: string): ParsedConversation {
  const messages: ConversationMessage[] = []
  let ignored = 0
  let cueTime: string | null = null
  // Une cue = ligne de timing puis texte, terminée par une ligne vide. Hors
  // cue, les lignes (identifiants Teams, en-tête WEBVTT, NOTE) sont ignorées.
  let inCue = false
  for (const raw of body.split('\n')) {
    const line = raw.trim()
    if (!line) { inCue = false; continue }
    if (line.toUpperCase().startsWith('WEBVTT') || line.startsWith('NOTE')) continue
    const arrow = /^([\d:.]+)\s+-->\s/.exec(line)
    if (arrow) { cueTime = vttTime(arrow[1]); inCue = true; continue }
    if (!inCue) continue
    const voice = VTT_VOICE.exec(line)
    const text = line.replace(/<\/?v[^>]*>/gi, '').trim()
    if (!text) continue
    if (voice) {
      const speaker = voice[1].trim()
      const prev = messages[messages.length - 1]
      // Fusion des cues consécutives du même interlocuteur.
      if (prev && prev.speaker === speaker) prev.text += ' ' + text
      else messages.push({ speaker, text, time: cueTime ?? undefined })
    } else if (messages.length > 0) {
      messages[messages.length - 1].text += ' ' + text
    } else {
      ignored++
    }
  }
  return { messages, ignored, format: 'vtt' }
}

export function parseConversation(
  body: string,
  format?: string,
): ParsedConversation {
  const f = format === 'records' || format === 'transcript' || format === 'vtt'
    ? format
    : detectFormat(body)
  if (f === 'vtt') return parseVtt(body)
  if (f === 'transcript') return parseTranscript(body)
  return parseRecordsFormat(body)
}
