import { forwardRef, useEffect, useImperativeHandle, useRef } from 'react'
import { EditorView, basicSetup } from 'codemirror'
import { json } from '@codemirror/lang-json'

export interface JsonEditorHandle {
  getValue: () => string
  setValue: (v: string) => void
}

const EDITOR_THEME = EditorView.theme({
  '&': { minHeight: '120px' },
  '.cm-scroller': {
    overflow: 'auto',
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
    fontSize: '13px',
  },
})

interface Props {
  initialValue?: string
  onChange?: (value: string) => void
}

export const JsonEditor = forwardRef<JsonEditorHandle, Props>(
  ({ initialValue = '', onChange }, ref) => {
    const containerRef = useRef<HTMLDivElement>(null)
    const viewRef = useRef<EditorView | null>(null)
    const onChangeRef = useRef(onChange)

    useEffect(() => {
      onChangeRef.current = onChange
    }, [onChange])

    useImperativeHandle(ref, () => ({
      getValue: () => viewRef.current?.state.doc.toString() ?? initialValue,
      setValue: (v: string) => {
        const view = viewRef.current
        if (!view) return
        view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: v } })
      },
    }))

    useEffect(() => {
      if (!containerRef.current) return
      const updateListener = EditorView.updateListener.of((update) => {
        if (update.docChanged) onChangeRef.current?.(update.state.doc.toString())
      })
      const view = new EditorView({
        doc: initialValue,
        extensions: [basicSetup, json(), EDITOR_THEME, updateListener],
        parent: containerRef.current,
      })
      viewRef.current = view
      return () => {
        view.destroy()
        viewRef.current = null
      }
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [])

    return (
      <div
        ref={containerRef}
        className="rounded-md border border-gray-200 overflow-hidden"
      />
    )
  }
)

JsonEditor.displayName = 'JsonEditor'
