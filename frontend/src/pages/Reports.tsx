import { useMemo, useState } from 'react'
import {
  useActivitySeries, useCatalog, useCoverage, useDefects, useDistribution,
} from '../api/hooks'
import { statusColor, statusLabel } from '../components/Status'
import { QualityReport } from '../components/QualityReport'
import { href, type Route } from '../route'

const PALETTE = ['#1c6ea4', '#6ca644', '#d99a2b', '#a9457c', '#4a8fb5',
                 '#8a8a8a', '#5c7cb0', '#b8703f']

/** A bar is a question with an answer behind it, so it becomes a link
 *  wherever the caller can say where that answer lives. */
function Bars({ buckets, total, colorAt, linkAt }: {
  buckets: { label: string; count: number }[]
  total: number
  colorAt?: (i: number) => string
  linkAt?: (i: number) => string | undefined
}) {
  const max = Math.max(1, ...buckets.map((b) => b.count))
  return (
    <div className="hbars">
      {buckets.map((b, i) => {
        const to = linkAt?.(i)
        const inner = (
          <>
            <span className="lbl" title={b.label}>{b.label}</span>
            <span className="track">
              <span className="fill"
                    style={{ width: `${(b.count / max) * 100}%`,
                             background: colorAt?.(i) ?? PALETTE[i % PALETTE.length] }} />
            </span>
            <span className="val">
              {b.count.toLocaleString('tr-TR')}
              <span className="faint"> {total ? Math.round((b.count / total) * 100) : 0}%</span>
            </span>
          </>
        )
        return to
          ? <a className="hbar linked" key={b.label} href={to}>{inner}</a>
          : <div className="hbar" key={b.label}>{inner}</div>
      })}
      {buckets.length === 0 && <span className="faint small">Veri yok.</span>}
    </div>
  )
}

/** Stacked daily columns. A real chart library would be a lot of bytes for
 *  one bar chart that only ever shows counts per day. */
