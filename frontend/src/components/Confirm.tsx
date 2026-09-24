import { Dialog } from './Dialog'
import { Icon } from './Icon'

/**
 * A destructive action never happens on one click.
 *
 * Everything in here is the team's own record of five years of testing, and
 * several of the deletes reach further than they look -- a run takes its
 * results with it, a section takes its cases -- so the dialog says what will
 * go, not just "are you sure".
 */
export function Confirm({ open, title, detail, danger = true, busy, error,
                          confirmLabel = 'Sil', onConfirm, onClose }: {
  open: boolean
  title: string
  detail?: string
  danger?: boolean
  busy?: boolean
  error?: string | null
  confirmLabel?: string
  onConfirm: () => void
  onClose: () => void
}) {
  return (
    <Dialog open={open} title={title} onClose={onClose} width={460}
            footer={<>
              <button onClick={onClose}>Vazgeç</button>
              <button className={danger ? 'danger-solid' : 'primary'}
                      disabled={busy} onClick={onConfirm}>
                {busy ? 'Siliniyor…' : confirmLabel}
              </button>
            </>}>
      <div className="row" style={{ gap: 12, alignItems: 'flex-start' }}>
        {danger && (
          <span style={{ color: 'var(--danger)', flexShrink: 0, marginTop: 2 }}>
            <Icon name="warning" size={20} />
          </span>
        )}
        <div>
          <div>{detail ?? 'Bu işlem geri alınamaz.'}</div>
          {error && <div className="error" style={{ marginTop: 10 }}>{error}</div>}
        </div>
      </div>
    </Dialog>
  )
}
