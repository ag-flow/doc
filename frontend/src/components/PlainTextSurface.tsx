/**
 * Surface de repli — tout type de contenu absent du registre (épic MLD — F4b).
 *
 * Garantit l'exigence « un type inconnu ne casse jamais la page » : le corps du
 * document est montré tel quel, lisible et éditable en texte brut. C'est la
 * surface que verra un document `table-schema` ou `model-layout` tant que sa
 * surface dédiée n'est pas écrite (F5, F7) — dégradé assumé, jamais une page
 * blanche ni une erreur.
 *
 * Le contenu n'est ni interprété ni réécrit : ce qui est lu est ce qui est
 * sauvegardé. Une surface qui ne comprend pas une grammaire ne doit surtout pas
 * la reformater — elle la corromprait.
 */

import { forwardRef, useImperativeHandle, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import type {
  ContentEditorHandle,
  ContentEditorProps,
  ContentViewerHandle,
  ContentViewerProps,
} from '../lib/contentSurfaces'

export const PlainTextEditor = forwardRef<ContentEditorHandle, ContentEditorProps>(
  ({ initialContent, onDirty }, ref) => {
    const { t } = useTranslation()
    const areaRef = useRef<HTMLTextAreaElement>(null)

    // Non contrôlé, comme les autres surfaces : `defaultValue` au montage, et la
    // page aspire le contenu courant au moment du save.
    useImperativeHandle(
      ref,
      () => ({
        getContent: async () => areaRef.current?.value ?? '',
      }),
      [],
    )

    return (
      <div className="rounded border border-gray-200 bg-white" data-testid="plaintext-editor">
        <p className="border-b border-gray-200 px-3 py-2 text-xs text-gray-600">
          {t('editor.unknownContentType')}
        </p>
        <textarea
          ref={areaRef}
          defaultValue={initialContent}
          onChange={onDirty}
          spellCheck={false}
          aria-label={t('editor.plainTextBody')}
          className="block max-h-[70vh] min-h-[24rem] w-full resize-y bg-transparent p-3 font-mono text-sm outline-none"
        />
      </div>
    )
  },
)
PlainTextEditor.displayName = 'PlainTextEditor'

export const PlainTextViewer = forwardRef<ContentViewerHandle, ContentViewerProps>(
  ({ content, bare }, ref) => {
    // Aucune copie riche : un contenu opaque n'a pas de représentation HTML
    // fidèle. `copyRich` reste absent du handle (il est optionnel au contrat),
    // et la page retombe sur la copie texte normale.
    useImperativeHandle(ref, () => ({}), [])

    return (
      <pre
        data-testid="plaintext-viewer"
        className={`overflow-x-auto whitespace-pre-wrap break-words font-mono text-sm ${
          bare ? '' : 'rounded border border-gray-200 bg-white p-3'
        }`}
      >
        {content}
      </pre>
    )
  },
)
PlainTextViewer.displayName = 'PlainTextViewer'
