/** Surface de repli : texte brut, pour tout type absent du registre. */

import { PlainTextEditor, PlainTextViewer } from '../../components/PlainTextSurface'
import type { ContentSurface } from './index'

// Ne sert aucune valeur de `DocumentOut.type` en propre : c'est le défaut du
// registre pour toute valeur inconnue (y compris absente).
export const plainTextSurface: ContentSurface = {
  contentType: '__plain__',
  Editor: PlainTextEditor,
  Viewer: PlainTextViewer,
}
