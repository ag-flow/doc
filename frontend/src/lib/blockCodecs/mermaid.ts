/** Codec du bloc mermaid : fence ```mermaid ⇆ bloc custom `mermaid`. */
import { MermaidBlock } from '../../components/MermaidBlock'

export interface MermaidProps extends Record<string, unknown> {
  source: string
}

export const mermaidCodec = {
  type: 'mermaid',
  pattern: /```mermaid\n([\s\S]*?)```/g,
  toBlock: (match: RegExpExecArray): MermaidProps => ({
    source: match[1].replace(/\n$/, ''),
  }),
  toMarkdown: (props: MermaidProps): string => '```mermaid\n' + (props.source ?? '') + '\n```',
  spec: () => MermaidBlock(),
}
