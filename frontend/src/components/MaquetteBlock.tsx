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

/** Presets d'appareil (largeur×hauteur en px, proportions réelles). */
const DEVICES: Record<string, { w: number; h: number }> = {
  'iphone-se': { w: 375, h: 667 },
  iphone: { w: 390, h: 844 },
  'iphone-13': { w: 390, h: 844 },
  'iphone-15-pro-max': { w: 430, h: 932 },
  pixel: { w: 412, h: 915 },
  'pixel-7': { w: 412, h: 915 },
  ipad: { w: 768, h: 1024 },
  'ipad-pro': { w: 1024, h: 1366 },
}

/** Résout `device` : preset nommé (ex. iphone-13) ou littéral "LxH" (ex. 390x844). */
function resolveDevice(key: string): { w: number; h: number } | null {
  const k = key.trim()
  if (!k) return null
  const lit = /^(\d{2,5})\s*[x×]\s*(\d{2,5})$/i.exec(k)
  if (lit) return { w: Number(lit[1]), h: Number(lit[2]) }
  return DEVICES[k.toLowerCase()] ?? null
}

const _num = (s: string): number | undefined => {
  const n = Number(s)
  return Number.isFinite(n) && n > 0 ? n : undefined
}

export interface MaquetteProps {
  artifactId: string
  titre: string
  viewport: string
  /** Hauteur en px (chaîne, comme tous les attributs de fence). Repli avant
   * mesure en mode auto ; hauteur VERROUILLÉE du cadre en mode fixe. */
  hauteur: string
  description: string
  /** Largeur libre en px : verrouille la largeur, prime sur le preset viewport. */
  largeur: string
  /** 'fixe' = cadre à hauteur figée + scroll interne (désactive l'auto-hauteur) ;
   * 'auto'/'' = la hauteur épouse le contenu. */
  mode: string
  /** Preset d'appareil (nommé ou "LxH") : pose largeur ET hauteur, cadre fixe. */
  device: string
}

/** Vue de la maquette (exportée pour les tests). */
export function MaquetteView({
  artifactId,
  titre,
  viewport,
  hauteur,
  description,
  largeur,
  mode,
  device,
}: MaquetteProps) {
  const { currentSlug: ws } = useWorkspace()

  // Résolution des verrous de taille (précédence : largeur/hauteur explicites →
  // device → viewport). Un device (ou mode=fixe) fige le cadre : hauteur
  // verrouillée, scroll INTERNE à l'iframe, auto-hauteur désactivée.
  const dev = resolveDevice(device)
  const lockedW = _num(largeur)
  const lockedH = _num(hauteur)
  const width = lockedW ?? dev?.w ?? VIEWPORT_WIDTH[viewport] ?? VIEWPORT_WIDTH.desktop
  // Largeur VERROUILLÉE (largeur explicite ou device) → taille exacte, le cadre
  // ne rétrécit pas à la colonne (le conteneur défile). Sinon (preset viewport
  // seul) → largeur responsive plafonnée à la colonne.
  const widthLocked = Boolean(lockedW || dev)
  const fixed = mode === 'fixe' || (Boolean(dev) && mode !== 'auto')
  const fixedHeight = Math.min(lockedH ?? dev?.h ?? 480, _MAX_HEIGHT)
  const fallback = lockedH ?? 480

  const [autoHeight, setAutoHeight] = useState<number>(fallback)
  const height = fixed ? fixedHeight : autoHeight
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
        setAutoHeight(Math.min(Math.ceil(data.height), _MAX_HEIGHT))
      }
    }
    window.addEventListener('message', onMessage)
    return () => window.removeEventListener('message', onMessage)
  }, [])

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

      <div className="flex justify-center overflow-x-auto bg-gray-50 p-3">
        {!artifactId ? (
          <div
            className="flex w-full items-center justify-center rounded border border-dashed border-gray-300 bg-white p-4 text-center text-sm text-gray-400"
            style={{ maxWidth: width, minHeight: 120 }}
          >
            Renseigner l'artefact HTML de la maquette (create_artifact mutable .html).
          </div>
        ) : link.isPending ? (
          <div
            className={
              widthLocked
                ? 'shrink-0 animate-pulse rounded bg-gray-200'
                : 'w-full animate-pulse rounded bg-gray-200'
            }
            style={widthLocked ? { width, height } : { maxWidth: width, height }}
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
            className={
              widthLocked
                ? 'shrink-0 rounded border-0 bg-white shadow-sm'
                : 'w-full rounded border-0 bg-white shadow-sm'
            }
            style={widthLocked ? { width, height } : { maxWidth: width, height }}
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
      largeur: { default: '' },
      mode: { default: '' },
      device: { default: '' },
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
        largeur={props.block.props.largeur}
        mode={props.block.props.mode}
        device={props.block.props.device}
      />
    ),
  },
)
