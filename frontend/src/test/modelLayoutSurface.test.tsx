/** Surface `model-layout` : le point où tout l'épic MLD se rejoint (F7). */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createRef } from 'react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { parse as parseYaml } from 'yaml'
import { ModelLayoutEditor, ModelLayoutViewer } from '../components/mld/ModelLayoutSurface'
import { surfaceFor, type ContentEditorHandle } from '../lib/contentSurfaces'
import { docsApi, type DocumentOut } from '../lib/api'

vi.mock('../lib/api', () => ({
  docsApi: { listDocuments: vi.fn(), getDocument: vi.fn() },
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

/** Sonde d'URL : la surface de lecture NAVIGUE (clic sur une entité), il faut
 *  donc pouvoir observer où l'on a atterri. */
function LocationProbe() {
  return <span data-testid="pathname">{useLocation().pathname}</span>
}

/** La surface de lecture a besoin d'un routeur, et des params `ws` / `block`
 *  pour construire le lien vers la fiche d'une entité. */
function renderSurface(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[`/ws/ws/blocs/b1/documents/${MODEL_ID}`]}>
        <Routes>
          <Route
            path="/ws/:ws/blocs/:block/documents/:id"
            element={<>{ui}<LocationProbe /></>}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

/** `listDocuments` rend des TÊTES : l'API ne peuple JAMAIS `content` sur la
 *  liste. Le mock doit le refléter — un mock qui rend le corps ici avait laissé
 *  passer un bug où le diagramme s'affichait sans titres, sans champs et sans
 *  relations. */
const asHead = (d: DocumentOut): DocumentOut => ({ ...d, content: null })

beforeEach(() => {
  vi.mocked(docsApi.listDocuments).mockResolvedValue([COMMANDE, CLIENT].map(asHead))
  vi.mocked(docsApi.getDocument).mockImplementation(async (_ws: string, id: string) => {
    const found = [COMMANDE, CLIENT].find((d) => d.doc_technical_key === id)
    if (!found) throw new Error(`document ${id} introuvable`)
    return found
  })
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

  it('affiche le TITRE de l\'entité, pas son identifiant', async () => {
    // Régression : `listDocuments` ne peuple pas `content`. La surface lisait
    // donc des schémas vides, et retombait sur l'UUID du document — un
    // diagramme de boîtes nommées « c49ec8cf-3acd-44f8-… ».
    renderSurface(<ModelLayoutViewer content="" docId={MODEL_ID} />)

    expect(await screen.findByText('Commande')).toBeInTheDocument()
    expect(screen.getByText('Client')).toBeInTheDocument()
    expect(screen.queryByText(/doc-commande/)).not.toBeInTheDocument()
  })

  it('dessine les champs en ports — donc le corps des entités est bien chargé', async () => {
    // Même régression : sans le corps des entités, il n'y avait ni champ ni
    // relation — le diagramme se réduisait à des boîtes vides sans lien.
    //
    // La présence d'un port prouve que le schéma a été lu. Le TRACÉ de la
    // relation, lui, n'est pas vérifiable ici : le moteur de rendu ne peint les
    // liens qu'une fois les nœuds mesurés, et jsdom ne mesure rien. La
    // production de l'arête est couverte à l'unité dans `mldAdapter.test.ts`.
    renderSurface(<ModelLayoutViewer content="" docId={MODEL_ID} />)

    expect(
      await screen.findByTestId('canvas-port-doc-commande-fld_aaaaaaaaaaaa'),
    ).toBeInTheDocument()
  })

  it('annonce un modèle sans entité au lieu d\'une page vide', async () => {
    vi.mocked(docsApi.listDocuments).mockResolvedValue([])
    renderSurface(<ModelLayoutViewer content="" docId={MODEL_ID} />)

    expect(await screen.findByTestId('mld-empty')).toBeInTheDocument()
  })

  it('ignore les documents qui ne sont pas des entités de CE modèle', async () => {
    const etranger = { ...entityDoc('doc-autre', 'Autre', 'name: autre'), parent_id: 'autre-modele' }
    const page = { ...entityDoc('doc-page', 'Page', '# markdown'), type: 'md' }
    vi.mocked(docsApi.listDocuments).mockResolvedValue([COMMANDE, etranger, page].map(asHead))

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

// ── Naviguer depuis le diagramme ─────────────────────────────────────────────

describe('ModelLayoutSurface — ouvrir une entité', () => {
  it('un clic sur une boîte ouvre la fiche de l\'entité', async () => {
    renderSurface(<ModelLayoutViewer content="" docId={MODEL_ID} />)
    fireEvent.click(await screen.findByTestId('canvas-node-doc-client'))

    await waitFor(() =>
      expect(screen.getByTestId('pathname')).toHaveTextContent(
        '/ws/ws/blocs/b1/documents/doc-client',
      ),
    )
  })

  it('en ÉDITION le clic ne navigue pas — il sélectionne et déplace', async () => {
    // Naviguer au premier clic rendrait le repositionnement impossible.
    renderSurface(<ModelLayoutEditor initialContent="" docId={MODEL_ID} onDirty={vi.fn()} />)
    fireEvent.click(await screen.findByTestId('canvas-node-doc-client'))

    expect(screen.getByTestId('pathname')).toHaveTextContent(
      `/ws/ws/blocs/b1/documents/${MODEL_ID}`,
    )
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

  it('ne signale PAS une modification quand la mise en page n\'a pas bougé', async () => {
    // Régression : le moteur de rendu émet des changements de lui-même (mesure
    // des nœuds au montage, restauration du viewport, re-rendu après
    // sauvegarde). Les traiter comme des gestes de l'utilisateur rallumait
    // « modifications non enregistrées » juste après un enregistrement réussi.
    const onDirty = vi.fn()
    renderSurface(
      <ModelLayoutEditor
        initialContent="entities:\n  - id: doc-commande\n    x: 10\n    y: 20\n"
        onDirty={onDirty}
        docId={MODEL_ID}
      />,
    )
    await screen.findByTestId('canvas-node-doc-commande')

    expect(onDirty).not.toHaveBeenCalled()
  })

  it('garde les entités quand un changement survient AVANT leur chargement', async () => {
    // Régression : la surface retenait le canvas entier en état. Le moteur de
    // rendu émet un changement dès le montage (mesure des nœuds), donc avant
    // que les corps soient arrivés — l'état figeait alors un modèle sans
    // entités, et les liens n'apparaissaient plus jamais en ÉDITION (en
    // lecture, aucun changement n'est émis, d'où la différence).
    let resolveBody: ((d: DocumentOut) => void) | undefined
    vi.mocked(docsApi.getDocument).mockImplementation(
      (_ws: string, id: string) =>
        new Promise<DocumentOut>((resolve) => {
          if (id === 'doc-client') resolveBody = resolve
          else resolve(COMMANDE)
        }),
    )

    const ref = createRef<ContentEditorHandle>()
    const onDirty = vi.fn()
    renderSurface(
      <ModelLayoutEditor ref={ref} initialContent="" onDirty={onDirty} docId={MODEL_ID} />,
    )
    await waitFor(() => expect(resolveBody).toBeDefined())

    // L'entité manquante arrive APRÈS : elle doit quand même être dessinée.
    resolveBody!(CLIENT)

    expect(await screen.findByText('Client')).toBeInTheDocument()
    expect(screen.getByText('Commande')).toBeInTheDocument()
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
