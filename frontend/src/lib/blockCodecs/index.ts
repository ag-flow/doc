/**
 * Registre de codecs de blocs custom (spec 39_MBC).
 *
 * Un composant d'éditeur = UNE entrée de registre (fichier dédié) : détection
 * markdown (pattern), conversion match → props (toBlock), sérialisation props
 * → markdown canonique (toMarkdown), spec BlockNote et item de menu slash.
 *
 * Le parsing est une passe unique ordonnée par position (plus d'empilement de
 * codecs ni d'ordre implicite), avec placeholders indexés à nonce aléatoire
 * (aucune collision possible avec le contenu utilisateur). BlockNote 0.51
 * n'expose pas de hook de parsing markdown par bloc custom : la technique du
 * placeholder reste nécessaire — centralisée ici, testée une fois pour toutes.
 *
 * La sérialisation est un lookup par type avec GARDE ANTI-PERTE : un bloc d'un
 * type ni par défaut ni enregistré fait échouer la sauvegarde (BlockNote le
 * sérialiserait silencieusement en vide).
 */

import type { ReactNode } from 'react'
import { BlockNoteSchema, defaultBlockSpecs } from '@blocknote/core'
import { mermaidCodec } from './mermaid'
import { datasetCodec } from './dataset'
import { timelineCodec } from './timeline'
import { chartCodec } from './chart'

// ── Contrat ───────────────────────────────────────────────────────────────────

/** Contexte fourni aux items de menu slash des codecs. */
export interface SlashContext {
  /** L'éditeur BlockNote (typé minimal — l'inférence générique du schéma custom diverge). */
  editor: {
    insertBlocks: (blocks: unknown[], referenceBlock: unknown, placement: 'before' | 'after') => void
    getTextCursorPosition: () => { block: unknown }
  }
  wsSlug: string
  t: (key: string) => string
}

export interface SlashItem {
  title: string
  subtext?: string
  onItemClick: () => void
  aliases?: string[]
  group?: string
  icon?: ReactNode
  key: string
}

export interface BlockCodec<P extends Record<string, unknown> = Record<string, unknown>> {
  /** Type du bloc BlockNote. Unique dans le registre. */
  type: string
  /** Détection dans le markdown. Regex GLOBALE. */
  pattern: RegExp
  /** Match markdown → props du bloc. `null` = match écarté. */
  toBlock: (match: RegExpExecArray) => P | null
  /** Props → markdown canonique. Doit être stable en round-trip. */
  toMarkdown: (props: P) => string
  /** La spec BlockNote (`createReactBlockSpec` appelé). */
  spec: () => unknown
  /** Entrée du menu `/`. Absente pour un codec legacy. */
  slashItem?: (ctx: SlashContext) => SlashItem
  /** Reconnu en lecture/écriture mais non proposé à l'insertion. */
  legacy?: boolean
}

// ── Registre ──────────────────────────────────────────────────────────────────
// Ajouter un composant = son fichier + une entrée ici. Ni l'éditeur, ni le
// viewer, ni le parseur, ni le sérialiseur ne changent.

// Cast via unknown : chaque codec est typé précisément (P concret) dans son
// fichier ; le registre l'expose sous le contrat générique.
export const registry: BlockCodec[] = [
  mermaidCodec as unknown as BlockCodec,
  datasetCodec as unknown as BlockCodec,
  timelineCodec as unknown as BlockCodec,
  chartCodec as unknown as BlockCodec,
]

const byType = new Map(registry.map((c) => [c.type, c]))

// ── Schéma unique (éditeur + viewer) ─────────────────────────────────────────

const customSpecs = Object.fromEntries(registry.map((c) => [c.type, c.spec()]))

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const docflowSchema = BlockNoteSchema.create({
  blockSpecs: { ...defaultBlockSpecs, ...(customSpecs as any) },
})

/** Items de menu slash dérivés du registre (codecs non-legacy avec item). */
export function slashItemsFromRegistry(ctx: SlashContext): SlashItem[] {
  return registry.filter((c) => c.slashItem && !c.legacy).map((c) => c.slashItem!(ctx))
}

// ── API éditeur minimale ─────────────────────────────────────────────────────

/** Sous-ensemble de l'API BlockNote utilisé par le moteur (cf. SlashContext). */
export interface CodecEditorApi {
  document: ReadonlyArray<{ type?: string; props?: Record<string, unknown> }>
  tryParseMarkdownToBlocks: (markdown: string) => Promise<unknown[]>
  blocksToMarkdownLossy: (blocks?: unknown[]) => Promise<string>
}

// ── Parsing : une passe, ordonnée par position ───────────────────────────────

interface Claim {
  start: number
  end: number
  codec: BlockCodec
  props: Record<string, unknown>
}

