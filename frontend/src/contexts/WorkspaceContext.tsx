import { createContext, useContext, useState } from 'react'
import type { ReactNode } from 'react'

interface WorkspaceContextValue {
  currentSlug: string | null
  setCurrentSlug: (slug: string | null) => void
}

const WorkspaceContext = createContext<WorkspaceContextValue | null>(null)

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const [currentSlug, setCurrentSlug] = useState<string | null>(
    () => localStorage.getItem('ws_slug')
  )

  const set = (slug: string | null) => {
    if (slug) localStorage.setItem('ws_slug', slug)
    else localStorage.removeItem('ws_slug')
    setCurrentSlug(slug)
  }

  return (
    <WorkspaceContext.Provider value={{ currentSlug, setCurrentSlug: set }}>
      {children}
    </WorkspaceContext.Provider>
  )
}

export function useWorkspace(): WorkspaceContextValue {
  const ctx = useContext(WorkspaceContext)
  if (!ctx) throw new Error('useWorkspace must be used inside WorkspaceProvider')
  return ctx
}
