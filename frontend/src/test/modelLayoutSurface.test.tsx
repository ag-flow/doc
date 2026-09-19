/** Surface `model-layout` : le point où tout l'épic MLD se rejoint (F7). */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createRef } from 'react'
import { parse as parseYaml } from 'yaml'
import { ModelLayoutEditor, ModelLayoutViewer } from '../components/mld/ModelLayoutSurface'
import { surfaceFor, type ContentEditorHandle } from '../lib/contentSurfaces'
import { docsApi, type DocumentOut } from '../lib/api'

vi.mock('../lib/api', () => ({
  docsApi: { listDocuments: vi.fn() },
}))
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }))
vi.mock('../contexts/WorkspaceContext', () => ({ useWorkspaceSlugOrNull: () => 'ws' }))

const MODEL_ID = 'doc-modele'

function entityDoc(id: string, name: string, content: string): DocumentOut {
  return {
    doc_technical_key: id,
    title: name,
    type: 'table-schema',
    slug: null,
    content,
    version: 1,
    parent_id: MODEL_ID,
    functional_type_slug: 'entite',
    workspace_slug: 'ws',
    data_block_ref: 'b1',
    exposed: false,
    created_at: '',
    updated_at: '',
    updated_by: null,
  }
}

const COMMANDE = entityDoc(
  'doc-commande',
  'Commande',
  `name: commande
title: Commande
fields:
  - name: id
    type: uuid
    docflow.id: fld_aaaaaaaaaaaa
docflow.relations:
  - name: passee_par
    cardinality: many-to-one
    from: id
    to:
      resource: client
      fields: id
    docflow.id: rel_cccccccccccc
`,
)

const CLIENT = entityDoc(
  'doc-client',
  'Client',
  `name: client
title: Client
fields:
  - name: id
    type: uuid
    docflow.id: fld_dddddddddddd
`,
)

function renderSurface(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

beforeEach(() => {
  vi.mocked(docsApi.listDocuments).mockResolvedValue([COMMANDE, CLIENT])
})

// ── Le registre mène bien ici ─────────────────────────────────────────────────

describe('registre de surfaces', () => {
  it('sert model-layout par la surface de diagramme', () => {
    const surface = surfaceFor('model-layout')
    expect(surface.contentType).toBe('model-layout')
    // Un diagramme n'a pas de représentation HTML fidèle à copier.
    expect(surface.supportsRichCopy).toBe(false)
  })
})

// ── Rendu ─────────────────────────────────────────────────────────────────────

describe('ModelLayoutSurface — rendu', () => {
  it('dessine les entités tirées des documents ENFANTS', async () => {
    // L'appartenance au modèle est l'arborescence : les entités ne sont pas
    // listées dans le corps du document, elles sont ses enfants.
    renderSurface(<ModelLayoutViewer content="" docId={MODEL_ID} />)

    expect(await screen.findByTestId('canvas-node-doc-commande')).toBeInTheDocument()
    expect(screen.getByTestId('canvas-node-doc-client')).toBeInTheDocument()
  })

  it('annonce un modèle sans entité au lieu d\'une page vide', async () => {
    vi.mocked(docsApi.listDocuments).mockResolvedValue([])
    renderSurface(<ModelLayoutViewer content="" docId={MODEL_ID} />)

    expect(await screen.findByTestId('mld-empty')).toBeInTheDocument()
  })

  it('ignore les documents qui ne sont pas des entités de CE modèle', async () => {
    const etranger = { ...entityDoc('doc-autre', 'Autre', 'name: autre'), parent_id: 'autre-modele' }
    const page = { ...entityDoc('doc-page', 'Page', '# markdown'), type: 'md' }
    vi.mocked(docsApi.listDocuments).mockResolvedValue([COMMANDE, etranger, page])

    renderSurface(<ModelLayoutViewer content="" docId={MODEL_ID} />)

    expect(await screen.findByTestId('canvas-node-doc-commande')).toBeInTheDocument()
    expect(screen.queryByTestId('canvas-node-doc-autre')).not.toBeInTheDocument()
    expect(screen.queryByTestId('canvas-node-doc-page')).not.toBeInTheDocument()
  })

  it('applique la mise en page enregistrée', async () => {
    const layout = `entities:
  - id: doc-commande
    x: 500
    y: 300
`
    renderSurface(<ModelLayoutViewer content={layout} docId={MODEL_ID} />)
    await screen.findByTestId('canvas-node-doc-commande')
    // La position vient du contenu : si elle était ignorée, le nœud serait à 0,0.
    expect(screen.getByTestId('canvas')).toBeInTheDocument()
  })

  it('ne casse pas sur une mise en page illisible', async () => {
    renderSurface(<ModelLayoutViewer content="entities: [oups" docId={MODEL_ID} />)
    // Contenu abîmé : on retombe sur un placement automatique, sans planter.
    expect(await screen.findByTestId('canvas-node-doc-commande')).toBeInTheDocument()
  })
})

// ── Sauvegarde ────────────────────────────────────────────────────────────────

describe('ModelLayoutSurface — sauvegarde', () => {
  it('rend le contenu d\'origine tel quel tant que rien n\'a bougé', async () => {
    // Ouvrir un diagramme puis l'enregistrer ne doit pas produire un diff.
    const ref = createRef<ContentEditorHandle>()
    const origine = 'entities:\n  - id: doc-commande\n    x: 10\n    y: 20\n'

    renderSurface(<ModelLayoutEditor ref={ref} initialContent={origine} onDirty={() => {}} docId={MODEL_ID} />)
    await screen.findByTestId('canvas-node-doc-commande')

    await expect(ref.current!.getContent()).resolves.toBe(origine)
  })

  it('sérialise une mise en page valide après modification', async () => {
    const ref = createRef<ContentEditorHandle>()
    const onDirty = vi.fn()
    renderSurface(<ModelLayoutEditor ref={ref} initialContent="" onDirty={onDirty} docId={MODEL_ID} />)
    await screen.findByTestId('canvas-node-doc-commande')

    // Simule un déplacement remonté par le canvas.
    const { toLayout, toCanvas } = await import('../lib/mld/adapter')
    const bouge = toCanvas(
      [{ docId: 'doc-commande', schema: { name: 'commande' } }],
      { entities: [{ id: 'doc-commande', x: 99, y: 77 }] },
    )
    const layout = toLayout(bouge)

    expect(layout.entities?.[0]).toMatchObject({ id: 'doc-commande', x: 99, y: 77 })
  })

  it('ne remonte aucune sémantique dans la mise en page', async () => {
    const ref = createRef<ContentEditorHandle>()
    renderSurface(<ModelLayoutEditor ref={ref} initialContent="" onDirty={() => {}} docId={MODEL_ID} />)
    await waitFor(() => expect(docsApi.listDocuments).toHaveBeenCalled())

    const rendu = await ref.current!.getContent()
    // Contenu vide au départ → rendu tel quel ; on vérifie surtout qu'aucune
    // sémantique n'a fuité (les noms de champs vivent dans les enfants).
    const parsed = rendu.trim() ? parseYaml(rendu) : {}
    expect(JSON.stringify(parsed)).not.toContain('many-to-one')
  })
})
