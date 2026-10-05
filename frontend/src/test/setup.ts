import '@testing-library/jest-dom'

// jsdom n'implémente ni matchMedia ni ResizeObserver ; BlockNote (mantine)
// en a besoin quand un test monte le vrai éditeur/viewer.
if (typeof window !== 'undefined') {
  window.matchMedia = window.matchMedia
    ?? ((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }) as MediaQueryList)

  window.ResizeObserver = window.ResizeObserver
    ?? class {
      observe() {}
      unobserve() {}
      disconnect() {}
    }
}
