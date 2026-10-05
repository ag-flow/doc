/** Surface d'édition d'une entité `table-schema` (épic MLD — F7). */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import userEvent from '@testing-library/user-event'
import React, { createRef } from 'react'
import { parse as parseYaml } from 'yaml'
import { TableSchemaEditor, TableSchemaViewer } from '../components/mld/TableSchemaSurface'
import type { ContentEditorHandle } from '../lib/contentSurfaces'
import { docsApi } from '../lib/api'

vi.mock('../lib/api', () => ({
  docsApi: { listDocuments: vi.fn(), getDocument: vi.fn() },
}))
vi.mock('../contexts/WorkspaceContext', () => ({ useWorkspaceSlugOrNull: () => 'ws' }))

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }))

// La description est rédigée dans l'éditeur markdown complet. On le remplace par
// un substitut au contrat identique : BlockNote n'est pas déterministe en jsdom,
// et ce n'est pas lui qu'on teste ici.
vi.mock('../components/MarkdownEditor', () => ({
  MarkdownEditor: React.forwardRef(
    (
      { initialContent, onDirty }: { initialContent?: string; onDirty?: () => void },
      ref: React.Ref<{ getContent: () => Promise<string> }>,
    ) => {
      const [value, setValue] = React.useState(initialContent ?? '')
      React.useImperativeHandle(ref, () => ({ getContent: async () => value }), [value])
      return (
        <textarea
          aria-label="description"
          value={value}
          onChange={(e) => {
            setValue(e.target.value)
            onDirty?.()
          }}
        />
      )
    },
  ),
}))
vi.mock('../components/MarkdownViewer', () => ({
  MarkdownViewer: ({ content }: { content: string }) => <div>{content}</div>,
}))

const SCHEMA = `name: commande
title: Commande
description: Une commande passée par un client.
fields:
  - docflow.id: fld_aaaaaaaaaaaa
    name: id
    type: uuid
    format: uuid-v4
  - docflow.id: fld_bbbbbbbbbbbb
    name: montant
    type: number
    constraints:
      required: true
docflow.relations:
  - docflow.id: rel_cccccccccccc
    name: passee_par
    cardinality: many-to-one
    from: id
    to:
      resource: client
      fields: id
`

/** Entités voisines : la cible d'une relation se CHOISIT désormais dans la
 *  liste des entités du bloc, ce qui fait de cette surface une consommatrice de
 *  l'API. Les têtes ne portent pas de contenu — l'API ne le peuple jamais sur
 *  une liste — les corps sont servis document par document. */
const CLIENT = {
  doc_technical_key: 'doc-client',
  title: 'Client',
  type: 'table-schema',
  slug: null,
  content: 'name: client\nfields:\n  - name: id\n    type: uuid\n  - name: email\n    title: E-mail\n',
  version: 1,
  parent_id: 'doc-modele',
  functional_type_slug: 'entity',
  workspace_slug: 'ws',
  data_block_ref: 'b1',
  exposed: false,
  created_at: '',
  updated_at: '',
  updated_by: null,
}
const SELF = {
  ...CLIENT,
  doc_technical_key: 'doc-commande',
  title: 'Commande',
  content: 'name: commande\n',
}
const MODELE = {
  ...CLIENT,
  doc_technical_key: 'doc-modele',
  title: 'Boutique',
  type: 'model-layout',
  functional_type_slug: 'model',
  parent_id: null,
  content: '',
}

beforeEach(() => {
  vi.mocked(docsApi.listDocuments).mockResolvedValue(
    [MODELE, SELF, CLIENT].map((d) => ({ ...d, content: null })) as never,
  )
  vi.mocked(docsApi.getDocument).mockImplementation((async (_ws: string, id: string) =>
    [MODELE, SELF, CLIENT].find((d) => d.doc_technical_key === id)) as never)
})

function renderEditor(content = SCHEMA, onDirty = vi.fn()) {
  const ref = createRef<ContentEditorHandle>()
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={qc}>
      <TableSchemaEditor
        ref={ref}
        initialContent={content}
        onDirty={onDirty}
        docId="doc-commande"
      />
    </QueryClientProvider>,
  )
  return { ref, onDirty }
}

async function contentOf(ref: React.RefObject<ContentEditorHandle | null>) {
  return parseYaml(await ref.current!.getContent())
}

// ── Rendu ─────────────────────────────────────────────────────────────────────

