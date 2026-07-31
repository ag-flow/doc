import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, PencilSimple, Trash } from '@phosphor-icons/react'
import { artifactTypesApi, type ArtifactTypeOut, ApiError } from '../lib/api'
import { Button } from '../components/ui/button'
import { SectionHead } from '../components/SectionHead'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { EmptyState, ErrorLine, TableSkeleton } from '../components/ui/states'
import { Input } from '../components/ui/input'
import { Field } from '../components/ui/field'
import { useToast } from '../components/Toast'

interface DialogState {
  mode: 'create' | 'edit'
  extension: string
  media_type: string
  label: string
}

function errMessage(e: unknown): string {
  return e instanceof ApiError ? e.message : 'Opération impossible'
}

/** Écran admin : registre des types de fichiers acceptés comme artefacts. */
export function ArtifactTypesAdmin() {
  const qc = useQueryClient()
  const { toast } = useToast()
  const [dialog, setDialog] = useState<DialogState | null>(null)
  const [toDelete, setToDelete] = useState<ArtifactTypeOut | null>(null)

  const { data: types = [], isLoading, isError } = useQuery<ArtifactTypeOut[]>({
    queryKey: ['artifact-types'],
    queryFn: () => artifactTypesApi.adminList(),
  })

  const invalidate = () => qc.invalidateQueries({ queryKey: ['artifact-types'] })

  const saveMutation = useMutation({
    mutationFn: (d: DialogState) =>
      d.mode === 'create'
        ? artifactTypesApi.create({ extension: d.extension, media_type: d.media_type, label: d.label })
        : artifactTypesApi.update(d.extension, { media_type: d.media_type, label: d.label }),
    onSuccess: () => {
      invalidate()
      setDialog(null)
    },
    onError: (e) => toast(errMessage(e), 'error'),
  })

  const deleteMutation = useMutation({
    mutationFn: (extension: string) => artifactTypesApi.delete(extension),
    onSuccess: () => {
      invalidate()
      setToDelete(null)
    },
    onError: (e) => toast(errMessage(e), 'error'),
  })

  return (
    <div className="mx-auto max-w-4xl px-6 py-8">
      <SectionHead kicker="Administration" title="Types d'artefact">
        <Button
          onClick={() => setDialog({ mode: 'create', extension: '', media_type: '', label: '' })}
          data-testid="add-type-btn"
        >
          <Plus size={14} weight="bold" /> Ajouter un type
        </Button>
      </SectionHead>

      <p className="mb-4 max-w-2xl text-[13px] text-ink/[0.6]">
        Extensions acceptées à l'upload d'un fichier. Un fichier dont l'extension
        n'est pas listée est refusé. Les types actifs (HTML, JavaScript…) sont
        interdits par sécurité et ne peuvent pas être ajoutés.
      </p>

      {isLoading ? (
        <TableSkeleton rows={6} columns={3} />
      ) : isError ? (
        <ErrorLine message="Impossible de charger les types d'artefact." />
      ) : types.length === 0 ? (
        <EmptyState message="Aucun type enregistré." />
      ) : (
        <table className="table" data-testid="artifact-types-table">
          <thead>
            <tr>
              <th>Extension</th>
              <th>Type MIME</th>
              <th>Libellé</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {types.map((t) => (
              <tr key={t.extension} data-testid={`type-row-${t.extension}`}>
                <td className="[font-family:var(--font-mono)]">{t.extension}</td>
                <td className="[font-family:var(--font-mono)] text-[13px]">{t.media_type}</td>
                <td>{t.label}</td>
                <td className="text-right whitespace-nowrap">
                  <Button
                    variant="icon"
                    size="sm"
                    title="Modifier"
                    onClick={() =>
                      setDialog({ mode: 'edit', extension: t.extension, media_type: t.media_type, label: t.label })
                    }
                    data-testid={`edit-${t.extension}`}
                  >
                    <PencilSimple size={14} weight="duotone" />
                  </Button>
                  <Button
                    variant="icon"
                    size="sm"
                    title="Supprimer"
                    onClick={() => setToDelete(t)}
                    data-testid={`delete-${t.extension}`}
                  >
                    <Trash size={14} weight="duotone" />
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {dialog && (
        <div className="dialog-backdrop z-50" data-testid="type-dialog">
          <div className="dialog" role="dialog" aria-modal="true">
            <h4 className="dialog-title m-0">
              {dialog.mode === 'create' ? 'Ajouter un type' : `Modifier « ${dialog.extension} »`}
            </h4>
            <form
              onSubmit={(e) => {
                e.preventDefault()
                saveMutation.mutate(dialog)
              }}
            >
              <Field label="Extension" htmlFor="type-ext" hint="minuscules, sans point (ex. pdf)">
                <Input
                  id="type-ext"
                  value={dialog.extension}
                  disabled={dialog.mode === 'edit'}
                  onChange={(e) => setDialog({ ...dialog, extension: e.target.value })}
                  data-testid="type-ext-input"
                />
              </Field>
              <Field label="Type MIME" htmlFor="type-mime" hint="ex. application/pdf">
                <Input
                  id="type-mime"
                  value={dialog.media_type}
                  onChange={(e) => setDialog({ ...dialog, media_type: e.target.value })}
                  data-testid="type-mime-input"
                />
              </Field>
              <Field label="Libellé" htmlFor="type-label">
                <Input
                  id="type-label"
                  value={dialog.label}
                  onChange={(e) => setDialog({ ...dialog, label: e.target.value })}
                  data-testid="type-label-input"
                />
              </Field>
              <div className="dialog-actions">
                <Button type="button" variant="ghost" onClick={() => setDialog(null)}>
                  Annuler
                </Button>
                <Button
                  type="submit"
                  disabled={!dialog.extension.trim() || !dialog.media_type.trim() || saveMutation.isPending}
                  data-testid="type-save"
                >
                  Enregistrer
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}

      {toDelete && (
        <ConfirmDialog
          title="Supprimer ce type"
          message={
            <>
              Le type <strong>{toDelete.extension}</strong> ({toDelete.media_type}) ne sera plus
              accepté à l'upload. Les artefacts déjà stockés ne sont pas affectés.
            </>
          }
          confirmLabel="Supprimer le type"
          pending={deleteMutation.isPending}
          onConfirm={() => deleteMutation.mutate(toDelete.extension)}
          onCancel={() => setToDelete(null)}
          testId="delete-type-dialog"
        />
      )}
    </div>
  )
}