function collectClaims(markdown: string, codecs: readonly BlockCodec[]): Claim[] {
  const claims: Claim[] = []
  for (const codec of codecs) {
    // Regex globales : repartir d'un lastIndex neutre à chaque parsing.
    const re = new RegExp(codec.pattern.source, codec.pattern.flags)
    for (const match of markdown.matchAll(re)) {
      const props = codec.toBlock(match as RegExpExecArray)
      if (props === null || match.index === undefined) continue
      claims.push({ start: match.index, end: match.index + match[0].length, codec, props })
    }
  }
  // Tri par position ; en cas de chevauchement, le premier gagne (journalisé).
  claims.sort((a, b) => a.start - b.start || a.end - b.end)
  const kept: Claim[] = []
  for (const claim of claims) {
    const last = kept[kept.length - 1]
    if (last && claim.start < last.end) {
      console.warn(
        `[blockCodecs] chevauchement écarté : ${claim.codec.type}@${claim.start} sous ${last.codec.type}@${last.start}`,
      )
      continue
    }
    kept.push(claim)
  }
  return kept
}

function extractPlainText(block: unknown): string {
  if (typeof block !== 'object' || block === null) return ''
  const content = (block as { content?: unknown }).content
  if (!Array.isArray(content)) return ''
  return content
    .map((node) =>
      typeof node === 'object' && node !== null && 'text' in node
        ? String((node as { text: unknown }).text)
        : '',
    )
    .join('')
}

/**
 * Parse un markdown en blocs BlockNote : les fragments revendiqués par un codec
 * deviennent des blocs custom `{ type, props }`, le reste passe par BlockNote.
 * Une fence qu'aucun codec ne revendique reste un bloc de code intact.
 */
export async function parseMarkdownWithCodecs(
  editor: CodecEditorApi,
  markdown: string,
  codecs: readonly BlockCodec[] = registry,
): Promise<unknown[]> {
  const source = markdown ?? ''
  const claims = collectClaims(source, codecs)
  if (claims.length === 0) return editor.tryParseMarkdownToBlocks(source)

  // Nonce tiré à CHAQUE parsing : aucune séquence littérale du document ne
  // peut entrer en collision avec les placeholders.
  const nonce = Math.random().toString(36).slice(2, 10)
  const placeholder = (i: number) => `%%DF_${nonce}_${i}%%`
  const placeholderRe = new RegExp(`^%%DF_${nonce}_(\\d+)%%$`)

  let sanitized = ''
  let cursor = 0
  claims.forEach((claim, i) => {
    sanitized += source.slice(cursor, claim.start) + `\n${placeholder(i)}\n`
    cursor = claim.end
  })
  sanitized += source.slice(cursor)

  const blocks = await editor.tryParseMarkdownToBlocks(sanitized)

  const result: unknown[] = []
  for (const block of blocks) {
    const m = placeholderRe.exec(extractPlainText(block).trim())
    const claim = m ? claims[Number(m[1])] : undefined
    if (claim) {
      result.push({ type: claim.codec.type, props: claim.props })
    } else {
      result.push(block)
    }
  }
  return result
}

// ── Sérialisation : lookup par type + garde anti-perte ───────────────────────

const DEFAULT_BLOCK_TYPES = new Set(Object.keys(defaultBlockSpecs))

/**
 * Sérialise les blocs courants en markdown. Les blocs custom passent par le
 * `toMarkdown` de leur codec ; les blocs par défaut par BlockNote.
 *
 * GARDE ANTI-PERTE : un type ni par défaut ni enregistré lève une erreur
 * (sauvegarde interrompue) au lieu de produire du vide silencieusement.
 */
export async function serializeMarkdownWithCodecs(
  editor: CodecEditorApi,
  codecs: readonly BlockCodec[] = registry,
): Promise<string> {
  const lookup = codecs === registry ? byType : new Map(codecs.map((c) => [c.type, c]))
  const parts: string[] = []
  for (const block of editor.document) {
    const codec = block.type ? lookup.get(block.type) : undefined
    if (codec) {
      parts.push(codec.toMarkdown(block.props ?? {}))
      continue
    }
    if (block.type && !DEFAULT_BLOCK_TYPES.has(block.type)) {
      console.error('[blockCodecs] bloc de type inconnu, sauvegarde interrompue', block.type)
      throw new Error(
        `bloc de type inconnu « ${block.type} » : sauvegarde interrompue pour ne pas perdre de contenu`,
      )
    }
    const md = await editor.blocksToMarkdownLossy([block])
    parts.push(md.trimEnd())
  }
  return parts.filter((p) => p.length > 0).join('\n\n') + '\n'
}
