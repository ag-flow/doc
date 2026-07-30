/**
 * Catalogue de primitives du bloc `df-display` (ADR 5713844b).
 *
 * Chaque entrée valide ses props (zod, WHITELIST — rien n'est jamais spread
 * brut dans le DOM) et rend avec les tokens Broadsheet : un bloc display doit
 * ressembler à du docflow, pas à un widget étranger. Une prop invalide tombe
 * sur le défaut ; un composant inconnu est traité par l'appelant.
 */
import { useEffect, useState, type ReactNode } from 'react'
import { z } from 'zod'
import {
  ArrowDown, ArrowRight, ArrowUp, Calendar, ChartLineUp, ChartLineDown, ChatCircle,
  Check, Circle, Clock, Database, Envelope, File, Flag, FolderSimple, GearSix, Globe,
  Info, Lightning, LinkSimple, LockSimple, RocketLaunch, ShieldCheck, Star, Tag,
  Target, User, Users, Warning, X,
} from '@phosphor-icons/react'
import { resolveArtifactUrl } from '../lib/artifacts'

// ── Icônes curées : noms kebab-case STABLES, publiés dans la doc agents. ──
const ICONS: Record<string, typeof Circle> = {
  'check': Check, 'x': X, 'warning': Warning, 'info': Info, 'clock': Clock,
  'calendar': Calendar, 'user': User, 'users': Users, 'gear': GearSix,
  'lightning': Lightning, 'flag': Flag, 'star': Star, 'arrow-right': ArrowRight,
  'arrow-up': ArrowUp, 'arrow-down': ArrowDown, 'link': LinkSimple, 'file': File,
  'folder': FolderSimple, 'tag': Tag, 'chat': ChatCircle, 'envelope': Envelope,
  'globe': Globe, 'lock': LockSimple, 'shield': ShieldCheck, 'database': Database,
  'rocket': RocketLaunch, 'target': Target, 'trend-up': ChartLineUp,
  'trend-down': ChartLineDown, 'circle': Circle,
}

export const ICON_NAMES = Object.keys(ICONS)

// Variants Broadsheet : la palette n'a que deux accents — neutral (encre),
// accent (cyan, positif/mis en avant), alert (magenta, échec/attention).
const variantSchema = z.enum(['neutral', 'accent', 'alert']).catch('neutral')
const VARIANT_TAG: Record<string, string> = {
  neutral: 'tag tag-neutral', accent: 'tag tag-accent', alert: 'tag tag-accent-2',
}

const textSchema = z.object({
  text: z.string().catch(''),
  hint: z.enum(['h1', 'h2', 'h3', 'body', 'caption']).catch('body'),
})
const TEXT_CLASS: Record<string, string> = {
  h1: 'm-0 text-[24px] font-[600] leading-[1.2] [font-family:var(--font-heading)]',
  h2: 'm-0 text-[19px] font-[600] leading-[1.25] [font-family:var(--font-heading)]',
  h3: 'm-0 text-[16px] font-[600] leading-[1.3] [font-family:var(--font-heading)]',
  body: 'm-0 text-[15px] leading-[1.6]',
  caption: 'm-0 text-[12px] text-ink/[0.55]',
}

/** `https:` ou artefact docflow (/api/…, résolution authentifiée). */
function imagePolicy(src: string): 'https' | 'artifact' | null {
  if (src.startsWith('https://')) return 'https'
  if (src.startsWith('/api/')) return 'artifact'
  return null
}

/** Image d'artefact : l'endpoint est Bearer — résolution authentifiée en
 *  object URL (cache partagé de resolveArtifactUrl : ne PAS révoquer ici). */
function ArtifactImage({ src, alt }: { src: string; alt: string }) {
  const [url, setUrl] = useState<string | null>(null)
  useEffect(() => {
    let cancelled = false
    void resolveArtifactUrl(src).then((u) => {
      if (!cancelled) setUrl(u)
    })
    return () => { cancelled = true }
  }, [src])
  if (!url) return null
  return <img src={url} alt={alt} className="max-w-full rounded-md" />
}

