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
    onChange(build(newMode, raw))
  }

  function setRaw(newRaw: string) {
    onChange(build(mode, newRaw))
  }

  const inputPlaceholder =
    mode === LOCAL
      ? (placeholder ?? 'Valeur en clair')
      : 'chemin dans le wallet (ex: oidc/client_secret)'

  return (
    <div className="flex rounded-md shadow-sm">
      <select
        value={mode}
        onChange={(e) => setMode(e.target.value)}
        disabled={disabled}
        className="w-32 shrink-0 rounded-l-md border border-r-0 border-gray-300 bg-gray-50 px-2 py-2 text-xs text-gray-700 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
      >
        <option value={LOCAL}>En local</option>
        {wallets.map((w) => (
          <option key={w.id} value={w.name}>{w.name}</option>
        ))}
      </select>
      <input
        type={mode === LOCAL ? 'password' : 'text'}
        value={raw}
        onChange={(e) => setRaw(e.target.value)}
        placeholder={inputPlaceholder}
        disabled={disabled}
        className="min-w-0 flex-1 rounded-r-md border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 disabled:bg-gray-50 disabled:text-gray-400"
      />
    </div>
  )
}
