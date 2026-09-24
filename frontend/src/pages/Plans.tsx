import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import {
  useCatalog, useDeletePlan, useMilestones, useSections, useSuites, useUsers,
} from '../api/hooks'
import { Confirm } from '../components/Confirm'
import { Dialog } from '../components/Dialog'
import { Icon } from '../components/Icon'
import { MiniBar } from '../components/Status'
import { href, type Route } from '../route'

interface PlanRow {
  id: number
  name: string
  description: string | null
  milestone_id: number | null
  is_completed: boolean
  created_on: string | null
  entry_count: number
  test_count: number
  passed_count: number
  untested_count: number
}

interface PlanRun {
  id: number
  name: string
  config: string | null
  is_completed: boolean
  test_count: number
  passed_count: number
  untested_count: number
}

interface PlanDetail {
  id: number
  name: string
  description: string | null
  is_completed: boolean
  entries: { id: number; name: string; suite_id: number; suite_name: string; runs: PlanRun[] }[]
}

function pct(passed: number, total: number) {
  return total ? Math.round((passed / total) * 100) : 0
}

function NewPlanDialog({ projectId, open, onClose }: {
  projectId?: number; open: boolean; onClose: () => void
}) {
  const client = useQueryClient()
  const { data: suites = [] } = useSuites(projectId)
  const { data: milestones = [] } = useMilestones(projectId)
  const { data: users = [] } = useUsers()

  const [name, setName] = useState('')
  const [milestoneId, setMilestoneId] = useState<number | ''>('')
  const [suiteId, setSuiteId] = useState<number | ''>('')
  const [assignee, setAssignee] = useState<number | ''>('')
  const [configs, setConfigs] = useState('')
  const [scope, setScope] = useState<'all' | 'sections'>('all')
  const [sectionIds, setSectionIds] = useState<number[]>([])

  const effectiveSuite = suiteId === '' ? suites[0]?.id : suiteId
  const { data: tree = [] } = useSections(scope === 'sections' ? effectiveSuite : undefined)

  const flat: { id: number; label: string; count: number }[] = []
  const walk = (nodes: typeof tree, depth = 0) => {
    for (const n of nodes) {
      flat.push({ id: n.id, label: ' '.repeat(depth * 3) + n.name, count: n.case_count })
      walk(n.children, depth + 1)
    }
  }
  walk(tree)

  const create = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api.post<{ id: number }>(`/api/projects/${projectId}/plans`, body),
    onSuccess: (plan) => {
      client.invalidateQueries({ queryKey: ['plans', projectId] })
      client.invalidateQueries({ queryKey: ['runs', projectId] })
      onClose()
      location.hash = href({ page: 'plans', project: projectId, plan: plan.id })
    },
  })

  const configList = configs.split(',').map((c) => c.trim()).filter(Boolean)
  const suite = suites.find((s) => s.id === effectiveSuite)
  const selectedCases = scope === 'all'
    ? (suite?.case_count ?? 0)
    : flat.filter((f) => sectionIds.includes(f.id)).reduce((n, f) => n + f.count, 0)

  const submit = () => create.mutate({
    name,
    milestone_id: milestoneId === '' ? null : milestoneId,
    entries: [{
      suite_id: effectiveSuite,
      include_all: scope === 'all',
      section_ids: scope === 'sections' ? sectionIds : [],
      configs: configList,
      assignedto_id: assignee === '' ? null : assignee,
    }],
  })

  return (
    <Dialog open={open} title="Test planı oluştur" onClose={onClose} width={640}
            footer={<>
              <button onClick={onClose}>Vazgeç</button>
              <button className="primary" onClick={submit}
                      disabled={!name || !effectiveSuite || create.isPending}>
                {create.isPending ? 'Oluşturuluyor…' : 'Planı oluştur'}
              </button>
            </>}>
      <div className="stack">
        <div className="field">
          <label>Plan adı</label>
          <input value={name} autoFocus onChange={(e) => setName(e.target.value)}
                 placeholder="ör. Sürüm 4.2 Regresyon" />
        </div>
        <div className="field">
          <label>Milestone</label>
          <select value={milestoneId}
                  onChange={(e) => setMilestoneId(e.target.value === '' ? '' : Number(e.target.value))}>
            <option value="">— yok —</option>
            {milestones.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
          </select>
        </div>
        <div className="field">
          <label>Test suite</label>
          <select value={effectiveSuite ?? ''}
                  onChange={(e) => { setSuiteId(Number(e.target.value)); setSectionIds([]) }}>
            {suites.map((s) => (
              <option key={s.id} value={s.id}>{s.name} ({s.case_count} case)</option>
            ))}
          </select>
        </div>
        <div className="field">
          <label>Konfigürasyonlar — virgülle ayırın, her biri için ayrı koşum açılır</label>
          <input value={configs} onChange={(e) => setConfigs(e.target.value)}
                 placeholder="Chrome, Firefox, Android" />
          <div className="small faint" style={{ marginTop: 5 }}>
            {configList.length || 1} koşum × {selectedCases} case ={' '}
            <b>{(configList.length || 1) * selectedCases}</b> test
          </div>
        </div>
        <div className="field">
          <label>Atanan</label>
          <select value={assignee}
                  onChange={(e) => setAssignee(e.target.value === '' ? '' : Number(e.target.value))}>
            <option value="">— yok —</option>
            {users.filter((u) => u.is_active).map((u) => (
              <option key={u.id} value={u.id}>{u.name}</option>
            ))}
          </select>
        </div>
        <div className="field">
          <label>Kapsam</label>
          <div className="chiprow">
            <button type="button" className={`chip-toggle ${scope === 'all' ? 'on' : ''}`}
                    onClick={() => setScope('all')}>Tüm case’ler</button>
            <button type="button" className={`chip-toggle ${scope === 'sections' ? 'on' : ''}`}
                    onClick={() => setScope('sections')}>Bölüm seç</button>
          </div>
        </div>
        {scope === 'sections' && (
          <div style={{ maxHeight: 200, overflow: 'auto', border: '1px solid var(--border)',
                        borderRadius: 'var(--radius-sm)', padding: 8 }}>
            {flat.map((f) => (
              <label key={f.id} className="row small" style={{ gap: 8, padding: '3px 2px' }}>
                <input type="checkbox" checked={sectionIds.includes(f.id)}
                       onChange={() => setSectionIds(
                         sectionIds.includes(f.id)
                           ? sectionIds.filter((x) => x !== f.id)
                           : [...sectionIds, f.id])} />
                <span style={{ flex: 1 }}>{f.label}</span>
                <span className="faint">{f.count}</span>
              </label>
            ))}
          </div>
        )}
        {create.isError && <div className="error">Plan oluşturulamadı</div>}
      </div>
    </Dialog>
  )
}

