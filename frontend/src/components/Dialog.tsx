import { useEffect, useRef, type ReactNode } from 'react'
import { Icon } from './Icon'

/**
 * Modal built on <dialog>, so the browser handles focus trapping, Escape and
 * the top layer instead of us reimplementing them badly.
 */
export function Dialog({ open, title, onClose, children, footer, width = 520 }: {
  open: boolean
  title: string
  onClose: () => void
  children: ReactNode
  footer?: ReactNode
  width?: number
}) {
  const ref = useRef<HTMLDialogElement>(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    if (open && !el.open) el.showModal()
    if (!open && el.open) el.close()
  }, [open])

  return (
    <dialog ref={ref} className="modal" style={{ width }}
            onCancel={(e) => { e.preventDefault(); onClose() }}
            onClick={(e) => { if (e.target === ref.current) onClose() }}>
      <div className="modal-head">
        <b>{title}</b>
        <button type="button" className="ghost icon-only right" onClick={onClose}>
          <Icon name="close" size={15} />
        </button>
      </div>
      <div className="modal-body">{children}</div>
      {footer && <div className="modal-foot">{footer}</div>}
    </dialog>
  )
}
