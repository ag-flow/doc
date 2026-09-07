/**
 * Bloc maquette d'écran : rend un artefact HTML mutable dans une iframe
 * SANDBOXÉE servie depuis l'origine de preview DÉDIÉE (jamais l'origine docflow).
 *
 * Le bloc ne contient PAS le HTML : il porte l'`artifactId` (sérialisé en
 * `artifact://<uuid>` pour être compté au refcount) et des métadonnées. La vue
 * demande un lien de preview signé (révision-conscient) puis pointe l'iframe
 * dessus. `sandbox="allow-scripts"` SANS `allow-same-origin` : le JS de la
 * maquette s'exécute mais ne peut ni lire le DOM parent, ni les cookies, ni le
 * réseau. La hauteur remonte par postMessage ; comme l'iframe sandboxée a une
 * origine OPAQUE (`e.origin === "null"`), on n'authentifie PAS le message par
 * l'origine mais par `e.source === iframe.contentWindow` (il vient de NOTRE
 * iframe). À défaut de message, la hauteur déclarée s'applique.
 */
import { createReactBlockSpec } from '@blocknote/react'
import { useQuery } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { AppWindow, ArrowClockwise, Warning } from '@phosphor-icons/react'
import { artifactsApi, type PreviewLinkOut } from '../lib/api'
import { useWorkspace } from '../contexts/WorkspaceContext'

/** Largeur simulée par viewport (px). Inconnu → desktop. */
const VIEWPORT_WIDTH: Record<string, number> = { mobile: 390, tablette: 768, desktop: 1024 }
const _MAX_HEIGHT = 6000

export interface MaquetteProps {
  artifactId: string
  titre: string
  viewport: string
  /** Hauteur de repli en px (chaîne, comme tous les attributs de fence). */
  hauteur: string
  description: string
}

/** Vue de la maquette (exportée pour les tests). */
export function MaquetteView({ artifactId, titre, viewport, hauteur, description }: MaquetteProps) {
  const { currentSlug: ws } = useWorkspace()
  const declared = Number(hauteur)
  const fallback = Number.isFinite(declared) && declared > 0 ? declared : 480
  const [height, setHeight] = useState<number>(fallback)
  const iframeRef = useRef<HTMLIFrameElement>(null)

  const link = useQuery<PreviewLinkOut>({
    queryKey: ['artifact-preview', ws, artifactId],
    queryFn: () => artifactsApi.previewLink(ws!, artifactId),
    enabled: Boolean(ws && artifactId),
    staleTime: 30_000,
    // Une maquette éditée par un agent : au retour sur l'onglet, on re-mint le
    // lien ; si la révision a changé, l'URL change et l'iframe recharge.
    refetchOnWindowFocus: true,
    retry: false,
  })

  useEffect(() => {
    function onMessage(e: MessageEvent) {
      // L'iframe sandboxée (sans allow-same-origin) a une origine opaque : son
      // postMessage arrive avec e.origin === "null". On authentifie donc le
      // message par sa SOURCE — il doit venir de notre propre iframe — et non
      // par l'origine (qui ne matcherait jamais l'origine de preview).
      const frame = iframeRef.current
      if (!frame || e.source !== frame.contentWindow) return
      const data = e.data as { type?: string; height?: number } | null
      if (data?.type === 'docflow-preview-height' && typeof data.height === 'number' && data.height > 0) {
        setHeight(Math.min(Math.ceil(data.height), _MAX_HEIGHT))
      }
    }
    window.addEventListener('message', onMessage)
    return () => window.removeEventListener('message', onMessage)
  }, [])

  const width = VIEWPORT_WIDTH[viewport] ?? VIEWPORT_WIDTH.desktop
  const label = titre || description || 'Maquette'

  return (
    <div className="my-2 rounded border border-gray-200 bg-white" data-df-block="maquette">
      <div className="flex items-center gap-2 border-b border-gray-100 px-3 py-1.5 text-sm text-gray-600">
        <AppWindow size={16} weight="duotone" />
        <span className="font-medium text-gray-800">{label}</span>
        <span className="ml-auto text-xs uppercase tracking-wide text-gray-400">{viewport}</span>
        {link.data && (
          <button
            type="button"
            title="Rafraîchir la maquette"
            className="text-gray-400 hover:text-gray-700"
            onClick={() => void link.refetch()}
          >
            <ArrowClockwise size={15} />
          </button>
        )}
      </div>

      {!description && (
        <div className="flex items-center gap-1.5 bg-amber-50 px-3 py-1 text-xs text-amber-700">
          <Warning size={13} /> Description manquante — la maquette ne sera pas trouvable par recherche.
        </div>
      )}

      <div className="flex justify-center bg-gray-50 p-3">
        {!artifactId ? (
          <div
            className="flex w-full items-center justify-center rounded border border-dashed border-gray-300 bg-white p-4 text-center text-sm text-gray-400"
            style={{ maxWidth: width, minHeight: 120 }}
          >
            Renseigner l'artefact HTML de la maquette (create_artifact mutable .html).
          </div>
        ) : link.isPending ? (
          <div
            className="w-full animate-pulse rounded bg-gray-200"
            style={{ maxWidth: width, height: fallback }}
            aria-label="chargement de la maquette"
          />
        ) : link.isError ? (
          <div
            className="flex w-full flex-col items-center justify-center gap-1 rounded bg-gray-100 p-4 text-center text-sm text-gray-500"
            style={{ maxWidth: width, minHeight: 120 }}
          >
            <Warning size={20} />
            <span>Maquette indisponible.</span>
            {description && <span className="text-xs text-gray-400">{description}</span>}
          </div>
        ) : link.data ? (
          <iframe
            ref={iframeRef}
            title={label}
            src={link.data.url}
            sandbox="allow-scripts"
            loading="lazy"
            referrerPolicy="no-referrer"
            className="w-full rounded border-0 bg-white shadow-sm"
            style={{ maxWidth: width, height }}
          />
        ) : null}
      </div>
    </div>
  )
}

/** Spec BlockNote du bloc `dfMaquette`. */
export const MaquetteBlock = createReactBlockSpec(
  {
    type: 'dfMaquette',
    propSchema: {
      artifactId: { default: '' },
      titre: { default: '' },
      viewport: { default: 'desktop' },
      hauteur: { default: '' },
      description: { default: '' },
    },
    content: 'none',
  },
  {
    render: (props) => (
      <MaquetteView
        artifactId={props.block.props.artifactId}
        titre={props.block.props.titre}
        viewport={props.block.props.viewport}
        hauteur={props.block.props.hauteur}
        description={props.block.props.description}
      />
    ),
  },
)