function PlanDetailView({ route }: { route: Route }) {
  const client = useQueryClient()
  const { data: catalog } = useCatalog()
  const removePlan = useDeletePlan(route.project)
  const [deleting, setDeleting] = useState(false)
  const { data: plan } = useQuery({
    queryKey: ['plan', route.plan],
    queryFn: () => api.get<PlanDetail>(`/api/plans/${route.plan}`),
    enabled: !!route.plan,
  })
  const complete = useMutation({
    mutationFn: (done: boolean) =>
      api.patch(`/api/plans/${route.plan}`, { is_completed: done }),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ['plan', route.plan] })
      client.invalidateQueries({ queryKey: ['plans', route.project] })
    },
  })

  if (!plan) {
    return <main className="main"><div className="skeleton" style={{ width: 240 }} /></main>
  }

  const allRuns = plan.entries.flatMap((e) => e.runs)
  const total = allRuns.reduce((n, r) => n + r.test_count, 0)
  const passed = allRuns.reduce((n, r) => n + r.passed_count, 0)

  return (
    <main className="main">
      <div className="crumbs">
        <a href={href({ page: 'plans', project: route.project })}>Test Planları</a>
        <Icon name="chevron-right" size={12} />{plan.name}
      </div>
      <div className="page-title">
        <span className="idbadge run">P{plan.id}</span>
        <h1>{plan.name}</h1>
        {plan.is_completed && <span className="badge soft">tamamlandı</span>}
        <div className="right row" style={{ gap: 6 }}>
          <button onClick={() => complete.mutate(!plan.is_completed)}>
            {plan.is_completed ? 'Yeniden aç' : 'Planı tamamla'}
          </button>
          <button className="ghost danger" onClick={() => setDeleting(true)}>
            <Icon name="trash" size={13} /> Planı sil
          </button>
        </div>
      </div>

      <Confirm open={deleting} title="Planı sil" busy={removePlan.isPending}
               error={removePlan.isError ? (removePlan.error as Error).message : null}
               detail={`"${plan.name}" planı, ${allRuns.length} koşumu ve bunlara`
                 + ' girilmiş bütün sonuçlar kalıcı olarak silinecek.'}
               onClose={() => setDeleting(false)}
               onConfirm={() => removePlan.mutate(plan.id, {
                 onSuccess: () => {
                   setDeleting(false)
                   location.hash = href({ page: 'plans', project: route.project })
                 },
               })} />

      <div className="cards" style={{ marginBottom: 16 }}>
        <div className="panel tile"><div className="n">{plan.entries.length}</div>
          <div className="k">plan satırı</div></div>
        <div className="panel tile"><div className="n">{allRuns.length}</div>
          <div className="k">koşum</div></div>
        <div className="panel tile"><div className="n">{total.toLocaleString('tr-TR')}</div>
          <div className="k">test</div></div>
        <div className="panel tile"><div className="n">{pct(passed, total)}%</div>
          <div className="k">passed</div></div>
      </div>

      {plan.entries.map((entry) => (
        <div key={entry.id} style={{ marginBottom: 16 }}>
          <div className="section-rule">
            {entry.name} <span className="faint small">· {entry.suite_name}</span>
          </div>
          <div className="panel">
            <table>
              <tbody>
                {entry.runs.map((run) => (
                  <tr key={run.id}
                      onClick={() => {
                        location.hash = href({ page: 'runs', project: route.project, run: run.id })
                      }}>
                    <td className="title">
                      {run.name}
                      {run.config && <span className="badge soft" style={{ marginLeft: 8 }}>
                        {run.config}
                      </span>}
                    </td>
                    <td style={{ width: 150 }}>
                      <MiniBar run={run} catalog={catalog} />
                    </td>
                    <td className="small faint nowrap" style={{ width: 90 }}>
                      {run.test_count} test
                    </td>
                    <td className="nowrap" style={{ width: 54, textAlign: 'right' }}>
                      <b>{pct(run.passed_count, run.test_count)}%</b>
                    </td>
                  </tr>
                ))}
                {entry.runs.length === 0 && (
                  <tr><td className="faint">Bu satırda koşum yok.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      ))}
    </main>
  )
}

export function Plans({ route, projectName }: { route: Route; projectName: string }) {
  const [adding, setAdding] = useState(false)
  const { data: catalog } = useCatalog()
  const { data: plans = [], isLoading } = useQuery({
    queryKey: ['plans', route.project],
    queryFn: () => api.get<PlanRow[]>(`/api/projects/${route.project}/plans`),
    enabled: !!route.project,
  })

  if (route.plan) return <PlanDetailView route={route} />

  if (isLoading) {
    return <main className="main"><div className="skeleton" style={{ width: 260 }} /></main>
  }

  return (
    <main className="main">
      <div className="crumbs"><b>{projectName}</b></div>
      <div className="page-title">
        <h1>Test Planları</h1>
        <span className="faint small">{plans.length} plan</span>
        <button className="primary right" onClick={() => setAdding(true)}>
          <Icon name="plus" size={14} /> Plan oluştur
        </button>
      </div>

      <NewPlanDialog projectId={route.project} open={adding}
                     onClose={() => setAdding(false)} />

      {plans.length === 0 ? (
        <div className="panel empty">
          <Icon name="grid" size={30} />
          <b>Test planı yok</b>
          Bir kampanyayı tek seferde yönetmek için plan oluşturun — her
          konfigürasyon için ayrı koşum açılır.
        </div>
      ) : (
        <div className="panel">
          <table>
            <thead>
              <tr>
                <th>Plan</th>
                <th style={{ width: 90 }}>Satır</th>
                <th style={{ width: 100 }}>Test</th>
                <th style={{ width: 150 }}>İlerleme</th>
                <th style={{ width: 60 }}></th>
              </tr>
            </thead>
            <tbody>
              {plans.map((p) => (
                <tr key={p.id}
                    onClick={() => {
                      location.hash = href({ page: 'plans', project: route.project, plan: p.id })
                    }}>
                  <td className="title">
                    <b>{p.name}</b>
                    {p.is_completed && <span className="badge soft" style={{ marginLeft: 8 }}>
                      tamamlandı
                    </span>}
                    {p.description && <div className="small faint">{p.description}</div>}
                  </td>
                  <td className="small muted">{p.entry_count}</td>
                  <td className="small muted">{p.test_count.toLocaleString('tr-TR')}</td>
                  <td><MiniBar run={p} catalog={catalog} /></td>
                  <td className="nowrap" style={{ textAlign: 'right' }}>
                    <b>{pct(p.passed_count, p.test_count)}%</b>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </main>
  )
}
