import { useEffect, useRef, useState } from 'react'
import { Icon, type IconName } from './Icon'

export interface MoreItem {
  label: string
  icon?: IconName
  danger?: boolean
  onClick: () => void
}

/**
 * The "⋯" menu at the end of a page's action row.
 *
 * Delete used to sit in the row itself, a red word one button away from
 * "Case ekle" -- the action people reach for most, next to the one they can
 * least afford to hit by accident. It lives here now: one click further,
 * still easy to find, and still behind the confirmation dialog.
 */
export function MoreMenu({ items, title = 'Diğer işlemler' }: {
  items: MoreItem[]
  title?: string
}) {
  const [open, setOpen] = useState(false)
  const box = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const away = (e: MouseEvent) => {
      if (!box.current?.contains(e.target as Node)) setOpen(false)
    }
    const escape = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', away)
    document.addEventListener('keydown', escape)
    return () => {
      document.removeEventListener('mousedown', away)
      document.removeEventListener('keydown', escape)
    }
  }, [open])

  return (
    <div className="moremenu" ref={box}>
      <button className="ghost icon-only" title={title} aria-label={title}
              aria-haspopup="menu" aria-expanded={open}
              onClick={() => setOpen(!open)}>
        <Icon name="more" size={16} strokeWidth={3} />
      </button>
      {open && (
        <div className="moremenu-list" role="menu">
          {items.map((item) => (
            <button key={item.label} role="menuitem"
                    className={item.danger ? 'danger' : ''}
                    onClick={() => { setOpen(false); item.onClick() }}>
              {item.icon && <Icon name={item.icon} size={14} />}
              {item.label}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
