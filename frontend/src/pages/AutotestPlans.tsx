import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import { useUsers } from '../api/hooks'
import { Icon } from '../components/Icon'
import { href } from '../route'
import { RunPill, type RunSummary } from './Autotest'

interface Counts { queued: number; running: number; passed: number; failed: number; error: number; stopped: number }

interface Batch {
  id: number
  plan_id: number | null
  trigger: 'schedule' | 'manual'
  created_on: string
  finished_on: string | null
  started_by: string | null
  run_ids: number[]
  skipped: string[]
  counts: Counts
  total: number
  runs?: (RunSummary & { scenario: string | null })[]
}

interface Plan {
  id: number
  name: string
  is_active: boolean
  scenario_ids: number[]
  days: number[]
  times: string[]
  record_run: boolean
  notify_user_ids: number[]
  notify_always: boolean
  next_run_at: string | null
  last_run_at: string | null
  updated_by: string | null
  timezone: string
  last_batch: Batch | null
}

interface ScenarioLite { id: number; name: string; case_id: number | null }

const DAYS = ['Pzt', 'Sal', 'Çar', 'Per', 'Cum', 'Cmt', 'Paz']

const when = (value: string | null) => value
  ? new Date(value).toLocaleString('tr-TR', { weekday: 'short', day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
  : '—'

function BatchPill({ b }: { b: Batch }) {
  const live = b.counts.queued + b.counts.running > 0
  const bad = b.counts.failed + b.counts.error
  const status = live ? 'running' : bad ? 'failed' : b.total ? 'passed' : 'stopped'
  return (
    <span className={`runpill ${status}`}>
      {live && <span className="pulse" />}
      {live ? `Koşuyor ${b.total - b.counts.queued - b.counts.running}/${b.total}`
        : `${b.counts.passed}/${b.total} geçti`}
    </span>
  )
}

function BatchRow({ b, projectId }: { b: Batch; projectId: number }) {
  const [open, setOpen] = useState(false)
  const live = b.counts.queued + b.counts.running > 0
  const client = useQueryClient()
  const { data } = useQuery({
    queryKey: ['autotest-batch', b.id],
    queryFn: () => api.get<Batch>(`/api/autotest/batches/${b.id}`),
    enabled: open,
    refetchInterval: (q) => (q.state.data && !(q.state.data.counts.queued + q.state.data.counts.running) ? false : 1500),
  })
  const stop = useMutation({
    mutationFn: () => api.post(`/api/autotest/batches/${b.id}/stop`, {}),
    onSuccess: () => client.invalidateQueries({ queryKey: ['autotest-batch', b.id] }),
  })
  return (
    <li className="batchrow">
      <button className="batchrow-head" onClick={() => setOpen(!open)} aria-expanded={open}>
        <Icon name={open ? 'chevron-down' : 'chevron-right'} size={13} />
        <span className="small">{when(b.created_on)}</span>
        <span className="faint small">{b.trigger === 'schedule' ? 'planlı' : `elle · ${b.started_by ?? ''}`}</span>
        <BatchPill b={b} />
        {b.counts.failed + b.counts.error > 0 && !live && (
          <span className="small" style={{ color: 'var(--failed)' }}>{b.counts.failed + b.counts.error} kaldı</span>
        )}
      </button>
      {open && (
        <div className="batchrow-body">
          {b.run_ids.length > 0 && (
            <div className="small" style={{ marginBottom: 6 }}>
              Sonuçlar test koşumuna yazıldı:{' '}
              {b.run_ids.map((id) => (
                <a key={id} href={href({ page: 'runs', project: projectId, run: id })}>R{id} </a>
              ))}
            </div>
          )}
          {b.skipped.length > 0 && (
            <div className="faint small">Hatalı olduğu için atlanan: {b.skipped.join(', ')}</div>
          )}
          {live && (
            <button className="ghost danger small" onClick={() => stop.mutate()} style={{ marginBottom: 6 }}>
              Kalanları durdur
            </button>
          )}
          <ul className="batchruns">
            {(data?.runs ?? []).map((r) => (
              <li key={r.id}>
                <RunPill run={r} />
                <a className="small ellipsis"
                   href={href({ page: 'autotest', project: projectId, scenario: r.scenario_id,
                                filters: { run: String(r.id) } })}>
                  {r.scenario ?? `#${r.scenario_id}`}
                </a>
                {r.message && <span className="faint small ellipsis" title={r.message}>{r.message}</span>}
              </li>
            ))}
            {!data && <li className="skeleton" style={{ width: 200 }} />}
          </ul>
        </div>
      )}
    </li>
  )
}

function PlanEditor({ plan, projectId, scenarios, onSaved, onDeleted }: {
  plan: Plan | null
  projectId: number
  scenarios: ScenarioLite[]
  onSaved: (p: Plan) => void
  onDeleted: () => void
}) {
  const client = useQueryClient()
  const { data: users = [] } = useUsers()
  const [name, setName] = useState(plan?.name ?? '')
  const [active, setActive] = useState(plan?.is_active ?? true)
  const [days, setDays] = useState<number[]>(plan?.days ?? [0, 1, 2, 3, 4])
  const [times, setTimes] = useState((plan?.times ?? ['07:30']).join(', '))
  const [picked, setPicked] = useState<number[]>(plan?.scenario_ids ?? [])
  const [record, setRecord] = useState(plan?.record_run ?? true)
  const [notifyIds, setNotifyIds] = useState<number[]>(plan?.notify_user_ids ?? [])
  const [notifyAlways, setNotifyAlways] = useState(plan?.notify_always ?? false)
  const [filter, setFilter] = useState('')

  const body = () => ({
    name, is_active: active, days, scenario_ids: picked, record_run: record,
    times: times.split(/[,\s]+/).map((t) => t.trim()).filter(Boolean),
    notify_user_ids: notifyIds, notify_always: notifyAlways,
  })
  const refresh = () => client.invalidateQueries({ queryKey: ['autotest-plans', projectId] })

  const save = useMutation({
    mutationFn: () => plan
      ? api.patch<Plan>(`/api/autotest/plans/${plan.id}`, body())
      : api.post<Plan>(`/api/projects/${projectId}/autotest/plans`, body()),
    onSuccess: (p) => { refresh(); onSaved(p) },
  })
  const fire = useMutation({
    mutationFn: async () => {
      if (!plan) throw new Error('önce kaydedin')
      return api.post<Batch>(`/api/autotest/plans/${plan.id}/fire`, {})
    },
    onSuccess: () => { refresh(); client.invalidateQueries({ queryKey: ['autotest-batches', plan?.id] }) },
  })
  const remove = useMutation({
    mutationFn: () => api.del(`/api/autotest/plans/${plan!.id}`),
    onSuccess: () => { refresh(); onDeleted() },
  })
  const batches = useQuery({
    queryKey: ['autotest-batches', plan?.id],
    queryFn: () => api.get<Batch[]>(`/api/autotest/plans/${plan!.id}/batches`),
    enabled: !!plan,
    refetchInterval: (q) => (q.state.data?.some((b) => !b.finished_on) ? 2000 : false),
  })

  const shown = useMemo(() => {
    const q = filter.trim().toLocaleLowerCase('tr')
    return q ? scenarios.filter((s) => s.name.toLocaleLowerCase('tr').includes(q)) : scenarios
  }, [scenarios, filter])
  const toggle = <T,>(list: T[], v: T) => (list.includes(v) ? list.filter((x) => x !== v) : [...list, v])
  const linked = scenarios.filter((s) => picked.includes(s.id) && s.case_id).length
  const problem = (save.error || fire.error || remove.error) as Error | null
  const running = batches.data?.some((b) => !b.finished_on)

  return (
    <div className="autoedit">
      <div className="autoedit-top">
        <input className="autoname" value={name} onChange={(e) => setName(e.target.value)}
               placeholder="Plan adı, ör. Gece regresyonu" aria-label="Plan adı" />
        <label className="small row" style={{ gap: 6 }}>
          <input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} /> Etkin
        </label>
        <button className="ghost" disabled={!name.trim() || save.isPending} onClick={() => save.mutate()}>Kaydet</button>
        <button className="primary" disabled={!plan || fire.isPending || running || !plan.scenario_ids.length}
                onClick={() => fire.mutate()} title={plan ? 'Planı şimdi koş' : 'Önce kaydedin'}>
          <Icon name="play" size={14} /> {running ? 'Koşuyor…' : 'Şimdi koş'}
        </button>
        {plan && (
          <button className="ghost danger" title="Sil" aria-label="Planı sil"
                  onClick={() => confirm(`"${plan.name}" planı silinsin mi?`) && remove.mutate()}>
            <Icon name="trash" size={14} />
          </button>
        )}
      </div>
      {problem && <div className="error small" style={{ marginBottom: 10 }}>{problem.message}</div>}

      <div className="plangrid">
        <section>
          <div className="eyebrow" style={{ marginBottom: 6 }}>Ne zaman</div>
          <div className="chiprow" style={{ marginBottom: 8 }}>
            {DAYS.map((d, i) => (
              <button key={d} className={`chip-toggle ${days.includes(i) ? 'on' : ''}`}
                      onClick={() => setDays(toggle(days, i).sort())}>{d}</button>
            ))}
          </div>
          <input value={times} onChange={(e) => setTimes(e.target.value)} aria-label="Saatler"
                 placeholder="Saatler, ör. 07:30, 13:00" style={{ width: '100%' }} />
          <div className="faint small" style={{ marginTop: 4 }}>
            Virgülle birden çok saat yazılabilir. Saat dilimi: {plan?.timezone ?? 'Europe/Istanbul'}.
            {plan?.next_run_at && <> Sıradaki koşum: <b>{when(plan.next_run_at)}</b>.</>}
            {plan && !plan.is_active && <> Plan duraklatıldı.</>}
          </div>

          <div className="eyebrow" style={{ margin: '16px 0 6px' }}>Sonuçlar</div>
          <label className="small row" style={{ gap: 6, alignItems: 'flex-start' }}>
            <input type="checkbox" checked={record} onChange={(e) => setRecord(e.target.checked)} />
            <span>Her seferinde yeni bir test koşumu aç ve sonuçları oraya yaz
              <span className="faint"> — yalnız case’e bağlı senaryolar ({linked}) koşuma girer</span></span>
          </label>

          <div className="eyebrow" style={{ margin: '16px 0 6px' }}>Bildirim</div>
          <div className="notifylist">
            {users.filter((u) => u.is_active).map((u) => (
              <label key={u.id} className="small row" style={{ gap: 6 }}>
                <input type="checkbox" checked={notifyIds.includes(u.id)}
                       onChange={() => setNotifyIds(toggle(notifyIds, u.id))} /> {u.name}
              </label>
            ))}
          </div>
          <label className="small row" style={{ gap: 6, marginTop: 6 }}>
            <input type="checkbox" checked={notifyAlways} onChange={(e) => setNotifyAlways(e.target.checked)} />
            Hepsi geçtiğinde de bildir (yoksa yalnız kalan olursa)
          </label>
        </section>

        <section>
          <div className="eyebrow" style={{ marginBottom: 6 }}>
            Senaryolar <span className="faint">· {picked.length} seçili</span>
          </div>
          <div className="toolbar" style={{ marginBottom: 6 }}>
            <input className="grow" value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Senaryo ara" />
            <button className="ghost small" onClick={() => setPicked([...new Set([...picked, ...shown.map((s) => s.id)])])}>Görünenleri seç</button>
            <button className="ghost small" onClick={() => setPicked([])}>Temizle</button>
          </div>
          <div className="scenariopick">
            {shown.map((s) => (
              <label key={s.id} className="small row" style={{ gap: 6 }}>
                <input type="checkbox" checked={picked.includes(s.id)} onChange={() => setPicked(toggle(picked, s.id))} />
                <span className="ellipsis">{s.name}</span>
                {s.case_id && <span className="faint">C{s.case_id}</span>}
              </label>
            ))}
            {!scenarios.length && <div className="faint small">Bu projede henüz senaryo yok.</div>}
          </div>
        </section>
      </div>

      {plan && (
        <>
          <div className="eyebrow" style={{ margin: '18px 0 8px' }}>Geçmiş</div>
          {batches.data?.length ? (
            <ul className="batchlist">
              {batches.data.map((b) => <BatchRow key={b.id} b={b} projectId={projectId} />)}
            </ul>
          ) : <div className="faint small">Plan henüz hiç koşmadı.</div>}
        </>
      )}
    </div>
  )
}

/** The "Planlar" tab: scenarios grouped to run by themselves on a schedule. */
export function AutotestPlans({ projectId, selected, onSelect, creating, scenarios }: {
  projectId: number
  selected: number | undefined
  onSelect: (id: number | undefined) => void
  creating: boolean
  scenarios: ScenarioLite[]
}) {
  const { data: plans = [], isLoading } = useQuery({
    queryKey: ['autotest-plans', projectId],
    queryFn: () => api.get<Plan[]>(`/api/projects/${projectId}/autotest/plans`),
    refetchInterval: (q) => (q.state.data?.some((p) => p.last_batch && !p.last_batch.finished_on) ? 2000 : 60_000),
  })
  const plan = plans.find((p) => p.id === selected) ?? null

  return (
    <div className="autolayout">
      <nav className="panel autolist" aria-label="Planlar">
        {isLoading && <div className="skeleton" style={{ margin: 12, width: 160 }} />}
        {!isLoading && !plans.length && !creating && (
          <div className="empty" style={{ padding: 24 }}>
            <b>Henüz plan yok</b>
            Senaryoları belirli gün ve saatlerde kendiliğinden koşturmak için bir plan oluşturun.
          </div>
        )}
        {creating && <div className="autolist-item active"><span className="title">Yeni plan</span></div>}
        {plans.map((p) => (
          <button key={p.id} className={`autolist-item ${p.id === plan?.id && !creating ? 'active' : ''}`}
                  onClick={() => onSelect(p.id)}>
            <span className="title ellipsis">{p.name}</span>
            <span className="row small" style={{ gap: 6 }}>
              {p.is_active
                ? <span className="faint"><Icon name="clock" size={11} /> {when(p.next_run_at)}</span>
                : <span className="faint">duraklatıldı</span>}
              {p.last_batch && <BatchPill b={p.last_batch} />}
            </span>
          </button>
        ))}
      </nav>
      <section className="panel autopane">
        {creating || plan ? (
          <PlanEditor key={creating ? 'new' : plan!.id} plan={creating ? null : plan}
                      projectId={projectId} scenarios={scenarios}
                      onSaved={(p) => { if (creating) onSelect(p.id) }}
                      onDeleted={() => onSelect(undefined)} />
        ) : (
          <div className="empty">
            <Icon name="clock" size={36} className="icon" />
            <b>Planlı otomasyon</b>
            Bir plan, seçtiğiniz senaryoları belirlediğiniz gün ve saatlerde kendiliğinden koşar.
            Sonuçları yeni bir test koşumuna yazabilir, kalan olursa size haber verir.
          </div>
        )}
      </section>
    </div>
  )
}