describe('TableSchemaSurface — rendu', () => {
  it('affiche une ligne par champ', () => {
    renderEditor()
    expect(screen.getByTestId('field-row-0')).toBeInTheDocument()
    expect(screen.getByTestId('field-row-1')).toBeInTheDocument()
    expect(screen.getByDisplayValue('montant')).toBeInTheDocument()
  })

  it('sort la description en panneau latéral', () => {
    // Un texte libre ne tient pas dans une colonne sans rendre la grille illisible.
    renderEditor()
    const panel = screen.getByTestId('description-panel')
    expect(panel).toHaveTextContent('mld.description')
    expect(screen.getByLabelText('description')).toHaveValue('Une commande passée par un client.')
  })

  it('rend un schéma illisible sans casser', () => {
    renderEditor('name: t\n  fields: [oups')
    expect(screen.getByTestId('table-schema-surface')).toBeInTheDocument()
  })

  it('la vue lecture n\'offre ni ajout ni suppression', () => {
    render(<TableSchemaViewer content={SCHEMA} />)
    expect(screen.queryByTestId('field-add')).not.toBeInTheDocument()
    expect(screen.queryByTestId('field-remove-0')).not.toBeInTheDocument()
  })
})

// ── Édition ───────────────────────────────────────────────────────────────────

describe('TableSchemaSurface — édition', () => {
  it('modifie un champ et signale la modification', async () => {
    const { ref, onDirty } = renderEditor()
    // Ciblé par sa LIGNE : plusieurs champs du tableau sont vides.
    const nom = within(screen.getByTestId('field-row-1')).getByLabelText('mld.fieldName')

    await userEvent.clear(nom)
    await userEvent.type(nom, 'montant_ttc')

    expect(onDirty).toHaveBeenCalled()
    const schema = await contentOf(ref)
    expect(schema.fields[1].name).toBe('montant_ttc')
  })

  it('change le type d\'un champ dans le vocabulaire logique', async () => {
    const { ref } = renderEditor()
    const type = within(screen.getByTestId('field-row-1')).getByLabelText('mld.fieldType')

    await userEvent.selectOptions(type, 'integer')

    expect((await contentOf(ref)).fields[1].type).toBe('integer')
  })

  it('ajoute et retire un champ', async () => {
    const { ref } = renderEditor()

    await userEvent.click(screen.getByTestId('field-add'))
    expect((await contentOf(ref)).fields).toHaveLength(3)

    await userEvent.click(screen.getByTestId('field-remove-0'))
    const schema = await contentOf(ref)
    expect(schema.fields).toHaveLength(2)
    expect(schema.fields[0].name).toBe('montant')
  })

  it('édite la description dans l\'éditeur markdown', async () => {
    const { ref } = renderEditor()
    const area = screen.getByLabelText('description')

    await userEvent.clear(area)
    await userEvent.type(area, 'Nouvelle description.')

    expect((await contentOf(ref)).description).toBe('Nouvelle description.')
  })
})

// ── Relations ─────────────────────────────────────────────────────────────────

describe('TableSchemaSurface — relations', () => {
  it('affiche les relations de l\'entité', () => {
    renderEditor()
    expect(screen.getByTestId('relation-row-0')).toBeInTheDocument()
    expect(screen.getByDisplayValue('passee_par')).toBeInTheDocument()
  })

  it('renomme une relation', async () => {
    const { ref } = renderEditor()
    const nom = within(screen.getByTestId('relation-row-0')).getByLabelText('mld.relationName')

    await userEvent.clear(nom)
    await userEvent.type(nom, 'rattachee_a')

    expect((await contentOf(ref))['docflow.relations'][0].name).toBe('rattachee_a')
  })

  it('change la cardinalité', async () => {
    const { ref } = renderEditor()
    const card = within(screen.getByTestId('relation-row-0')).getByLabelText(
      'mld.relationCardinality',
    )

    await userEvent.selectOptions(card, 'one-to-many')

    expect((await contentOf(ref))['docflow.relations'][0].cardinality).toBe('one-to-many')
  })

  it('ajoute et retire une relation', async () => {
    const { ref } = renderEditor()

    await userEvent.click(screen.getByTestId('relation-add'))
    expect((await contentOf(ref))['docflow.relations']).toHaveLength(2)

    await userEvent.click(screen.getByTestId('relation-remove-1'))
    expect((await contentOf(ref))['docflow.relations']).toHaveLength(1)
  })

  it('préserve l\'identifiant stable d\'une relation qu\'on renomme', async () => {
    // `docflow.id` rattache les coudes persistés du diagramme à la relation :
    // le perdre les détacherait.
    const { ref } = renderEditor()
    const nom = within(screen.getByTestId('relation-row-0')).getByLabelText('mld.relationName')

    await userEvent.clear(nom)

    expect((await contentOf(ref))['docflow.relations'][0]['docflow.id']).toBe('rel_cccccccccccc')
  })

  it('la vue lecture n\'offre ni ajout ni suppression', () => {
    render(<TableSchemaViewer content={SCHEMA} />)
    expect(screen.queryByTestId('relation-add')).not.toBeInTheDocument()
    expect(screen.queryByTestId('relation-remove-0')).not.toBeInTheDocument()
  })
})

