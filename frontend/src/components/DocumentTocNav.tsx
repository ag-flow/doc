import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { ArrowLeft, ArrowRight } from '@phosphor-icons/react'
import { docsApi, type BlockTreeNode } from '../lib/api'

/**
 * Navigation de lecture d'un bloc : sommaire (colonne gauche) et boutons
 * Précédent / Suivant (bas de feuille), tous deux dans l'ordre de lecture de
 * l'arbre (parcours en profondeur — le même que la page sommaire du bloc).
 * Mode lecture uniquement : l'édition garde son écran concentré.
 */

interface FlatEntry {
  id: string
  title: string
  depth: number
}

function flatten(nodes: BlockTreeNode[], depth = 0, out: FlatEntry[] = []): FlatEntry[] {
  for (const n of nodes) {
    out.push({ id: n.id, title: n.title, depth })
    flatten(n.children, depth + 1, out)
  }
  return out
}

/** Arbre complet du bloc (toutes les pages de racines, plafonné à 1000). */
function useBlockReadingOrder(ws: string, bloc: string) {
  return useQuery<FlatEntry[]>({
    queryKey: ['block-reading-order', ws, bloc],
    queryFn: async () => {
      const roots: BlockTreeNode[] = []
      let page = 1
      for (;;) {
        const p = await docsApi.getBlockTree(ws, bloc, page, 100)
        roots.push(...p.roots)
        // Garde-fou : au-delà de 1000 racines, le sommaire s'arrête là.
        if (!p.has_next || page >= 10) break
        page += 1
      }
      return flatten(roots)
    },
    staleTime: 30_000,
  })
}

function docPath(ws: string, bloc: string, id: string) {
  return `/ws/${ws}/blocs/${bloc}/documents/${id}`
}

/** Sommaire du bloc, document courant marqué. */
export function DocumentToc({ ws, bloc, docId }: { ws: string; bloc: string; docId: string }) {
  const { t } = useTranslation()
  const { data } = useBlockReadingOrder(ws, bloc)
  if (!data?.length) return null
  return (
    <nav className="doc-toc" aria-label={t('docnav.toc')} data-testid="doc-toc">
      <h2 className="doc-aside-kicker">{t('docnav.toc')}</h2>
      <ul className="m-0 list-none p-0">
        {data.map((e) => (
          <li key={e.id} style={{ paddingLeft: e.depth * 14 }}>
            <Link
              to={docPath(ws, bloc, e.id)}
              aria-current={e.id === docId ? 'page' : undefined}
              className={`doc-toc-link${e.id === docId ? ' doc-toc-current' : ''}`}
            >
              {e.title}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  )
}

/** Précédent / Suivant en bas de feuille, dans l'ordre du sommaire. */
export function DocumentPrevNext({ ws, bloc, docId }: { ws: string; bloc: string; docId: string }) {
  const { t } = useTranslation()
  const { data } = useBlockReadingOrder(ws, bloc)
  const idx = data?.findIndex((e) => e.id === docId) ?? -1
  if (!data || idx < 0) return null
  const prev = idx > 0 ? data[idx - 1] : null
  const next = idx < data.length - 1 ? data[idx + 1] : null
  if (!prev && !next) return null
  return (
    <nav className="doc-pagenav" aria-label={`${t('docnav.prev')} / ${t('docnav.next')}`}
      data-testid="doc-pagenav">
      {prev ? (
        <Link to={docPath(ws, bloc, prev.id)} className="doc-pagenav-link"
          data-testid="doc-pagenav-prev">
          <span className="doc-pagenav-kicker">
            <ArrowLeft size={12} weight="bold" /> {t('docnav.prev')}
          </span>
          <span className="doc-pagenav-title">{prev.title}</span>
        </Link>
      ) : (
        <span />
      )}
      {next && (
        <Link to={docPath(ws, bloc, next.id)} className="doc-pagenav-link doc-pagenav-next"
          data-testid="doc-pagenav-next">
          <span className="doc-pagenav-kicker">
            {t('docnav.next')} <ArrowRight size={12} weight="bold" />
          </span>
          <span className="doc-pagenav-title">{next.title}</span>
        </Link>
      )}
    </nav>
  )
}
