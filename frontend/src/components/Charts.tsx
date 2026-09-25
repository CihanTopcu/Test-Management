import { useEffect, useRef, useState } from 'react'

/**
 * The few charts DGTest draws, in plain SVG.
 *
 * No chart library: the server may have no internet, and three shapes do
 * not justify one. They follow one set of rules so they read as a family --
 * thin marks (2px lines, bars no taller than they need to be), hairline
 * solid gridlines, a single y-axis, text in text colours rather than the
 * series colour, a gap for "no data" rather than a false zero, and a hover
 * readout that is never the only way to a value.
 */

/** Width of an element, kept current; SVG then draws at real pixels. */
function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null)
  const [width, setWidth] = useState(0)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const observer = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width))
    observer.observe(el)
    setWidth(el.getBoundingClientRect().width)
    return () => observer.disconnect()
  }, [])
  return [ref, width] as const
}

export interface TrendPoint {
  /** x label, e.g. the week's Monday */
  label: string
  /** null = nothing to measure; drawn as a gap */
  value: number | null
  /** extra lines for the readout, value first */
  detail?: string[]
}

/**
 * A single series over time, 0–100 by default. One series needs no legend:
 * the card's title says what it is.
 */
export function TrendChart({ points, height = 200, max = 100, unit = '%',
                             ariaLabel, tickLabel }: {
  points: TrendPoint[]
  height?: number
  max?: number
  unit?: string
  ariaLabel: string
  /** which x labels to print; default: every ~6th */
  tickLabel?: (label: string, index: number) => string | null
}) {
  const [box, width] = useWidth<HTMLDivElement>()
  const [hover, setHover] = useState<number | null>(null)
  const pad = { top: 12, right: 16, bottom: 26, left: 38 }
  const w = Math.max(0, width - pad.left - pad.right)
  const h = height - pad.top - pad.bottom
  const n = points.length
  const x = (i: number) => pad.left + (n <= 1 ? w / 2 : (i / (n - 1)) * w)
  const y = (v: number) => pad.top + h - (v / max) * h

  // one path per run of consecutive values: a null breaks the line
  const runs: { i: number; v: number }[][] = []
  points.forEach((p, i) => {
    if (p.value == null) return
    const last = runs[runs.length - 1]
    if (last && last[last.length - 1].i === i - 1) last.push({ i, v: p.value })
    else runs.push([{ i, v: p.value }])
  })
  const line = (run: { i: number; v: number }[]) =>
    run.map((p, k) => `${k ? 'L' : 'M'}${x(p.i).toFixed(1)},${y(p.v).toFixed(1)}`).join('')
  const area = (run: { i: number; v: number }[]) =>
    `${line(run)}L${x(run[run.length - 1].i).toFixed(1)},${y(0)}L${x(run[0].i).toFixed(1)},${y(0)}Z`
  const lastValued = [...points].map((p, i) => ({ p, i })).reverse().find((e) => e.p.value != null)

  const nearest = (clientX: number) => {
    const rect = box.current?.getBoundingClientRect()
    if (!rect || n === 0) return null
    const rel = clientX - rect.left - pad.left
    return Math.max(0, Math.min(n - 1, Math.round((rel / Math.max(w, 1)) * (n - 1))))
  }
  const ticks = tickLabel ?? ((label: string, i: number) =>
    i % Math.max(1, Math.round(n / 6)) === 0 ? label : null)
  const shown = hover != null ? points[hover] : null

  return (
    <div ref={box} className="chart" style={{ height }}
         tabIndex={0} role="img" aria-label={ariaLabel}
         onPointerMove={(e) => setHover(nearest(e.clientX))}
         onPointerLeave={() => setHover(null)}
         onBlur={() => setHover(null)}
         onKeyDown={(e) => {
           if (e.key === 'ArrowRight') setHover((h) => Math.min(n - 1, (h ?? -1) + 1))
           if (e.key === 'ArrowLeft') setHover((h) => Math.max(0, (h ?? n) - 1))
         }}>
      {width > 0 && (
        <svg width={width} height={height} aria-hidden="true">
          {[0, 25, 50, 75, 100].filter((v) => v <= max).map((v) => (
            <g key={v}>
              <line className="grid" x1={pad.left} x2={pad.left + w} y1={y(v)} y2={y(v)} />
              <text className="axis" x={pad.left - 8} y={y(v)} dy="0.32em" textAnchor="end">
                {v}{unit}
              </text>
            </g>
          ))}
          {points.map((p, i) => {
            const label = ticks(p.label, i)
            return label ? (
              <text key={p.label} className="axis" x={x(i)} y={height - 8} textAnchor="middle">
                {label}
              </text>
            ) : null
          })}
          {runs.map((run, k) => <path key={`a${k}`} className="area" d={area(run)} />)}
          {runs.map((run, k) => (
            run.length === 1
              ? <circle key={`l${k}`} className="dot" cx={x(run[0].i)} cy={y(run[0].v)} r={3} />
              : <path key={`l${k}`} className="line" d={line(run)} />
          ))}
          {lastValued && hover == null && (
            <circle className="dot end" cx={x(lastValued.i)} cy={y(lastValued.p.value!)} r={4} />
          )}
          {hover != null && (
            <>
              <line className="crosshair" x1={x(hover)} x2={x(hover)} y1={pad.top} y2={pad.top + h} />
              {points[hover].value != null && (
                <circle className="dot end" cx={x(hover)} cy={y(points[hover].value!)} r={4} />
              )}
            </>
          )}
        </svg>
      )}
      {shown && hover != null && (() => {
        // beside the point it describes, inside the plot: above it when
        // there is room, below it when the point is near the top
        const anchor = shown.value != null ? y(shown.value) : pad.top + h / 2
        const below = anchor < 96
        return (
        <div className={`chart-tip ${below ? 'below' : ''}`}
             style={{ left: Math.min(Math.max(x(hover), 90), width - 90),
                      top: below ? anchor + 6 : anchor - 12 }}>
          <b>{shown.value == null ? 'sonuç yok' : `${shown.value.toLocaleString('tr-TR')}${unit}`}</b>
          <span>{shown.label}</span>
          {shown.detail?.map((d) => <span key={d} className="faint">{d}</span>)}
        </div>
        )
      })()}
    </div>
  )
}

