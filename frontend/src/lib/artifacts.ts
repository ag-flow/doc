import { artifactsApi, getToken } from './api'

/** URL de service d'un artefact telle qu'insérée dans le markdown par l'éditeur
 *  (et extraite côté backend par artifacts/parser.py). */
const ARTIFACT_URL_RE = /^\/api\/workspaces\/([^/]+)\/artifacts\/([0-9a-fA-F-]{36})$/

/** Cache des object URLs : un artefact est adressé par contenu (dédup sha256),
 *  son binaire est immuable — une résolution par session suffit. */
const objectUrlCache = new Map<string, string>()

/** Handler `uploadFile` de BlockNote : pousse le binaire vers l'API artefacts
 *  et retourne l'URL de service à stocker dans le bloc image (markdown `![]()`). */
export function makeUploadFile(ws: string): (file: File) => Promise<string> {
  return async (file: File) => {
    const created = await artifactsApi.upload(ws, file)
    return created.url
  }
}

/** Handler `resolveFileUrl` de BlockNote : une balise <img> ne peut pas porter
 *  le Bearer, on télécharge donc le binaire via fetch authentifié et on rend
 *  une object URL locale. Les URLs non-artefact passent inchangées. */
export async function resolveArtifactUrl(url: string): Promise<string> {
  const match = ARTIFACT_URL_RE.exec(url)
  if (!match) return url
  const cached = objectUrlCache.get(url)
  if (cached) return cached
  // Visiteur non authentifié (page publique) : laisser l'URL telle quelle
  // plutôt que déclencher un fetch voué au 401.
  if (!getToken()) return url
  try {
    const blob = await artifactsApi.getBlob(match[1], match[2])
    const objectUrl = URL.createObjectURL(blob)
    objectUrlCache.set(url, objectUrl)
    return objectUrl
  } catch {
    return url
  }
}
