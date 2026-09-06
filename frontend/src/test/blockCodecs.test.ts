import { describe, it, expect } from 'vitest'
import {
  registry,
  parseMarkdownWithCodecs,
  serializeMarkdownWithCodecs,
  type CodecEditorApi,
} from '../lib/blockCodecs'
import { maquetteCodec } from '../lib/blockCodecs/maquette'

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
  dfDiagram: {
    attrs: ' type="layers"',
    body: 'Présentation | UI\nMétier | logique',
  },
  dfConversation: {
    attrs: ' title="Point CRM" me="Alice"',
    body: 'Alice | On livre vendredi ?\nBob | Oui, si la recette passe jeudi.',
  },
  dfDisplay: {
    fence: 'df-display',
    attrs: ' title="Comparatif"',
    body: '[{"id": "root", "component": "Text", "text": "Hello", "hint": "h2"}]',
  },
  artifactChip: { id: UUID, label: 'Rapport.pdf' },
  dfMaquette: {
    artifactId: UUID,
    titre: 'Écran de connexion',
    viewport: 'mobile',
    hauteur: '640',
    description: 'Formulaire email + mot de passe',
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

describe('frontière après le nom de fence df-* (pas de préfixe partiel)', () => {
  it.each([
    ['```df-diagramme\nRacine\n```\n', 'dfDiagram'],
    ['```df-chart2\nA | 1\n```\n', 'dfChart'],
    ['```df-timelinex\nA | b\n```\n', 'dfTimeline'],
    ['```df-conversationnel\nA | b\n```\n', 'dfConversation'],
  ])('une fence dont le nom continue après le codec (%s) reste un bloc de code intact', async (md, type) => {
    const blocks = await parseMarkdownWithCodecs(makeEditor(), md)
    expect(blocks.some((b) => (b as { type?: string }).type === type)).toBe(false)
    const out = await serializeMarkdownWithCodecs(makeEditor(blocks as CodecEditorApi['document']))
    expect(out).toBe(md)
  })
})

describe('alias ```display (A2UI)', () => {
  const JSON_BODY = '[{"id": "root", "component": "Text", "text": "Hi"}]'

  it('corps JSON valide → revendiqué, fence d’origine préservée au round-trip', async () => {
    const md = '```display\n' + JSON_BODY + '\n```\n'
    const blocks = await parseMarkdownWithCodecs(makeEditor(), md)
    const block = blocks.find((b) => (b as { type?: string }).type === 'dfDisplay') as {
      props: { fence: string; body: string }
    }
    expect(block).toBeDefined()
    expect(block.props.fence).toBe('display')
    const out = await serializeMarkdownWithCodecs(makeEditor(blocks as CodecEditorApi['document']))
    expect(out).toBe(md)
  })

  it('corps non-JSON → écarté : reste un bloc de code ordinaire, intact', async () => {
    const md = '```display\nconst x = 1;\n```\n'
    const blocks = await parseMarkdownWithCodecs(makeEditor(), md)
    expect(blocks.some((b) => (b as { type?: string }).type === 'dfDisplay')).toBe(false)
    const out = await serializeMarkdownWithCodecs(makeEditor(blocks as CodecEditorApi['document']))
    expect(out).toBe(md)
  })

  it('```df-display revendique même un JSON cassé (intention explicite, dégradation au rendu)', async () => {
    const md = '```df-display\n{oops\n```\n'
    const blocks = await parseMarkdownWithCodecs(makeEditor(), md)
    expect(blocks.some((b) => (b as { type?: string }).type === 'dfDisplay')).toBe(true)
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

describe('puce artefact [](artifact://id)', () => {
  it('lien seul sur sa ligne → bloc artifactChip', async () => {
    const md = `Intro\n\n[Rapport.pdf](artifact://${UUID})\n\nSuite`
    const blocks = await parseMarkdownWithCodecs(makeEditor(), md)
    const chip = blocks.find((b) => (b as { type?: string }).type === 'artifactChip') as {
      props: { id: string; label: string }
    }
    expect(chip).toBeDefined()
    expect(chip.props.id).toBe(UUID)
    expect(chip.props.label).toBe('Rapport.pdf')
  })

  it('label vide accepté (retombe sur le nom de fichier au rendu)', async () => {
    const md = `[](artifact://${UUID})`
    const blocks = await parseMarkdownWithCodecs(makeEditor(), md)
    const chip = blocks.find((b) => (b as { type?: string }).type === 'artifactChip') as {
      props: { label: string }
    }
    expect(chip).toBeDefined()
    expect(chip.props.label).toBe('')
  })

  it('lien au fil du texte → PAS de puce (reste un lien inline)', async () => {
    const md = `Voir [le fichier](artifact://${UUID}) pour la suite.`
    const blocks = await parseMarkdownWithCodecs(makeEditor(), md)
    expect(blocks.some((b) => (b as { type?: string }).type === 'artifactChip')).toBe(false)
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

describe('maquette', () => {
  const UUID2 = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'

  it('sérialise l’artifactId en artifact:// dans le corps (compté au refcount)', () => {
    const md = maquetteCodec.toMarkdown({
      artifactId: UUID2,
      titre: 'X',
      viewport: 'desktop',
      hauteur: '',
      description: 'desc',
    } as unknown as Parameters<typeof maquetteCodec.toMarkdown>[0])
    expect(md).toContain(`artifact://${UUID2}`)
    expect(md).toContain('df-maquette')
  })

  it('une fence df-maquette sans artifact:// n’est PAS revendiquée', async () => {
    const md = '```df-maquette viewport="desktop"\nrien ici\n```\n'
    const blocks = await parseMarkdownWithCodecs(makeEditor(), md)
    expect(blocks.some((b) => (b as { type?: string }).type === 'dfMaquette')).toBe(false)
  })
})
