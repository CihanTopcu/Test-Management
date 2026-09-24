import { useActivity, useCatalog, useMilestones, useProjectStats, useRuns, useUsers } from '../api/hooks'
import { Donut, Legend, MiniBar, StatusBadge, slices } from '../components/Status'
import { href, type Route } from '../route'

export function Overview({ route, projectName }: { route: Route; projectName: string }) {
  const { data: stats, isLoading } = useProjectStats(route.project)
  const { data: catalog } = useCatalog()
  const { data: runs = [] } = useRuns(route.project)
  const { data: milestones = [] } = useMilestones(route.project)
  const { data: activity = [] } = useActivity(route.project)
  const { data: users = [] } = useUsers()

  if (isLoading || !stats) {
    return <main className="main"><div className="skeleton" style={{ width: 280 }} /></main>
  }

  const data = slices(catalog, stats.by_status)
  const passed = stats.by_status['1'] ?? 0
  const untested = (stats.by_status['3'] ?? 0) + (stats.by_status['untested'] ?? 0)
  const pct = stats.tests ? Math.round((passed / stats.tests) * 100) : 0

  const openMilestones = milestones.filter((m) => !m.is_completed).slice(0, 6)
  const recentRuns = runs.slice(0, 6)

  return (
    <main className="main">
      <div className="page-title">
        <h1>{projectName}</h1>
        <span className="faint small">Proje özeti</span>
      </div>

      <div className="cards" style={{ marginBottom: 14 }}>
        {[
          { n: stats.suites, k: 'test suite' },
          { n: stats.cases, k: 'test case' },
          { n: stats.runs, k: `koşum (${stats.active_runs} açık)` },
          { n: stats.milestones, k: `milestone (${stats.open_milestones} açık)` },
        ].map((t) => (
          <div className="panel tile" key={t.k}>
            <div className="n">{t.n.toLocaleString('tr-TR')}</div>
            <div className="k">{t.k}</div>
          </div>
        ))}
      </div>

      <div className="panel" style={{ padding: 16, marginBottom: 14 }}>
        {stats.tests === 0 ? (
          <div className="faint">Bu projede henüz test koşumu yok.</div>
        ) : (
          <div className="donut-wrap">
            <Donut data={data} />
            <div className="pass-big">
              <div className="n">{pct}%</div>
              <div className="k">passed</div>
              <div className="k">
                {untested.toLocaleString('tr-TR')} / {stats.tests.toLocaleString('tr-TR')} untested
              </div>
            </div>
            <div style={{ flex: 1, minWidth: 260 }}>
              <Legend data={data} total={stats.tests} />
            </div>
          </div>
        )}
      </div>

      <div className="split" style={{ alignItems: 'flex-start' }}>
        <div className="list">
          <div className="section-rule">Son aktivite</div>
          <div className="panel">
            {activity.length === 0 && <div className="empty">Kayıtlı sonuç yok.</div>}
            <table>
              <tbody>
                {activity.map((a) => (
                  <tr key={`${a.test_id}-${a.created_on}`}
                      onClick={() => { location.hash = href({ page: 'runs', project: route.project, run: a.run_id, test: a.test_id }) }}>
                    <td style={{ width: 110 }}>
                      <StatusBadge catalog={catalog} id={a.status_id} />
                    </td>
                    <td className="title">
                      {a.test_title}
                      <div className="small faint">{a.run_name}</div>
                    </td>
                    <td className="small faint nowrap" style={{ width: 150 }}>
                      {users.find((u) => u.id === a.created_by)?.name ?? '—'}
                      <div>{new Date(a.created_on).toLocaleDateString('tr-TR')}</div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="detail" style={{ padding: 0, width: 420 }}>
          <div style={{ padding: '12px 14px' }}>
            <div className="section-rule" style={{ marginTop: 0 }}>Milestone’lar</div>
            {openMilestones.length === 0 ? (
              <div className="faint small">Açık milestone yok.</div>
            ) : openMilestones.map((m) => (
              <div key={m.id} className="row" style={{ padding: '6px 0' }}>
                <span>🏳</span>
                <span className="grow">{m.name}</span>
                <span className="right small faint nowrap">
                  {m.due_on ? new Date(m.due_on).toLocaleDateString('tr-TR') : 'tarih yok'}
                </span>
              </div>
            ))}

            <div className="section-rule">Test koşumları</div>
            {recentRuns.length === 0 ? (
              <div className="faint small">Bu projede koşum yok.</div>
            ) : recentRuns.map((r) => (
              <div key={r.id} className="row" style={{ padding: '6px 0' }}>
                <a href={href({ page: 'runs', project: route.project, run: r.id })}
                   style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis',
                            whiteSpace: 'nowrap' }}>
                  {r.name}
                </a>
                <MiniBar run={r} catalog={catalog} />
                <span className="small faint nowrap" style={{ width: 42, textAlign: 'right' }}>
                  {r.test_count ? Math.round((r.passed_count / r.test_count) * 100) : 0}%
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </main>
  )
}
