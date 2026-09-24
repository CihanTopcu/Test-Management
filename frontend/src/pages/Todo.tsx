import { useMemo } from 'react'
import { useCatalog, useTodo } from '../api/hooks'
import { StatusBadge } from '../components/Status'
import { href } from '../route'

/** Everything assigned to me that still needs a result, across every project. */
export function Todo() {
  const { data: items = [], isLoading } = useTodo()
  const { data: catalog } = useCatalog()

  const groups = useMemo(() => {
    const map = new Map<string, typeof items>()
    for (const item of items) {
      const key = `${item.project_id}|${item.project_name}|${item.run_id}|${item.run_name}`
      map.set(key, [...(map.get(key) ?? []), item])
    }
    return [...map.entries()]
  }, [items])

  if (isLoading) {
    return <main className="main"><div className="skeleton" style={{ width: 260 }} /></main>
  }

  return (
    <main className="main">
      <div className="page-title">
        <h1>Yapılacaklar</h1>
        <span className="faint small">{items.length} test size atanmış ve henüz sonuçlanmamış</span>
      </div>

      {items.length === 0 ? (
        <div className="panel empty">
          <b>Temiz</b>
          Üzerinize atanmış, sonuç bekleyen test yok.
        </div>
      ) : (
        groups.map(([key, rows]) => {
          const [projectId, projectName, runId, runName] = key.split('|')
          return (
            <div key={key} style={{ marginBottom: 14 }}>
              <div className="section-rule">
                {projectName} › {runName} ({rows.length})
              </div>
              <div className="panel">
                <table>
                  <tbody>
                    {rows.map((r) => (
                      <tr key={r.test_id}
                          onClick={() => {
                            location.hash = href({
                              page: 'runs', project: Number(projectId),
                              run: Number(runId), test: r.test_id })
                          }}>
                        <td className="cid" style={{ width: 96 }}>T{r.test_id}</td>
                        <td className="title">{r.test_title}</td>
                        <td style={{ width: 120 }}>
                          <StatusBadge catalog={catalog} id={r.status_id} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )
        })
      )}
    </main>
  )
}
