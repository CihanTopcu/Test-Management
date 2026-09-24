import type { Catalog } from '../api/types'

/**
 * Status colours come from the catalog, never from a table in the code.
 *
 * This instance defines ten statuses -- Passed, Failed, Retouch, Testing,
 * Deferred, Blocked, Aborted, Cancelled, NoRun, Untested -- five of which are
 * custom, and an admin can add another tomorrow. The hex values are the ones
 * TestRail itself painted them with, imported along with everything else.
 */
export function statusColor(catalog: Catalog | undefined, id: number | null | undefined) {
  if (id == null) return 'var(--untested)'
  return catalog?.statuses.find((s) => s.id === id)?.color ?? 'var(--untested)'
}

export function statusLabel(catalog: Catalog | undefined, id: number | null | undefined) {
  if (id == null) return 'Untested'
  return catalog?.statuses.find((s) => s.id === id)?.label ?? `#${id}`
}

export function StatusBadge({ catalog, id }: { catalog?: Catalog; id: number | null }) {
  return (
    <span className="badge" style={{ background: statusColor(catalog, id) }}>
      {statusLabel(catalog, id)}
    </span>
  )
}

interface Slice { id: number | null; label: string; count: number; color: string }

export function slices(catalog: Catalog | undefined,
                       byStatus: Record<string, number>): Slice[] {
  return Object.entries(byStatus)
    .map(([key, count]) => {
      const id = key === 'untested' ? null : Number(key)
      return { id, count, label: statusLabel(catalog, id), color: statusColor(catalog, id) }
    })
    .filter((s) => s.count > 0)
    .sort((a, b) => b.count - a.count)
}

/** Donut drawn with stroke-dasharray: no chart library for one ring. */
export function Donut({ data, size = 150 }: { data: Slice[]; size?: number }) {
  const total = data.reduce((sum, s) => sum + s.count, 0)
  const r = size / 2 - 14
  const circumference = 2 * Math.PI * r
  let offset = 0

  if (!total) {
    return (
      <svg width={size} height={size} role="img" aria-label="veri yok">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none"
                stroke="var(--border)" strokeWidth={22} />
      </svg>
    )
  }

  return (
    <svg width={size} height={size} role="img"
         aria-label={data.map((s) => `${s.label} ${s.count}`).join(', ')}>
      <g transform={`rotate(-90 ${size / 2} ${size / 2})`}>
        {data.map((s) => {
          const len = (s.count / total) * circumference
          const dash = `${len} ${circumference - len}`
          const el = (
            <circle key={s.label} cx={size / 2} cy={size / 2} r={r} fill="none"
                    stroke={s.color} strokeWidth={22}
                    strokeDasharray={dash} strokeDashoffset={-offset}>
              <title>{`${s.label}: ${s.count}`}</title>
            </circle>
          )
          offset += len
          return el
        })}
      </g>
    </svg>
  )
}

export function Legend({ data, total, onPick, active }: {
  data: Slice[]
  total: number
  onPick?: (id: number | null) => void
  active?: number | null
}) {
  return (
    <div className="legend">
      {data.map((s) => (
        <div key={s.label}
             style={{ cursor: onPick ? 'pointer' : undefined,
                      opacity: active !== undefined && active !== null && active !== s.id ? 0.45 : 1 }}
             onClick={() => onPick?.(s.id)}>
          <i style={{ background: s.color }} />
          <b>{s.count.toLocaleString('tr-TR')}</b>
          <span>{s.label}</span>
          <span className="pct">({total ? Math.round((s.count / total) * 100) : 0}%)</span>
        </div>
      ))}
    </div>
  )
}

export function MiniBar({ run, catalog }: {
  run: { test_count: number; passed_count: number; untested_count: number }
  catalog?: Catalog
}) {
  const total = run.test_count || 1
  const failed = Math.max(0, run.test_count - run.passed_count - run.untested_count)
  const parts = [
    { w: run.passed_count / total, c: statusColor(catalog, 1) },
    { w: failed / total, c: statusColor(catalog, 5) },
    { w: run.untested_count / total, c: statusColor(catalog, 3) },
  ]
  return (
    <span className="mini-bar">
      {parts.map((p, i) => (
        <span key={i} style={{ width: `${p.w * 100}%`, background: p.c }} />
      ))}
    </span>
  )
}
