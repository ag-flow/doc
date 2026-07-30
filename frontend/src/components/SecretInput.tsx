import { useQuery } from '@tanstack/react-query'
import { vaultApi } from '../lib/api'

interface SecretInputProps {
  value: string
  onChange: (value: string) => void
  placeholder?: string
  disabled?: boolean
}

const LOCAL = '__local__'

// Parse une valeur : soit local raw, soit ${vault://name:/path}
function parse(value: string): { mode: string; raw: string } {
  const m = value.match(/^\$\{vault:\/\/([^/:]+):(\/.+)\}$/)
  if (m) return { mode: m[1], raw: m[2].replace(/^\//, '') }
  return { mode: LOCAL, raw: value }
}

function build(mode: string, raw: string): string {
  if (mode === LOCAL) return raw
  const path = raw.startsWith('/') ? raw : `/${raw}`
  return `\${vault://${mode}:${path}}`
}

export function SecretInput({ value, onChange, placeholder, disabled }: SecretInputProps) {
  const { data: wallets = [] } = useQuery({
    queryKey: ['vault-wallets'],
    queryFn: () => vaultApi.listWallets(),
  })

  const { mode, raw } = parse(value)

  function setMode(newMode: string) {
    // Changement de catégorie LOCAL ↔ wallet : ne jamais réutiliser la valeur
    // précédente (secret en clair ou chemin) comme donnée dans le nouveau mode.
    const crossesLocalBoundary = (mode === LOCAL) !== (newMode === LOCAL)
    onChange(build(newMode, crossesLocalBoundary ? '' : raw))
  }

  function setRaw(newRaw: string) {
    onChange(build(mode, newRaw))
  }

  const inputPlaceholder =
    mode === LOCAL
      ? (placeholder ?? 'Valeur en clair')
      : 'chemin dans le wallet (ex: oidc/client_secret)'

  return (
    <div className="flex gap-2">
      <div className="w-32 shrink-0">
        <select
          value={mode}
          onChange={(e) => setMode(e.target.value)}
          disabled={disabled}
          className="input text-xs"
        >
          <option value={LOCAL}>En local</option>
          {wallets.map((w) => (
            <option key={w.id} value={w.name}>{w.name}</option>
          ))}
        </select>
      </div>
      <div className="min-w-0 flex-1">
        <input
          type={mode === LOCAL ? 'password' : 'text'}
          value={raw}
          onChange={(e) => setRaw(e.target.value)}
          placeholder={inputPlaceholder}
          disabled={disabled}
          className="input"
        />
      </div>
    </div>
  )
}
