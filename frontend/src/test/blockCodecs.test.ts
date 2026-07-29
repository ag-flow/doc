import { describe, it, expect } from 'vitest'
import {
  registry,
  parseMarkdownWithCodecs,
  serializeMarkdownWithCodecs,
  type CodecEditorApi,
} from '../lib/blockCodecs'

const UUID = '11111111-2222-3333-4444-555555555555'

/** Éditeur factice : parse = un bloc paragraphe par « paragraphe » markdown
 *  (séparés par lignes vides) ; serialize = le texte brut. Suffit à exercer le
 *  moteur (placement des placeholders, réinjection, round-trip). */
function makeEditor(document: CodecEditorApi['document'] = []): CodecEditorApi {
  return {
    document,
    tryParseMarkdownToBlocks: async (md: string) =>
      md
        .split(/\n{2,}/)
        .map((chunk) => chunk.trim())
        .filter((chunk) => chunk.length > 0)
        .map((text) => ({ type: 'paragraph', content: [{ type: 'text', text }] })),
    blocksToMarkdownLossy: async (blocks?: unknown[]) => {
      const b = (blocks ?? [])[0] as { content?: { text?: string }[] } | undefined
      return b?.content?.map((n) => n.text ?? '').join('') ?? ''
    },
  }
}

// Props d'exemple par codec — le test échoue si un codec du registre n'a pas
// d'exemple : le prochain composant DOIT arriver avec le sien.
const SAMPLES: Record<string, Record<string, unknown>> = {
  mermaid: { source: 'graph TD\n  A-->B' },
  dataset: { datasetId: UUID },
  dfTimeline: {
    attrs: ' title="Plan d\'action"',
    body: 'Analyse | Récupérer la volumétrie.\nCadrage | Réunion jeudi.',
  },
  dfChart: {
    attrs: ' type="donut" title="Répartition" format="percent"',
    body: 'Fait | 60\nEn cours | 30\nÀ faire | 10',
  },
  dfConversation: {
    attrs: ' title="Point CRM" me="Alice"',
    body: 'Alice | On livre vendredi ?\nBob | Oui, si la recette passe jeudi.',
  },
}

describe('round-trip paramétré sur le registre', () => {
  it('chaque codec du registre a des props d’exemple', () => {
    for (const codec of registry) {
      expect(SAMPLES[codec.type], `SAMPLES manquant pour le codec « ${codec.type} »`).toBeDefined()
    }
  })

  it.each(registry.map((c) => [c.type, c] as const))(
    'markdown → blocs → markdown est idempotent pour « %s »',
    async (_type, codec) => {
      const props = SAMPLES[codec.type]
      const md = `Intro\n\n${codec.toMarkdown(props)}\n\nOutro\n`

      const blocks = await parseMarkdownWithCodecs(makeEditor(), md)
      const custom = blocks.find(
        (b) => (b as { type?: string }).type === codec.type,
      ) as { type: string; props: Record<string, unknown> } | undefined
      expect(custom).toBeDefined()
      expect(custom!.props).toEqual(props)

      const out = await serializeMarkdownWithCodecs(
        makeEditor(blocks as CodecEditorApi['document']),
      )
      expect(out).toBe(md)
    },
  )
})

describe('parsing', () => {
  it('jeton dataset:// → bloc dataset avec le bon id, texte alentour conservé', async () => {
    const blocks = await parseMarkdownWithCodecs(
      makeEditor(),
      `Intro\n\ndataset://${UUID}\n\nOutro`,
    )
    expect(blocks.length).toBe(3)
    expect((blocks[1] as { type?: string }).type).toBe('dataset')
    expect((blocks[1] as { props: { datasetId: string } }).props.datasetId).toBe(UUID)
  })

  it('markdown sans motif : passe intégralement par BlockNote', async () => {
    const blocks = await parseMarkdownWithCodecs(makeEditor(), 'Hello world')
    expect(blocks.every((b) => (b as { type?: string }).type === 'paragraph')).toBe(true)
  })

  it('chevauchement : un jeton dataset DANS une fence mermaid est écarté (le premier gagne)', async () => {
    const md = '```mermaid\ngraph TD\n  X[dataset://' + UUID + ']\n```\n'
    const blocks = await parseMarkdownWithCodecs(makeEditor(), md)
    const types = blocks.map((b) => (b as { type?: string }).type)
    expect(types).toContain('mermaid')
    expect(types).not.toContain('dataset')
    // La source mermaid contient toujours le jeton, intact.
    const mermaid = blocks.find((b) => (b as { type?: string }).type === 'mermaid') as {
      props: { source: string }
    }
    expect(mermaid.props.source).toContain(`dataset://${UUID}`)
  })

  it('fence inconnue : aucun codec ne la revendique, elle traverse intacte', async () => {
    const md = '```inconnu\nfoo bar\n```\n'
    const blocks = await parseMarkdownWithCodecs(makeEditor(), md)
    const out = await serializeMarkdownWithCodecs(makeEditor(blocks as CodecEditorApi['document']))
    expect(out).toBe(md)
  })
})

describe('sérialisation — garde anti-perte', () => {
  it('un bloc de type inconnu fait échouer la sauvegarde (pas de perte silencieuse)', async () => {
    const editor = makeEditor([
      { type: 'paragraph', content: [{ type: 'text', text: 'ok' }] } as never,
      { type: 'widget-non-enregistre', props: {} },
    ])
    await expect(serializeMarkdownWithCodecs(editor)).rejects.toThrow(/widget-non-enregistre/)
  })

  it('un bloc par défaut passe par BlockNote sans erreur', async () => {
    const editor = makeEditor([
      { type: 'paragraph', content: [{ type: 'text', text: 'texte' }] } as never,
    ])
    await expect(serializeMarkdownWithCodecs(editor)).resolves.toBe('texte\n')
  })
})

describe('non-régression : document combiné mermaid + dataset', () => {
  it('load + save → markdown identique au caractère près', async () => {
    const md =
      '# Titre\n\n' +
      '```mermaid\ngraph TD\n  A-->B\n```\n\n' +
      `dataset://${UUID}\n\n` +
      'Conclusion\n'
    const blocks = await parseMarkdownWithCodecs(makeEditor(), md)
    const out = await serializeMarkdownWithCodecs(makeEditor(blocks as CodecEditorApi['document']))
    expect(out).toBe(md)
  })
})