// ── Choix de la cible ────────────────────────────────────────────────────────

describe('TableSchemaSurface — cible d\'une relation', () => {
  function targetSelect() {
    return within(screen.getByTestId('relation-row-0')).getByLabelText(
      'mld.relationTarget',
    ) as HTMLSelectElement
  }

  it('propose les entités du bloc, par leur TITRE', async () => {
    // Saisir le `name` à la main ne produisait aucune erreur en cas de faute :
    // la relation disparaissait simplement du diagramme.
    renderEditor()
    await waitFor(() =>
      expect(within(targetSelect()).getByRole('option', { name: 'Client' })).toBeInTheDocument(),
    )
    // Un modèle n'est pas une entité : il ne peut pas être la cible.
    expect(within(targetSelect()).queryByRole('option', { name: 'Boutique' })).toBeNull()
  })

  it('écrit le `name` du schéma, pas le titre affiché', async () => {
    const { ref } = renderEditor()
    await waitFor(() =>
      expect(within(targetSelect()).getByRole('option', { name: 'Commande' })).toBeInTheDocument(),
    )

    await userEvent.selectOptions(targetSelect(), 'commande')

    expect((await contentOf(ref))['docflow.relations'][0].to.resource).toBe('commande')
  })

  it('propose les champs de la cible choisie', async () => {
    renderEditor()
    const champ = within(screen.getByTestId('relation-row-0')).getByLabelText(
      'mld.relationTargetField',
    )
    // La cible enregistrée est `client` : ce sont SES champs qu'on vise.
    await waitFor(() =>
      expect(within(champ).getByRole('option', { name: /email/ })).toBeInTheDocument(),
    )
  })

  it('change de cible remet le champ visé à zéro', async () => {
    // Le garder pointerait vers un champ d'une AUTRE entité, silencieusement.
    const { ref } = renderEditor()
    await waitFor(() =>
      expect(within(targetSelect()).getByRole('option', { name: 'Commande' })).toBeInTheDocument(),
    )

    await userEvent.selectOptions(targetSelect(), 'commande')

    expect((await contentOf(ref))['docflow.relations'][0].to.fields).toBe('')
  })

  it('conserve une cible introuvable au lieu de la remplacer', async () => {
    // Cible d'un autre bloc, entité supprimée, relation écrite avant la liste :
    // afficher le formulaire ne doit pas réécrire la relation.
    const orphelin = SCHEMA.replace('resource: client', 'resource: disparue')
    const { ref } = renderEditor(orphelin)

    await waitFor(() => expect(targetSelect().value).toBe('disparue'))
    expect((await contentOf(ref))['docflow.relations'][0].to.resource).toBe('disparue')
  })
})

// ── Ce que l'édition ne doit JAMAIS détruire ─────────────────────────────────

describe('TableSchemaSurface — préservation', () => {
  it('préserve les identifiants stables des champs', async () => {
    // `docflow.id` porte l'identité du champ : le perdre détacherait les
    // relations qui s'y accrochent et les positions du diagramme.
    const { ref } = renderEditor()

    // Ciblé par sa LIGNE : « id » apparaît aussi dans les extrémités de relation.
    await userEvent.clear(
      within(screen.getByTestId('field-row-0')).getByLabelText('mld.fieldName'),
    )
    const schema = await contentOf(ref)

    expect(schema.fields[0]['docflow.id']).toBe('fld_aaaaaaaaaaaa')
    expect(schema.fields[1]['docflow.id']).toBe('fld_bbbbbbbbbbbb')
  })

  it('préserve les clés que la grille n\'affiche pas', async () => {
    // Une surface d'édition ne doit pas détruire ce qu'elle ne sait pas montrer.
    const { ref } = renderEditor()

    await userEvent.clear(screen.getByDisplayValue('montant'))
    const schema = await contentOf(ref)

    expect(schema.fields[0].format).toBe('uuid-v4')
    expect(schema.fields[1].constraints).toEqual({ required: true })
  })

  it('préserve les relations, absentes de la grille', async () => {
    const { ref } = renderEditor()
    await userEvent.click(screen.getByTestId('field-add'))

    const schema = await contentOf(ref)
    expect(schema['docflow.relations']).toHaveLength(1)
    expect(schema['docflow.relations'][0]['docflow.id']).toBe('rel_cccccccccccc')
  })

  it('rend le contenu d\'origine tel quel tant que rien n\'a bougé', async () => {
    // Ouvrir puis enregistrer ne doit pas produire un diff.
    const { ref } = renderEditor()
    await expect(ref.current!.getContent()).resolves.toBe(SCHEMA)
  })
})
