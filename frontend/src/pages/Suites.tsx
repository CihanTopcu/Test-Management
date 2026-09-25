import { useProjectStats, useSuites } from '../api/hooks'
import { Icon } from '../components/Icon'
import { href, type Route } from '../route'
import { Crumbs } from '../components/Crumbs'

/** Suite index, in the shape TestRail shows it: one card per suite with the
 *  counts that tell you where the work actually is. */
export function Suites({ route, projectName }: { route: Route; projectName: string }) {
  const { data: suites = [], isLoading } = useSuites(route.project)
  const { data: stats } = useProjectStats(route.project)

  if (isLoading) {
    return <main className="main"><div className="skeleton" style={{ width: 280 }} /></main>
  }

  return (
    <main className="main">
      <Crumbs projectId={route.project} projectName={projectName} />
      <div className="page-title">
        <h1>Test Suite’leri ve Case’ler</h1>
        {stats && (
          <span className="faint small">
            {stats.suites} suite, {stats.cases.toLocaleString('tr-TR')} case
          </span>
        )}
      </div>

      {suites.length === 0 ? (
        <div className="panel empty"><b>Suite yok</b>Bu projede test suite tanımlı değil.</div>
      ) : (
        <div className="panel">
          {suites.map((s) => (
            <div className="suite-card" key={s.id}>
              <div className="ico"><Icon name="folder" size={17} /></div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <h4>
                  <a href={href({ page: 'suites', project: route.project, suite: s.id })}>
                    {s.name}
                  </a>
                  {s.is_completed && <span className="badge soft" style={{ marginLeft: 8 }}>
                    tamamlandı
                  </span>}
                </h4>
                {s.description && <div className="small faint">{s.description}</div>}
                <div className="meta">
                  {s.section_count} bölüm, <b>{s.case_count.toLocaleString('tr-TR')}</b> test case
                  {s.run_count > 0
                    ? <> · {s.run_count} koşum</>
                    : <> · aktif koşum yok</>}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </main>
  )
}