/**
 * Twelve weeks in a table cell: the past in the recessive ink, the latest
 * value as an accent dot. Not a chart to read values from -- the column
 * beside it carries the number; this carries the direction.
 */
export function Sparkline({ values, width = 96, height = 24, label }: {
  values: (number | null)[]
  width?: number
  height?: number
  label: string
}) {
  const n = values.length
  if (!values.some((v) => v != null)) {
    return <span className="faint small" aria-label={label}>—</span>
  }
  const x = (i: number) => 3 + (i / Math.max(1, n - 1)) * (width - 6)
  const y = (v: number) => 3 + (height - 6) - (v / 100) * (height - 6)
  const segs: string[] = []
  let current = ''
  values.forEach((v, i) => {
    if (v == null) { if (current) segs.push(current); current = ''; return }
    current += `${current ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`
  })
  if (current) segs.push(current)
  const last = values.map((v, i) => ({ v, i })).reverse().find((e) => e.v != null)!
  return (
    <svg className="spark-line" width={width} height={height} role="img" aria-label={label}>
      <title>{label}</title>
      <line className="grid" x1={3} x2={width - 3} y1={y(50)} y2={y(50)} />
      {segs.map((d) => <path key={d} d={d} />)}
      {/* a lone point has no line to sit on, so every valued week gets a
          faint dot; the latest one is the accent */}
      {values.map((v, i) => v != null && i !== last.i
        ? <circle key={i} className="pt" cx={x(i)} cy={y(v)} r={1.6} /> : null)}
      <circle className="now" cx={x(last.i)} cy={y(last.v!)} r={3} />
    </svg>
  )
}

export interface Segment { key: string; label: string; count: number; color: string }

/** A 100% bar split by verdict, with a readout per segment. */
export function StackBar({ segments, total, ariaLabel }: {
  segments: Segment[]
  total: number
  ariaLabel: string
}) {
  const [tip, setTip] = useState<{ seg: Segment; left: number } | null>(null)
  const ref = useRef<HTMLDivElement>(null)
  const shown = segments.filter((s) => s.count > 0)
  if (!total) return <div className="stackbar empty" aria-label={ariaLabel} />
  return (
    <div ref={ref} className="stackbar" role="img" aria-label={ariaLabel}
         onPointerLeave={() => setTip(null)}>
      {shown.map((s) => (
        <span key={s.key} tabIndex={0}
              style={{ flexGrow: s.count, background: s.color }}
              aria-label={`${s.label}: ${s.count}`}
              onPointerEnter={(e) => {
                const box = ref.current!.getBoundingClientRect()
                const seg = (e.currentTarget as HTMLElement).getBoundingClientRect()
                setTip({ seg: s, left: seg.left - box.left + seg.width / 2 })
              }}
              onFocus={(e) => {
                const box = ref.current!.getBoundingClientRect()
                const seg = e.currentTarget.getBoundingClientRect()
                setTip({ seg: s, left: seg.left - box.left + seg.width / 2 })
              }}
              onBlur={() => setTip(null)} />
      ))}
      {tip && (
        <div className="chart-tip below" style={{ left: tip.left }}>
          <b>{tip.seg.count.toLocaleString('tr-TR')}</b>
          <span>{tip.seg.label} · %{Math.round((100 * tip.seg.count) / total)}</span>
        </div>
      )}
    </div>
  )
}
