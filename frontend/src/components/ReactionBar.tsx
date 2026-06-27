import { ThumbsDown, ThumbsUp } from 'lucide-react'
import type { ReactionOut } from '../lib/api'

interface ReactionButtonProps {
  icon: typeof ThumbsUp
  count: number
  active: boolean
  lastUsers: string[]
  onClick: () => void
  disabled?: boolean
}

function ReactionButton({ icon: Icon, count, active, lastUsers, onClick, disabled }: ReactionButtonProps) {
  return (
    <div className="relative group/btn">
      <button
        onClick={onClick}
        disabled={disabled}
        className={[
          'flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-medium',
          'transition-colors disabled:cursor-not-allowed',
          active
            ? 'bg-blue-100 text-blue-700 hover:bg-blue-200'
            : 'bg-gray-100 text-gray-500 hover:bg-gray-200',
        ].join(' ')}
      >
        <Icon size={14} strokeWidth={active ? 2.5 : 1.75} />
        <span>{count}</span>
      </button>
      {lastUsers.length > 0 && (
        <div className="absolute bottom-full left-0 mb-2 hidden group-hover/btn:block z-20 pointer-events-none">
          <div className="bg-gray-900 text-white text-xs rounded-lg py-2 px-3 min-w-max shadow-xl">
            {lastUsers.map((name, i) => (
              <div key={i} className={i > 0 ? 'mt-0.5' : ''}>{name}</div>
            ))}
          </div>
          <div className="w-2 h-2 bg-gray-900 rotate-45 ml-4 -mt-1" />
        </div>
      )}
    </div>
  )
}

interface ReactionBarProps {
  reactions: ReactionOut
  onReact: (nature: 1 | -1) => void
  disabled?: boolean
  className?: string
}

export function ReactionBar({ reactions, onReact, disabled, className }: ReactionBarProps) {
  return (
    <div className={`flex items-center gap-2 ${className ?? ''}`}>
      <ReactionButton
        icon={ThumbsUp}
        count={reactions.likes}
        active={reactions.my_reaction === 1}
        lastUsers={reactions.last_likes}
        onClick={() => onReact(1)}
        disabled={disabled}
      />
      <ReactionButton
        icon={ThumbsDown}
        count={reactions.dislikes}
        active={reactions.my_reaction === -1}
        lastUsers={reactions.last_dislikes}
        onClick={() => onReact(-1)}
        disabled={disabled}
      />
    </div>
  )
}
