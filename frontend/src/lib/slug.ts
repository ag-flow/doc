/** Dérive un slug depuis un label saisi : minuscules, [^a-z-] → '-', dédoublonnage. */
export function labelToSlug(label: string): string {
  return label
    .toLowerCase()
    .replace(/[^a-z-]/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-+|-+$/g, '')
}
