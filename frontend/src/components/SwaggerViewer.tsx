import { useEffect, useRef } from 'react'
// eslint-disable-next-line @typescript-eslint/ban-ts-comment
// @ts-expect-error — swagger-ui-dist n'expose pas de types
import { SwaggerUIBundle } from 'swagger-ui-dist'
import 'swagger-ui-dist/swagger-ui.css'

/** Rendu Swagger UI local d'un spec OpenAPI (chargé en lazy, hors bundle principal). */
export default function SwaggerViewer({ spec }: { spec: object }) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!ref.current) return
    SwaggerUIBundle({
      spec,
      domNode: ref.current,
      deepLinking: false,
      tryItOutEnabled: false,
      supportedSubmitMethods: [], // lecture/validation seule, pas d'appels réseau
      defaultModelsExpandDepth: 0,
    })
  }, [spec])

  return <div ref={ref} className="swagger-local" />
}