export interface CatalogEntry {
  /** true = accepte des enfants (containers). */
  container?: boolean
  render(props: Record<string, unknown>, children: ReactNode[]): ReactNode
}

export const CATALOG: Record<string, CatalogEntry> = {
  Row: {
    container: true,
    render: (_p, children) => <div className="flex flex-wrap items-start gap-2.5">{children}</div>,
  },
  Column: {
    container: true,
    render: (_p, children) => <div className="flex flex-col gap-2.5">{children}</div>,
  },
  Card: {
    container: true,
    render: (_p, children) => (
      <div className="min-w-0 flex-1 rounded-md border border-[var(--color-divider)] bg-surface p-3">
        {children}
      </div>
    ),
  },
  List: {
    container: true,
    render: (p, children) => {
      const ordered = z.object({ ordered: z.boolean().catch(false) }).parse(p).ordered
      const items = children.map((c, i) => <li key={i}>{c}</li>)
      return ordered
        ? <ol className="m-0 list-decimal pl-5 text-[15px] leading-[1.6]">{items}</ol>
        : <ul className="m-0 list-disc pl-5 text-[15px] leading-[1.6]">{items}</ul>
    },
  },
  Divider: {
    render: () => <hr className="my-1 border-0 border-t border-[var(--color-divider)]" />,
  },
  Text: {
    render: (p) => {
      const { text, hint } = textSchema.parse(p)
      return <p className={TEXT_CLASS[hint]}>{text}</p>
    },
  },
  Image: {
    render: (p) => {
      const { src, alt } = z
        .object({ src: z.string().catch(''), alt: z.string().catch('') })
        .parse(p)
      const policy = imagePolicy(src)
      if (policy === null) {
        return (
          <span className="text-[12px] italic text-ink/[0.45]" data-testid="display-image-blocked">
            image non autorisée
          </span>
        )
      }
      if (policy === 'artifact') return <ArtifactImage src={src} alt={alt} />
      return <img src={src} alt={alt} className="max-w-full rounded-md" />
    },
  },
  Icon: {
    render: (p) => {
      const { name } = z.object({ name: z.string().catch('circle') }).parse(p)
      const Ico = ICONS[name]
      if (!Ico) return <Circle size={16} weight="duotone" className="text-ink/[0.35]" data-testid="display-icon-unknown" />
      return <Ico size={16} weight="duotone" className="text-accent-700" />
    },
  },
  Badge: {
    render: (p) => {
      const { text, variant } = z
        .object({ text: z.string().catch(''), variant: variantSchema })
        .parse(p)
      return <span className={VARIANT_TAG[variant]}>{text}</span>
    },
  },
  Chip: {
    render: (p) => {
      const { text, variant } = z
        .object({ text: z.string().catch(''), variant: variantSchema })
        .parse(p)
      return <span className={`${VARIANT_TAG[variant]} rounded-full`}>{text}</span>
    },
  },
  ProgressBar: {
    render: (p) => {
      const { value, label } = z
        .object({ value: z.number().catch(0), label: z.string().optional().catch(undefined) })
        .parse(p)
      const pct = Math.max(0, Math.min(100, value))
      return (
        <div className="w-full">
          {label && <p className="m-0 mb-0.5 text-[12px] text-ink/[0.55]">{label}</p>}
          <div className="flex items-center gap-2">
            <div className="h-1.5 min-w-0 flex-1 overflow-hidden rounded-full bg-ink/[0.08]">
              <div className="h-full bg-accent" style={{ width: `${pct}%` }} data-testid="display-progress" />
            </div>
            <span className="shrink-0 text-[12px] text-ink/[0.55]">{pct}%</span>
          </div>
        </div>
      )
    },
  },
}
