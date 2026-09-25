import { useMemo, useState } from 'react'
import { useCatalog, useMilestones, useRuns } from '../api/hooks'
import { AddMilestoneDialog } from '../components/AddDialogs'
import { Icon } from '../components/Icon'
import { MiniBar } from '../components/Status'
import type { Milestone, Run } from '../api/types'
import { href, type Route } from '../route'
import { Crumbs } from '../components/Crumbs'

function fmt(value?: string | null) {
  if (!value) return null
  return new Date(value).toLocaleDateString('tr-TR',
    { year: 'numeric', month: '2-digit', day: '2-digit' })
}

function rollup(runs: Run[]) {
  const total = runs.reduce((n, r) => n + r.test_count, 0)
  const passed = runs.reduce((n, r) => n + r.passed_count, 0)
  const untested = runs.reduce((n, r) => n + r.untested_count, 0)
  return { test_count: total, passed_count: passed, untested_count: untested }
}

export function Milestones({ route, projectName }: { route: Route; projectName: string }) {
  const { data: milestones = [], isLoading } = useMilestones(route.project)
  const { data: runs = [] } = useRuns(route.project)
  const { data: catalog } = useCatalog()
  const [adding, setAdding] = useState(false)

  const runsByMilestone = useMemo(() => {
    const map = new Map<number, Run[]>()
    for (const run of runs) {
      if (!run.milestone_id) continue
      const list = map.get(run.milestone_id) ?? []
      list.push(run)
      map.set(run.milestone_id, list)
    }
    return map
  }, [runs])

  const { open, done } = useMemo(() => {
    const children = new Map<number, Milestone[]>()
    const roots: Milestone[] = []
    for (const m of milestones) {
      if (m.parent_id) {
        const list = children.get(m.parent_id) ?? []
        list.push(m)
        children.set(m.parent_id, list)
      } else {
        roots.push(m)
      }
    }
    const rows: { m: Milestone; depth: number; kids: number }[] = []
    for (const root of roots) {
      const kids = children.get(root.id) ?? []
      rows.push({ m: root, depth: 0, kids: kids.length })
      for (const kid of kids) rows.push({ m: kid, depth: 1, kids: 0 })
    }
    return {
      open: rows.filter((r) => !r.m.is_completed),
      done: rows.filter((r) => r.m.is_completed),
    }
  }, [milestones])

  if (isLoading) {
    return <main className="main"><div className="skeleton" style={{ width: 280 }} /></main>
  }

  const renderGroup = (rows: typeof open, title: string) => (
    rows.length > 0 && (
      <>
        <div className="section-rule">{title} ({rows.length})</div>
        <div className="panel">
          <table>
            <tbody>
              {rows.map(({ m, depth, kids }) => {
                const mine = runsByMilestone.get(m.id) ?? []
                const agg = rollup(mine)
                const pct = agg.test_count
                  ? Math.round((agg.passed_count / agg.test_count) * 100) : null
                const due = fmt(m.due_on)
                return (
                  <tr key={m.id} onClick={() => {
                    location.hash = href({ page: 'milestones',
                                           project: route.project,
                                           milestone: m.id })
                  }}>
                    <td style={{ paddingLeft: 10 + depth * 24 }}>
                      <Icon name="flag" size={14} className="faint" />{' '}
                      <b>{m.name}</b>
                      <div className="small faint" style={{ marginLeft: 24 }}>
                        {due ? `Bitiş ${due}` : 'Tarih yok'}
                        {kids > 0 && ` · ${kids} alt milestone`}
                        {mine.length > 0
                          ? ` · ${mine.length} koşum`
                          : ' · aktif koşum yok'}
                      </div>
                    </td>
                    <td style={{ width: 150 }}>
                      {agg.test_count > 0 && <MiniBar run={agg} catalog={catalog} />}
                    </td>
                    <td className="nowrap" style={{ width: 56, textAlign: 'right' }}>
                      {pct === null ? <span className="faint">—</span> : <b>{pct}%</b>}
                    </td>
                    <td style={{ width: 90 }} className="small muted">
                      detay <Icon name="chevron-right" size={12} />
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </>
    )
  )

  return (
    <main className="main">
      <Crumbs projectId={route.project} projectName={projectName} />
      <div className="page-title">
        <h1>Milestone’lar</h1>
        <span className="faint small">
          {open.length} açık, {done.length} tamamlanmış
        </span>
        <button className="primary right" onClick={() => setAdding(true)}>
          <Icon name="plus" size={14} /> Milestone ekle
        </button>
      </div>

      <AddMilestoneDialog projectId={route.project} open={adding}
                          onClose={() => setAdding(false)} />

      {milestones.length === 0 ? (
        <div className="panel empty">
          <b>Milestone yok</b>
          Bu projede tanımlı milestone bulunmuyor.
        </div>
      ) : (
        <>
          {renderGroup(open, 'Açık')}
          {renderGroup(done, 'Tamamlanan')}
        </>
      )}
    </main>
  )
}