function Activity({ route }: { route: Route }) {
  const [days, setDays] = useState(120)
  const { data: series = [] } = useActivitySeries(route.project, days)
  const { data: catalog } = useCatalog()

  const max = Math.max(1, ...series.map(
    (p) => Object.values(p.values).reduce((a, b) => a + b, 0)))
  const statuses = useMemo(() => {
    const seen = new Set<string>()
    series.forEach((p) => Object.keys(p.values).forEach((k) => seen.add(k)))
    return [...seen]
  }, [series])

  return (
    <div className="panel report-card">
      <div className="row" style={{ marginBottom: 10 }}>
        <h3 style={{ margin: 0 }}>Sonuç girişi (günlük)</h3>
        <div className="right chiprow">
          {[30, 120, 365].map((d) => (
            <button key={d} className={`chip-toggle ${days === d ? 'on' : ''}`}
                    onClick={() => setDays(d)}>{d} gün</button>
          ))}
        </div>
      </div>

      {series.length === 0 ? (
        <span className="faint small">Bu aralıkta sonuç girilmemiş.</span>
      ) : (
        <>
          <div className="spark">
            {series.map((p) => {
              const sum = Object.values(p.values).reduce((a, b) => a + b, 0)
              return (
                <div className="col" key={p.label}
                     style={{ height: `${(sum / max) * 100}%` }}
                     title={`${p.label}: ${sum}`}>
                  {Object.entries(p.values).map(([k, n]) => (
                    <span key={k}
                          style={{
                            height: `${(n / sum) * 100}%`,
                            background: statusColor(
                              catalog, k === 'untested' ? null : Number(k)),
                          }} />
                  ))}
                </div>
              )
            })}
          </div>
          <div className="row small faint" style={{ marginTop: 8, gap: 14, flexWrap: 'wrap' }}>
            <span>{series[0].label}</span>
            <span className="right">{series[series.length - 1].label}</span>
          </div>
          <div className="legend" style={{ marginTop: 10 }}>
            {statuses.map((k) => (
              <div key={k}>
                <i style={{ background: statusColor(catalog, k === 'untested' ? null : Number(k)) }} />
                <span>{statusLabel(catalog, k === 'untested' ? null : Number(k))}</span>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

export function Reports({ route, projectName }: { route: Route; projectName: string }) {
  const { data: byType } = useDistribution(route.project, 'type')
  const { data: byPriority } = useDistribution(route.project, 'priority')
  const { data: coverage } = useCoverage(route.project)
  const { data: defects } = useDefects(route.project)
  const { data: catalog } = useCatalog()

  /** Where a chart sends you: the filtered case list, in the address bar. */
  const explore = (filters: Record<string, string>) =>
    href({ page: 'cases', project: route.project, filters })

  return (
    <main className="main">
      <div className="crumbs"><b>{projectName}</b></div>
      <div className="page-title">
        <h1>Raporlar</h1>
        <span className="faint small">Canlı veriden üretilir</span>
      </div>

      {coverage && (
        <div className="cards" style={{ marginBottom: 14 }}>
          {[
            { n: coverage.cases, k: 'toplam case', to: explore({}) },
            { n: coverage.with_refs, k: 'gereksinime bağlı',
              sub: coverage.cases ? Math.round((coverage.with_refs / coverage.cases) * 100) : 0,
              to: explore({ refs: 'with' }) },
            { n: coverage.executed, k: 'en az bir kez koşulmuş',
              sub: coverage.cases ? Math.round((coverage.executed / coverage.cases) * 100) : 0,
              to: explore({ executed: 'yes', sort: 'runs' }) },
            { n: defects?.total ?? 0, k: 'farklı hata kaydı',
              to: undefined as string | undefined },
          ].map((t) => {
            const inner = (
              <>
                <div className="n">
                  {t.n.toLocaleString('tr-TR')}
                  {t.sub !== undefined && <span className="faint" style={{ fontSize: 15 }}> · %{t.sub}</span>}
                </div>
                <div className="k">{t.k}</div>
              </>
            )
            return t.to
              ? <a className="panel tile lift linked" key={t.k} href={t.to}>{inner}</a>
              : <div className="panel tile lift" key={t.k}>{inner}</div>
          })}
        </div>
      )}

      {/* The two numbers this library is judged on. They were only ever
          readable as their complement -- "11% linked" says nothing about
          which 89% to go and fix. */}
      {coverage && coverage.cases > 0 && (
        <div className="cards" style={{ marginBottom: 14 }}>
          <a className="panel tile lift linked gap" href={explore({ executed: 'no' })}>
            <div className="n">
              {(coverage.cases - coverage.executed).toLocaleString('tr-TR')}
              <span className="faint" style={{ fontSize: 15 }}>
                {' · %'}{Math.round(100 * (coverage.cases - coverage.executed) / coverage.cases)}
              </span>
            </div>
            <div className="k">hiç koşulmamış case</div>
          </a>
          <a className="panel tile lift linked gap" href={explore({ refs: 'without' })}>
            <div className="n">
              {(coverage.cases - coverage.with_refs).toLocaleString('tr-TR')}
              <span className="faint" style={{ fontSize: 15 }}>
                {' · %'}{Math.round(100 * (coverage.cases - coverage.with_refs) / coverage.cases)}
              </span>
            </div>
            <div className="k">gereksinime bağlı olmayan case</div>
          </a>
        </div>
      )}

      <div className="cards" style={{ marginBottom: 14 }}>
        <div className="panel report-card">
          <h3>{byType?.title ?? 'Case tipi dağılımı'}</h3>
          <Bars buckets={byType?.buckets ?? []} total={byType?.total ?? 0}
                linkAt={(i) => {
                  const id = byType?.buckets[i]?.id
                  return id == null ? undefined : explore({ type_id: String(id) })
                }} />
        </div>
        <div className="panel report-card">
          <h3>{byPriority?.title ?? 'Öncelik dağılımı'}</h3>
          <Bars buckets={byPriority?.buckets ?? []} total={byPriority?.total ?? 0}
                linkAt={(i) => {
                  const id = byPriority?.buckets[i]?.id
                  return id == null ? undefined : explore({ priority_id: String(id) })
                }} />
        </div>
      </div>

      <div style={{ marginBottom: 14 }}>
        <Activity route={route} />
      </div>

      <div className="cards">
        <div className="panel report-card">
          <h3>Suite başına case sayısı</h3>
          <Bars buckets={(coverage?.by_suite ?? []).slice(0, 12)}
                total={coverage?.cases ?? 0}
                linkAt={(i) => {
                  const id = coverage?.by_suite[i]?.id
                  return id == null ? undefined : explore({ suite_id: String(id) })
                }} />
        </div>

        <div className="panel report-card">
          <h3>En çok görülen hata kayıtları</h3>
          {!defects || defects.items.length === 0 ? (
            <span className="faint small">
              Sonuçlarda hata referansı girilmemiş.
            </span>
          ) : (
            <table>
              <tbody>
                {defects.items.slice(0, 12).map((d) => (
                  <tr key={d.ref} style={{ cursor: 'default' }}>
                    <td style={{ width: 130 }}><b>{d.ref}</b></td>
                    <td className="small muted">
                      {d.tests[0]?.title?.slice(0, 60)}
                      {d.tests.length > 1 && <span className="faint"> +{d.tests.length - 1}</span>}
                    </td>
                    <td className="nowrap" style={{ width: 70, textAlign: 'right' }}>
                      <span className="badge"
                            style={{ background: statusColor(catalog, d.tests[0]?.status_id) }}>
                        {d.count}
                      </span>
                    </td>
                    <td style={{ width: 70 }}>
                      {d.tests[0] && (
                        <a className="small"
                           href={href({ page: 'runs', project: route.project,
                                        run: d.tests[0].run_id })}>koşum</a>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      <QualityReport projectId={route.project} />
    </main>
  )
}
