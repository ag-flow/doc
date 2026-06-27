import { useEffect, useId, useState } from 'react'
import { createReactBlockSpec } from '@blocknote/react'
import mermaid from 'mermaid'

mermaid.initialize({ startOnLoad: false })

/** Rendu d'un diagramme mermaid ; en cas d'erreur, repli sur la source brute. */
function MermaidRenderer({ source }: { source: string }) {
  const rawId = useId()
  const renderId = `mermaid-${rawId.replace(/:/g, '')}`
  const [svg, setSvg] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    const src = source.trim()
    if (!src) {
      setSvg(null)
      setError(null)
      return
    }
    mermaid
      .render(renderId, src)
      .then((result) => {
        if (!cancelled) {
          setSvg(result.svg)
          setError(null)
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setSvg(null)
          setError(err instanceof Error ? err.message : String(err))
        }
      })
    return () => {
      cancelled = true
    }
  }, [source, renderId])

  if (error || svg === null) {
    return (
      <pre
        className="overflow-auto rounded border border-amber-300 bg-amber-50 p-3 text-xs text-amber-900"
        data-testid="mermaid-source"
      >
        {source}
      </pre>
    )
  }

  return (
    <div
      data-testid="mermaid-svg"
      className="overflow-auto rounded border border-gray-200 bg-white p-3"
      // eslint-disable-next-line react/no-danger -- sortie SVG produite par mermaid
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  )
}

/**
 * Bloc BlockNote custom `mermaid`.
 *
 * Stocke la source dans la prop `source`. La (dé)sérialisation markdown
 * (fences ```mermaid) est gérée au niveau du wrapper éditeur, BlockNote 0.51
 * n'exposant pas de sérialiseur markdown par bloc dans `createReactBlockSpec`.
 */
export const MermaidBlock = createReactBlockSpec(
  {
    type: 'mermaid',
    propSchema: {
      source: { default: '' },
    },
    content: 'none',
  },
  {
    render: (props) => {
      const source = props.block.props.source
      return (
        <div className="my-2 w-full" data-content-type="mermaid">
          <MermaidRenderer source={source} />
        </div>
      )
    },
  },
)
