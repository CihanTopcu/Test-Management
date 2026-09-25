import { useMemo, useState } from 'react'
import {
  useActivitySeries, useCatalog, useCoverage, useDefects, useDistribution,
  useMilestoneProgress, usePassTrend,
} from '../api/hooks'
import type { Catalog } from '../api/types'
import { StackBar, TrendChart } from '../components/Charts'
import { Icon } from '../components/Icon'
import { inkOn, statusColor, statusLabel } from '../components/Status'
import { QualityReport } from '../components/QualityReport'
import { href, type Route } from '../route'
import { Crumbs } from '../components/Crumbs'

/** Time windows for the charts over time: one choice, above them, for both. */
const RANGES = [
  { key: '3a', label: 'Son 3 ay', days: 90, weeks: 13 },
  { key: '6a', label: 'Son 6 ay', days: 180, weeks: 26 },
  { key: '12a', label: 'Son 12 ay', days: 365, weeks: 52 },
]

const shortDate = (iso: string) =>
  new Date(iso).toLocaleDateString('tr-TR', { day: 'numeric', month: 'short' })

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
                             // one measure per bar, each bar labelled: a hue per bar carried
                             // nothing but noise
                             background: colorAt?.(i) ?? 'var(--accent)' }} />
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
function Activity({ route, days }: { route: Route; days: number }) {
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

/** Of the verdicts entered each week, the share that passed. */
function PassTrend({ route, weeks }: { route: Route; weeks: number }) {
  const { data = [], isFetching } = usePassTrend(route.project, weeks)
  const [asTable, setAsTable] = useState(false)
  const tested = data.filter((w) => w.results > 0)
  const latest = tested[tested.length - 1]

  return (
    <div className="panel report-card" style={{ opacity: isFetching ? 0.6 : 1 }}>
      <div className="row" style={{ marginBottom: 4 }}>
        <h3 style={{ margin: 0 }}>Geçme oranı trendi</h3>
        <button className="ghost small right" onClick={() => setAsTable(!asTable)}>
          {asTable ? 'Grafik' : 'Tablo'}
        </button>
      </div>
      <div className="small muted" style={{ marginBottom: 12 }}>
        Her hafta girilen sonuçlardan geçenlerin oranı. Sonuç girilmeyen
        haftalar boşluk olarak kalır, sıfır sayılmaz.
        {latest && <> Son ölçüm: <b>%{latest.pass_rate}</b> ({shortDate(latest.week)} haftası,
          {' '}{latest.results.toLocaleString('tr-TR')} sonuç).</>}
      </div>

      {tested.length === 0 ? (
        <span className="faint small">Bu dönemde sonuç girilmemiş.</span>
      ) : asTable ? (
        <div style={{ maxHeight: 280, overflow: 'auto' }}>
          <table className="grid">
            <thead>
              <tr>
                <th>Hafta</th>
                <th style={{ textAlign: 'right' }}>Sonuç</th>
                <th style={{ textAlign: 'right' }}>Geçti</th>
                <th style={{ textAlign: 'right' }}>Kaldı</th>
                <th style={{ textAlign: 'right' }}>Diğer</th>
                <th style={{ textAlign: 'right' }}>Geçme</th>
              </tr>
            </thead>
            <tbody>
              {[...tested].reverse().map((w) => (
                <tr key={w.week} style={{ cursor: 'default' }}>
                  <td>{shortDate(w.week)}</td>
                  <td style={{ textAlign: 'right' }}>{w.results.toLocaleString('tr-TR')}</td>
                  <td style={{ textAlign: 'right' }}>{w.passed.toLocaleString('tr-TR')}</td>
                  <td style={{ textAlign: 'right' }}>{w.failed.toLocaleString('tr-TR')}</td>
                  <td style={{ textAlign: 'right' }}>{w.other.toLocaleString('tr-TR')}</td>
                  <td style={{ textAlign: 'right' }}><b>%{w.pass_rate}</b></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <TrendChart
          ariaLabel={`Haftalık geçme oranı, son ${weeks} hafta`}
          points={data.map((w) => ({
            label: shortDate(w.week),
            value: w.pass_rate,
            detail: w.results
              ? [`${w.results.toLocaleString('tr-TR')} sonuç`,
                 `${w.passed} geçti · ${w.failed} kaldı${w.other ? ` · ${w.other} diğer` : ''}`]
              : ['bu hafta sonuç girilmedi'],
          }))}
          // a label at each month's first week
          tickLabel={(_label, i) => {
            const month = new Date(data[i].week).getMonth()
            return i === 0 || new Date(data[i - 1].week).getMonth() !== month
              ? new Date(data[i].week).toLocaleDateString('tr-TR', { month: 'short' })
              : null
          }} />
      )}
    </div>
  )
}

function verdictSegments(catalog: Catalog | undefined, c: {
  passed: number; failed: number; other: number; untested: number
}) {
  return [
    { key: 'passed', label: 'Geçti', count: c.passed, color: statusColor(catalog, 1) },
    { key: 'failed', label: 'Kaldı', count: c.failed, color: statusColor(catalog, 5) },
    { key: 'other', label: 'Diğer sonuç', count: c.other, color: statusColor(catalog, 4) },
    { key: 'untested', label: 'Sonuçsuz', count: c.untested, color: statusColor(catalog, 3) },
  ]
}

/** Each open milestone: its date, and its tests by verdict. */
function MilestoneProgressCard({ route }: { route: Route }) {
  const { data = [] } = useMilestoneProgress(route.project)
  const { data: catalog } = useCatalog()
  const withRuns = data.filter((m) => m.total > 0)
  const empty = data.filter((m) => m.total === 0)

  return (
    <div className="panel report-card">
      <div className="row" style={{ marginBottom: 6 }}>
        <h3 style={{ margin: 0 }}>Milestone ilerlemesi</h3>
        <span className="faint small right">açık milestone’lar, alt milestone’lar dahil</span>
      </div>
      {data.length === 0 ? (
        <span className="faint small">Açık milestone yok.</span>
      ) : (
        <>
          <div className="barkey" style={{ margin: '4px 0 6px' }}>
            {verdictSegments(catalog, { passed: 0, failed: 0, other: 0, untested: 0 }).map((seg) => (
              <span key={seg.key}><i style={{ background: seg.color }} />{seg.label.toLowerCase()}</span>
            ))}
          </div>
          {withRuns.map((m) => (
            <div className="msrow" key={m.id}>
              <div className="name">
                <a href={href({ page: 'milestones', project: route.project, milestone: m.id })}>
                  {m.name}
                </a>
                <div className={`when ${m.overdue ? 'late' : ''}`}>
                  {m.overdue && <Icon name="warning" size={12} />}{' '}
                  {m.due_on
                    ? `${m.overdue ? 'gecikmiş · ' : ''}bitiş ${new Date(m.due_on).toLocaleDateString('tr-TR')}`
                    : 'tarih yok'}
                </div>
              </div>
              <div className="bar">
                <StackBar total={m.total} segments={verdictSegments(catalog, m)}
                          ariaLabel={`${m.name}: ${m.passed} geçti, ${m.failed} kaldı, ${m.other} diğer, ${m.untested} sonuçsuz`} />
              </div>
              <div className="figure">
                <b>%{m.pass_rate ?? 0}</b> geçti
                <div className="faint">
                  {m.total.toLocaleString('tr-TR')} test · {m.runs} koşum
                </div>
              </div>
            </div>
          ))}
          {empty.length > 0 && (
            <div className="faint small" style={{ marginTop: 10 }}>
              {empty.length} milestone’a henüz koşum bağlanmamış:{' '}
              {empty.slice(0, 6).map((m) => m.name).join(', ')}
              {empty.length > 6 && ` ve ${empty.length - 6} tane daha`}.
            </div>
          )}
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
  const [range, setRange] = useState(RANGES[1])

  /** Where a chart sends you: the filtered case list, in the address bar. */
  const explore = (filters: Record<string, string>) =>
    href({ page: 'cases', project: route.project, filters })

  return (
    <main className="main">
      <Crumbs projectId={route.project} projectName={projectName} />
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

      <div style={{ marginBottom: 14 }}>
        <MilestoneProgressCard route={route} />
      </div>

      {/* one time window, above the charts it scopes */}
      <div className="section-rule">
        Zaman içinde
        <div className="chiprow" style={{ order: 2 }}>
          {RANGES.map((r) => (
            <button key={r.key} className={`chip-toggle ${range.key === r.key ? 'on' : ''}`}
                    onClick={() => setRange(r)}>{r.label}</button>
          ))}
        </div>
      </div>
      <div style={{ marginBottom: 14 }}>
        <PassTrend route={route} weeks={range.weeks} />
      </div>
      <div style={{ marginBottom: 14 }}>
        <Activity route={route} days={range.days} />
      </div>

      <div className="section-rule">Case kütüphanesi</div>
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
            // fixed layout: with auto columns a long test title pushed the
            // count and the link out past the edge of the card
            <table className="grid">
              <tbody>
                {defects.items.slice(0, 12).map((d) => (
                  <tr key={d.ref} style={{ cursor: 'default' }}>
                    <td style={{ width: 110 }}><b>{d.ref}</b></td>
                    <td className="small muted ellipsis" title={d.tests[0]?.title}>
                      {d.tests.length > 1 && <span className="faint">+{d.tests.length - 1} · </span>}
                      {d.tests[0]?.title}
                    </td>
                    <td className="nowrap" style={{ width: 64, textAlign: 'right' }}>
                      <span className="badge"
                            style={{ background: statusColor(catalog, d.tests[0]?.status_id),
                                     color: inkOn(statusColor(catalog, d.tests[0]?.status_id)) }}>
                        {d.count}
                      </span>
                    </td>
                    <td className="nowrap" style={{ width: 76 }}>
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
