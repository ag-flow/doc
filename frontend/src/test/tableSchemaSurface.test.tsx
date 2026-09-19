/** Surface d'édition d'une entité `table-schema` (épic MLD — F7). */

import { describe, it, expect, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import React, { createRef } from 'react'
import { parse as parseYaml } from 'yaml'
import { TableSchemaEditor, TableSchemaViewer } from '../components/mld/TableSchemaSurface'
import type { ContentEditorHandle } from '../lib/contentSurfaces'

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

function renderEditor(content = SCHEMA, onDirty = vi.fn()) {
  const ref = createRef<ContentEditorHandle>()
  render(<TableSchemaEditor ref={ref} initialContent={content} onDirty={onDirty} />)
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
