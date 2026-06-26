import { forwardRef, useEffect, useImperativeHandle, useRef } from 'react'
import { EditorView, basicSetup } from 'codemirror'
import { yaml } from '@codemirror/lang-yaml'

export interface YamlEditorHandle {
  getValue: () => string
}

const EDITOR_THEME = EditorView.theme({
  '&': { height: '100%' },
  '.cm-scroller': { overflow: 'auto', fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace', fontSize: '13px' },
})

interface Props {
  initialValue: string
}

export const YamlEditor = forwardRef<YamlEditorHandle, Props>(({ initialValue }, ref) => {
  const containerRef = useRef<HTMLDivElement>(null)
  const viewRef = useRef<EditorView | null>(null)

  useImperativeHandle(ref, () => ({
    getValue: () => viewRef.current?.state.doc.toString() ?? initialValue,
  }))

  useEffect(() => {
    if (!containerRef.current) return
    const view = new EditorView({
      doc: initialValue,
      extensions: [basicSetup, yaml(), EDITOR_THEME],
      parent: containerRef.current,
    })
    viewRef.current = view
    return () => {
      view.destroy()
      viewRef.current = null
    }
  }, [initialValue])

  return <div ref={containerRef} style={{ height: '100%' }} />
})

YamlEditor.displayName = 'YamlEditor'
