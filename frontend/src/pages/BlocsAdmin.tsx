import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Eye, EyeOff } from 'lucide-react'
import { api, docsApi, type DataBlockOut, type FunctionalType } from '../lib/api'
import { labelToSlug } from '../lib/slug'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'

const SLUG_RE = /^[a-z0-9][a-z0-9_-]*$/

function BlocsTable({ blocs, wsSlug }: { blocs: DataBlockOut[]; wsSlug: string }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const qc = useQueryClient()

  const exposeMutation = useMutation({
    mutationFn: ({ slug, exposed }: { slug: string; exposed: boolean }) =>
      docsApi.setBlockExposed(wsSlug, slug, exposed),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['blocs', wsSlug] })
    },
  })

  return (
    <table className="w-full border-collapse text-sm">
      <thead>
        <tr className="border-b text-left text-gray-500">
          <th className="pb-2 pr-4">{t('ws.slug')}</th>
          <th className="pb-2 pr-4">{t('ws.label')}</th>
          <th className="pb-2 pr-4">{t('blocs.rootType')}</th>
          <th className="pb-2">{t('common.actions')}</th>
        </tr>
      </thead>
      <tbody>
        {blocs.map((bloc) => (
          <tr
            key={bloc.slug}
            className="border-b hover:bg-gray-50"
            data-testid={`bloc-row-${bloc.slug}`}
          >
            <td className="py-2 pr-4 font-mono text-xs">{bloc.slug}</td>
            <td className="py-2 pr-4">{bloc.label}</td>
            <td className="py-2 pr-4">
              <span className="font-mono text-xs text-gray-500">
                {bloc.functional_type_slug}
              </span>
            </td>
            <td className="py-2">
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  title={bloc.exposed ? 'Rendre privé' : 'Exposer publiquement'}
                  onClick={() =>
                    exposeMutation.mutate({ slug: bloc.slug, exposed: !bloc.exposed })
                  }
                  disabled={exposeMutation.isPending}
                  className={`flex items-center gap-1 rounded px-2 py-1 text-xs font-medium
                    transition-colors ${bloc.exposed
                      ? 'bg-emerald-50 text-emerald-700 hover:bg-emerald-100'
                      : 'bg-gray-100 text-gray-500 hover:bg-gray-200'}`}
                  data-testid={`expose-bloc-${bloc.slug}`}
                >
                  {bloc.exposed ? <Eye size={12} /> : <EyeOff size={12} />}
                  {bloc.exposed ? 'Public' : 'Privé'}
                </button>
                <Button
                  size="sm"
                  onClick={() =>
                    void navigate(`/ws/${wsSlug}/blocs/${bloc.slug}/documents`)
                  }
                  data-testid={`open-bloc-${bloc.slug}`}
                >
                  {t('blocs.open')}
                </Button>
              </div>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export function BlocsAdmin() {
  const { t } = useTranslation()
  const { wsSlug } = useParams<{ wsSlug: string }>()
  const qc = useQueryClient()

  const [showCreate, setShowCreate] = useState(false)
  const [slug, setSlug] = useState('')
  const [label, setLabel] = useState('')
  const [typeSlug, setTypeSlug] = useState('')
  const [slugError, setSlugError] = useState('')
  const [slugTouched, setSlugTouched] = useState(false)
  const [apiError, setApiError] = useState('')

  const { data: blocs = [], isLoading } = useQuery<DataBlockOut[]>({
    queryKey: ['blocs', wsSlug],
    queryFn: () => docsApi.getBlocks(wsSlug!),
    enabled: Boolean(wsSlug),
  })

  const { data: types = [] } = useQuery<FunctionalType[]>({
    queryKey: ['types', wsSlug],
    queryFn: () => api.get<FunctionalType[]>(`/workspaces/${wsSlug}/types`),
    enabled: Boolean(wsSlug),
  })

  // Types racines uniquement (sans parent)
  const rootTypes = types.filter((t) => !t.parent_slug)

  const createMutation = useMutation({
    mutationFn: () =>
      api.post<DataBlockOut>(`/workspaces/${wsSlug}/blocks`, {
        slug,
        label,
        functional_type_slug: typeSlug,
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['blocs', wsSlug] })
      setShowCreate(false)
      setSlug('')
      setLabel('')
      setTypeSlug('')
      setSlugTouched(false)
      setApiError('')
    },
    onError: (e: Error) => setApiError(e.message),
  })

  const validateSlug = (v: string) => {
    if (!SLUG_RE.test(v)) setSlugError(t('ws.slugInvalid'))
    else setSlugError('')
  }

  const canSubmit = !slugError && slug && label && typeSlug && !createMutation.isPending

  if (isLoading) return <div className="p-8">{t('common.loading')}</div>

  return (
    <div className="mx-auto max-w-3xl p-8" data-testid="blocs-admin">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-gray-900">{t('blocs.title')}</h1>
        <Button onClick={() => setShowCreate(true)} data-testid="create-bloc-btn">
          {t('blocs.create')}
        </Button>
      </div>

      {apiError && (
        <p className="mb-4 text-sm text-red-600" data-testid="api-error">
          {apiError}
        </p>
      )}

      {showCreate && (
        <form
          data-testid="create-bloc-form"
          className="mb-6 space-y-3 rounded border border-gray-200 bg-white p-4"
          onSubmit={(e) => {
            e.preventDefault()
            if (canSubmit) createMutation.mutate()
          }}
        >
          <div>
            <label className="mb-1 block text-sm font-medium">{t('ws.label')}</label>
            <Input
              data-testid="bloc-label-input"
              value={label}
              onChange={(e) => {
                setLabel(e.target.value)
                if (!slugTouched) {
                  const derived = labelToSlug(e.target.value)
                  setSlug(derived)
                  validateSlug(derived)
                }
              }}
              required
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium">{t('ws.slug')}</label>
            <Input
              data-testid="bloc-slug-input"
              value={slug}
              onChange={(e) => {
                setSlugTouched(true)
                setSlug(e.target.value)
                validateSlug(e.target.value)
              }}
              placeholder="mon-bloc"
              required
            />
            {slugError && <p className="mt-1 text-xs text-red-500">{slugError}</p>}
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium">{t('blocs.rootType')}</label>
            <select
              data-testid="bloc-type-select"
              className="block w-full rounded border border-gray-300 px-3 py-2 text-sm"
              value={typeSlug}
              onChange={(e) => setTypeSlug(e.target.value)}
              required
            >
              <option value="">{t('blocs.selectType')}</option>
              {rootTypes.map((tp) => (
                <option key={tp.slug} value={tp.slug}>
                  {tp.label} ({tp.slug})
                </option>
              ))}
            </select>
          </div>
          <div className="flex gap-2">
            <Button type="submit" disabled={!canSubmit}>
              {t('common.save')}
            </Button>
            <Button
              variant="secondary"
              type="button"
              onClick={() => {
                setShowCreate(false)
                setApiError('')
              }}
            >
              {t('common.cancel')}
            </Button>
          </div>
        </form>
      )}

      {blocs.length === 0 ? (
        <p className="text-gray-500" data-testid="no-blocs">
          {t('blocs.empty')}
        </p>
      ) : (
        <BlocsTable blocs={blocs} wsSlug={wsSlug!} />
      )}
    </div>
  )
}
