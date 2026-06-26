import { useEffect, useImperativeHandle, forwardRef, useRef } from 'react'
import { BlockNoteSchema, defaultBlockSpecs } from '@blocknote/core'
import { useCreateBlockNote } from '@blocknote/react'
import { BlockNoteView } from '@blocknote/mantine'
import '@blocknote/mantine/style.css'
import { MermaidBlock } from './MermaidBlock'
import {
  parseMarkdownWithMermaid,
  serializeMarkdownWithMermaid,
  type MarkdownEditorApi,
} from '../lib/mermaidMarkdown'

const schema = BlockNoteSchema.create({
  blockSpecs: { ...defaultBlockSpecs, mermaid: MermaidBlock() },
})

export interface MarkdownEditorHandle {
  getMarkdown: () => Promise<string>
}

interface MarkdownEditorProps {
  initialContent: string
  onDirty: () => void
}

/** Éditeur BlockNote avec schéma mermaid ; charge le markdown initial une fois. */
export const MarkdownEditor = forwardRef<MarkdownEditorHandle, MarkdownEditorProps>(
  ({ initialContent, onDirty }, ref) => {
    const editor = useCreateBlockNote({ schema })
    const loadedRef = useRef(false)

    useEffect(() => {
      if (loadedRef.current) return
      loadedRef.current = true
      let cancelled = false
      void (async () => {
        const api = editor as unknown as MarkdownEditorApi
        const blocks = await parseMarkdownWithMermaid(api, initialContent ?? '')
        if (cancelled || blocks.length === 0) return
        editor.replaceBlocks(editor.document, blocks as never)
      })()
      return () => {
        cancelled = true
      }
    }, [editor, initialContent])

    useImperativeHandle(
      ref,
      () => ({
        getMarkdown: () =>
          serializeMarkdownWithMermaid(editor as unknown as MarkdownEditorApi),
      }),
      [editor],
    )

    return (
      <div className="rounded border border-gray-200 bg-white" data-testid="markdown-editor">
        <BlockNoteView editor={editor} onChange={onDirty} />
      </div>
    )
  },
)
MarkdownEditor.displayName = 'MarkdownEditor'
