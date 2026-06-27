import { useEffect, useRef } from 'react'
import { BlockNoteSchema, defaultBlockSpecs } from '@blocknote/core'
import { useCreateBlockNote } from '@blocknote/react'
import { BlockNoteView } from '@blocknote/mantine'
import '@blocknote/mantine/style.css'
import { MermaidBlock } from './MermaidBlock'
import { parseMarkdownWithMermaid, type MarkdownEditorApi } from '../lib/mermaidMarkdown'

const schema = BlockNoteSchema.create({
  blockSpecs: { ...defaultBlockSpecs, mermaid: MermaidBlock() },
})

interface MarkdownViewerProps {
  content: string
}

export function MarkdownViewer({ content }: MarkdownViewerProps) {
  const editor = useCreateBlockNote({ schema })
  const loadedRef = useRef(false)

  useEffect(() => {
    if (loadedRef.current) return
    loadedRef.current = true
    let cancelled = false
    void (async () => {
      const api = editor as unknown as MarkdownEditorApi
      const blocks = await parseMarkdownWithMermaid(api, content ?? '')
      if (cancelled) return
      if (blocks.length > 0) {
        editor.replaceBlocks(editor.document, blocks as never)
      }
    })()
    return () => { cancelled = true }
  }, [editor, content])

  return (
    <div className="rounded border border-gray-100 bg-white">
      <BlockNoteView editor={editor} editable={false} />
    </div>
  )
}
