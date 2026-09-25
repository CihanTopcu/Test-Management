import { useState } from 'react'
import { useDashboard } from '../api/hooks'
import { ActivityByUser } from '../components/ActivityByUser'
import { Icon } from '../components/Icon'
import { MiniBar, statusColor } from '../components/Status'
import { useCatalog } from '../api/hooks'
import { href } from '../route'

/**
 * Every project on one page.
 *
 * With 16 projects the only way to compare them was to open each overview in
 * turn, which is why nobody did. Archived runs are excluded throughout: they
 * are release history, and counting them would make a finished project look
 * as busy as a running one.
 */

type SortKey = 'name' | 'cases' | 'tests' | 'pass_rate' | 'results_in_window'
  | 'active_runs'

export function Dashboard() {
  const [days, setDays] = useState(30)
  const [sort, setSort] = useState<SortKey>('results_in_window')
  const { data, isLoading } = useDashboard(days)
  const { data: catalog } = useCatalog()

  if (isLoading || !data) {
    return <main className="main"><div className="skeleton" style={{ width: 300 }} /></main>
  }

  const rows = [...data.projects].sort((a, b) => {
    if (sort === 'name') return a.name.localeCompare(b.name, 'tr')
    const x = (a[sort] ?? -1) as number
    const y = (b[sort] ?? -1) as number
    return y - x
  })

  const busiest = rows.filter((p) => p.results_in_window > 0).length

  return (
    <main className="main">
      <div className="page-title">
        <h1>Tüm Projeler</h1>
        <span className="faint small">
          son {days} günde {busiest} projede hareket var
        </span>
        <div className="right row" style={{ gap: 6 }}>
          <select value={days} onChange={(e) => setDays(Number(e.target.value))}>
            <option value={7}>Son 7 gün</option>
            <option value={30}>Son 30 gün</option>
            <option value={90}>Son 90 gün</option>
          </select>
        </div>
      </div>

      <div className="cards six" style={{ marginBottom: 16 }}>
        {[
          { n: data.totals.projects, k: 'proje' },
          { n: data.totals.cases, k: 'test case' },
          { n: data.totals.active_runs, k: 'devam eden koşum' },
          { n: data.totals.results_in_window, k: `son ${days} günde sonuç` },
          { n: data.totals.open_milestones, k: 'açık milestone' },
          { n: data.totals.overdue_milestones, k: 'geciken milestone',
            bad: data.totals.overdue_milestones > 0 },
        ].map((card) => (
          <div className="panel tile" key={card.k}>
            <div className="n" style={card.bad ? { color: 'var(--danger)' } : undefined}>
              {card.n.toLocaleString('tr-TR')}
            </div>
            <div className="k">{card.k}</div>
          </div>
        ))}
      </div>

      <div className="barkey">
        <span className="eyebrow">Durum çubuğu</span>
        <span><i style={{ background: statusColor(catalog, 1) }} />geçti</span>
        <span><i style={{ background: statusColor(catalog, 5) }} />kaldı</span>
        <span><i style={{ background: statusColor(catalog, 4) }} />diğer sonuç</span>
        <span><i style={{ background: statusColor(catalog, 3) }} />sonuçsuz</span>
      </div>
      <div className="panel" style={{ overflow: 'auto' }}>
        <table>
          <thead>
            <tr>
              {([
                ['name', 'Proje', 'left'],
                ['cases', 'Case', 'right'],
                ['active_runs', 'Devam eden', 'right'],
                ['tests', 'Test', 'right'],
                ['pass_rate', 'Geçme', 'right'],
              ] as [SortKey, string, string][]).map(([key, label, align]) => (
                <th key={key} style={{
                  cursor: 'pointer',
                  textAlign: align === 'right' ? 'right' : 'left',
                  width: key === 'name' ? undefined : 110,
                }} onClick={() => setSort(key)}>
                  {label}{sort === key && ' ▾'}
                </th>
              ))}
              <th style={{ width: 170 }}>Durum</th>
              <th style={{ width: 120, textAlign: 'right', cursor: 'pointer' }}
                  onClick={() => setSort('results_in_window')}>
                {days} gün{sort === 'results_in_window' && ' ▾'}
              </th>
              <th style={{ width: 130 }}>Milestone</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((p) => (
              <tr key={p.project_id} onClick={() => {
                location.hash = href({ page: 'overview', project: p.project_id })
              }}>
                <td className="title">
                  {p.name}
                  {p.is_completed && (
                    <span className="badge soft" style={{ marginLeft: 6 }}>kapalı</span>
                  )}
                </td>
                <td style={{ textAlign: 'right' }}>{p.cases.toLocaleString('tr-TR')}</td>
                <td style={{ textAlign: 'right' }}>
                  {p.active_runs || <span className="faint">—</span>}
                </td>
                <td style={{ textAlign: 'right' }}>
                  {p.tests ? p.tests.toLocaleString('tr-TR') : <span className="faint">—</span>}
                </td>
                <td style={{ textAlign: 'right' }}>
                  {p.pass_rate === null ? <span className="faint">—</span> : (
                    <b style={{ color: p.pass_rate >= 80 ? 'var(--ok)'
                      : p.pass_rate >= 50 ? 'var(--warn)' : 'var(--danger)' }}>
                      {p.pass_rate}%
                    </b>
                  )}
                </td>
                <td>
                  {p.tests > 0 && (
                    <MiniBar catalog={catalog} run={{
                      test_count: p.tests,
                      passed_count: p.passed,
                      // without it every failure fell into the amber "other"
                      // slice, and a red project looked merely unfinished
                      failed_count: p.failed,
                      untested_count: p.untested,
                    }} />
                  )}
                </td>
                <td style={{ textAlign: 'right' }}>
                  {p.results_in_window
                    ? p.results_in_window.toLocaleString('tr-TR')
                    : <span className="faint">—</span>}
                </td>
                <td className="small muted">
                  {p.open_milestones > 0 ? `${p.open_milestones} açık` : '—'}
                  {p.overdue_milestones > 0 && (
                    <span style={{ color: 'var(--danger)' }}>
                      {' '}<Icon name="warning" size={11} /> {p.overdue_milestones}
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="faint small" style={{ marginTop: 10 }}>
        Sayılar arşivlenmiş koşumları içermez.
      </div>

      <ActivityByUser />
    </main>
  )
}
