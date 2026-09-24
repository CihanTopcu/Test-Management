import { useMemo, useState } from 'react'
import {
  useCatalog, useDeleteMilestone, useMilestones, useRuns, useUpdateMilestone,
  useUsers,
} from '../api/hooks'
import { Confirm } from '../components/Confirm'
import { Icon } from '../components/Icon'
import { Donut, Legend, MiniBar, slices } from '../components/Status'
import { RichText } from '../components/RichText'
import type { Run } from '../api/types'
import { href, type Route } from '../route'

/**
 * One milestone: what it is due, what is running under it, where it stands.
 *
 * The list page could only ever show a bar per row. A release conversation
 * needs the runs themselves, the sub-milestones and the dates in one place --
 * which is what TestRail's milestone page was actually used for.
 */

function fmtDate(value?: string | null) {
  if (!value) return null
  return new Date(value).toLocaleDateString('tr-TR',
    { year: 'numeric', month: 'long', day: 'numeric' })
}

function daysLeft(due?: string | null) {
  if (!due) return null
  const ms = new Date(due).getTime() - Date.now()
  return Math.ceil(ms / 86_400_000)
}

export function MilestoneView({ route, projectName }: {
  route: Route; projectName: string
}) {
  const { data: milestones = [] } = useMilestones(route.project)
  const { data: runs = [] } = useRuns(route.project)
  const { data: catalog } = useCatalog()
  const { data: users = [] } = useUsers()
  const update = useUpdateMilestone(route.project)
  const remove = useDeleteMilestone(route.project)

  const [deleting, setDeleting] = useState(false)
  const [editing, setEditing] = useState(false)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [dueOn, setDueOn] = useState('')

  const milestone = milestones.find((m) => m.id === route.milestone)
  const children = milestones.filter((m) => m.parent_id === route.milestone)

  // a run under a sub-milestone counts towards the parent too, which is the
  // only way the release-level number means anything
  const family = useMemo(() => {
    const ids = new Set<number>([route.milestone ?? -1,
                                 ...children.map((c) => c.id)])
    return runs.filter((r) => r.milestone_id != null && ids.has(r.milestone_id))
  }, [runs, route.milestone, children])

  const mine = runs.filter((r) => r.milestone_id === route.milestone)

  if (!milestone) {
    return (
      <main className="main">
        <div className="panel empty">
          <b>Milestone bulunamadı</b>
          <a href={href({ page: 'milestones', project: route.project })}>
            Milestone listesine dön
          </a>
        </div>
      </main>
    )
  }

  // the run list carries each bucket outright now; the donut used to label
  // "not passed and not untested" as Failed, so a milestone full of deferred
  // tests reported itself as a milestone full of failures
  const totals = family.reduce((acc, r: Run) => ({
    test_count: acc.test_count + r.test_count,
    passed_count: acc.passed_count + r.passed_count,
    untested_count: acc.untested_count + r.untested_count,
    failed_count: acc.failed_count + (r.failed_count ?? 0),
    other_count: acc.other_count + Math.max(
      0, r.test_count - r.passed_count - r.untested_count - (r.failed_count ?? 0)),
  }), { test_count: 0, passed_count: 0, untested_count: 0, failed_count: 0,
        other_count: 0 })

  const pct = totals.test_count
    ? Math.round((totals.passed_count / totals.test_count) * 100) : null
  const left = daysLeft(milestone.due_on)
  // "Diğer" is a bucket, not a status, so it is not looked up in the
  // catalogue: it holds retouch, blocked, deferred and aborted together.
  const data = [
    ...slices(catalog, { '1': totals.passed_count, '5': totals.failed_count }),
    ...(totals.other_count > 0
      ? [{ id: null, count: totals.other_count, label: 'Diğer',
           color: 'var(--warn)' }]
      : []),
    ...slices(catalog, { '3': totals.untested_count }),
  ]

  const startEdit = () => {
    setName(milestone.name)
    setDescription(milestone.description ?? '')
    setDueOn(milestone.due_on ? milestone.due_on.slice(0, 10) : '')
    setEditing(true)
  }

  const save = () => update.mutate({
    id: milestone.id,
    patch: {
      name,
      description: description || null,
      due_on: dueOn ? new Date(dueOn).toISOString() : null,
    },
  }, { onSuccess: () => setEditing(false) })

  return (
    <main className="main">
      <div className="crumbs">
        <b>{projectName}</b>
        <Icon name="chevron-right" size={12} />
        <a href={href({ page: 'milestones', project: route.project })}>
          Milestone’lar
        </a>
        {milestone.parent_id && (
          <>
            <Icon name="chevron-right" size={12} />
            <a href={href({ page: 'milestones', project: route.project,
                            milestone: milestone.parent_id })}>
              {milestones.find((m) => m.id === milestone.parent_id)?.name}
            </a>
          </>
        )}
      </div>

      <div className="page-title">
        <span className="idbadge"><Icon name="flag" size={12} /></span>
        {editing ? (
          <input value={name} autoFocus style={{ maxWidth: 520 }}
                 onChange={(e) => setName(e.target.value)} />
        ) : (
          <h1>{milestone.name}</h1>
        )}
        {milestone.is_completed && <span className="badge soft">tamamlandı</span>}
        {!milestone.is_completed && left != null && (
          <span className={`badge ${left < 0 ? '' : 'soft'}`}
                style={left < 0 ? { background: 'var(--danger)' } : undefined}>
            {left < 0 ? `${-left} gün gecikti` : `${left} gün kaldı`}
          </span>
        )}
        <div className="right row" style={{ gap: 6 }}>
          {editing ? (
            <>
              <button className="primary" onClick={save} disabled={update.isPending}>
                {update.isPending ? 'Kaydediliyor…' : 'Kaydet'}
              </button>
              <button onClick={() => setEditing(false)}>Vazgeç</button>
            </>
          ) : (
            <>
              <button onClick={startEdit}>
                <Icon name="edit" size={13} /> Düzenle
              </button>
              <button onClick={() => update.mutate({
                id: milestone.id,
                patch: { is_completed: !milestone.is_completed },
              })}>
                <Icon name="check-circle" size={13} />
                {milestone.is_completed ? ' Yeniden aç' : ' Tamamlandı'}
              </button>
              <button className="ghost danger" onClick={() => setDeleting(true)}>
                <Icon name="trash" size={13} /> Sil
              </button>
            </>
          )}
        </div>
      </div>

      <Confirm open={deleting} title="Milestone’u sil" busy={remove.isPending}
               error={remove.isError ? (remove.error as Error).message : null}
               detail={'Milestone silinecek. Koşumlar ve planlar silinmez —'
                 + ' yalnızca bu milestone ile bağları kopar.'
                 + (children.length
                     ? ` ${children.length} alt milestone bir üst seviyeye taşınır.`
                     : '')}
               onClose={() => setDeleting(false)}
               onConfirm={() => remove.mutate(milestone.id, {
                 onSuccess: () => {
                   setDeleting(false)
                   location.hash = href({ page: 'milestones', project: route.project })
                 },
               })} />

      {editing ? (
        <div className="panel" style={{ padding: 16 }}>
          <div className="field">
            <label>Açıklama</label>
            <textarea rows={4} value={description}
                      onChange={(e) => setDescription(e.target.value)} />
          </div>
          <div className="field" style={{ maxWidth: 240 }}>
            <label>Bitiş tarihi</label>
            <input type="date" value={dueOn}
                   onChange={(e) => setDueOn(e.target.value)} />
          </div>
        </div>
      ) : (
        <>
          <div className="fieldgrid">
            <div>
              <div className="k">Başlangıç</div>
              <div className="v">{fmtDate(milestone.start_on)
                ?? <span className="faint">—</span>}</div>
            </div>
            <div>
              <div className="k">Bitiş</div>
              <div className="v">{fmtDate(milestone.due_on)
                ?? <span className="faint">—</span>}</div>
            </div>
            <div>
              <div className="k">Koşum</div>
              <div className="v">{mine.length}
                {children.length > 0 && (
                  <span className="faint small"> · alt dahil {family.length}</span>
                )}
              </div>
            </div>
            <div>
              <div className="k">Test</div>
              <div className="v">{totals.test_count.toLocaleString('tr-TR')}</div>
            </div>
          </div>

          {milestone.description && (
            <>
              <div className="section-rule">Açıklama</div>
              <div className="panel" style={{ padding: '10px 13px' }}>
                <RichText value={milestone.description} />
              </div>
            </>
          )}

          {totals.test_count > 0 && (
            <div className="panel" style={{ padding: 16, marginTop: 12 }}>
              <div className="donut-wrap">
                <Donut data={data} size={130} />
                <div className="pass-big">
                  <div className="n">{pct}%</div>
                  <div className="k">passed</div>
                  <div className="k">
                    {totals.untested_count} / {totals.test_count} untested
                  </div>
                </div>
                <div style={{ flex: 1, minWidth: 240 }}>
                  <Legend data={data} total={totals.test_count} />
                </div>
              </div>
            </div>
          )}
        </>
      )}

      {children.length > 0 && (
        <>
          <div className="section-rule">Alt milestone’lar ({children.length})</div>
          <div className="panel">
            <table>
              <tbody>
                {children.map((child) => {
                  const childRuns = runs.filter((r) => r.milestone_id === child.id)
                  const agg = childRuns.reduce((acc, r) => ({
                    test_count: acc.test_count + r.test_count,
                    passed_count: acc.passed_count + r.passed_count,
                    untested_count: acc.untested_count + r.untested_count,
                  }), { test_count: 0, passed_count: 0, untested_count: 0 })
                  return (
                    <tr key={child.id} onClick={() => {
                      location.hash = href({ page: 'milestones',
                                             project: route.project,
                                             milestone: child.id })
                    }}>
                      <td className="title">
                        <Icon name="flag" size={13} className="faint" /> {child.name}
                      </td>
                      <td className="small muted" style={{ width: 140 }}>
                        {fmtDate(child.due_on) ?? 'tarih yok'}
                      </td>
                      <td style={{ width: 160 }}>
                        {agg.test_count > 0 && <MiniBar run={agg} catalog={catalog} />}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </>
      )}

      <div className="section-rule">Koşumlar ({mine.length})</div>
      {mine.length === 0 ? (
        <div className="panel empty">
          <b>Koşum yok</b>
          Bu milestone’a bağlı aktif bir test koşumu bulunmuyor.
        </div>
      ) : (
        <div className="panel">
          <table>
            <thead>
              <tr>
                <th style={{ width: 90 }}>ID</th>
                <th>Koşum</th>
                <th style={{ width: 150 }}>Atanan</th>
                <th style={{ width: 170 }}>İlerleme</th>
              </tr>
            </thead>
            <tbody>
              {mine.map((run) => (
                <tr key={run.id} onClick={() => {
                  location.hash = href({ page: 'runs', project: route.project,
                                         run: run.id })
                }}>
                  <td className="cid">R{run.id}</td>
                  <td className="title">{run.name}</td>
                  <td className="small muted">
                    {users.find((u) => u.id === run.assignedto_id)?.name ?? '—'}
                  </td>
                  <td><MiniBar run={run} catalog={catalog} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

    </main>
  )
}
