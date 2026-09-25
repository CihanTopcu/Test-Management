import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import { useCatalog } from '../api/hooks'
import { StackBar, TrendChart } from '../components/Charts'
import { Icon } from '../components/Icon'
import { href } from '../route'

interface Row {
  scenario_id: number
  name: string
  case_id: number | null
  runs: number
  passed: number
  pass_rate: number
  history: number[]
  flips: number
  flaky: boolean
  avg_seconds: number | null
  last_status: string
  last_run_id: number
  last_on: string
  last_failure: { run_id: number; on: string; step: string | null; message: string | null } | null
}

interface Dashboard {
  days: number
  totals: {
    scenarios: number; linked_to_cases: number; runs: number; passed: number; failed: number
    error: number; stopped: number; pass_rate: number | null; avg_seconds: number | null
    flaky: number; never_run: number; active_plans: number
  }
  trend: { day: string; passed: number; failed: number; error: number; total: number; pass_rate: number | null }[]
  scenarios: Row[]
}

const RANGES = [7, 30, 90]
const dayLabel = (iso: string) => {
  const [, m, d] = iso.split('-')
  return `${d}.${m}`
}
const secs = (s: number | null) => (s == null ? '—' : s < 60 ? `${s.toFixed(1)} sn` : `${(s / 60).toFixed(1)} dk`)

function Tile({ label, value, hint, tone }: { label: string; value: string; hint?: string; tone?: 'good' | 'bad' }) {
  return (
    <div className="panel autotile">
      <div className="eyebrow">{label}</div>
      <div className={`autotile-value ${tone ?? ''}`}>{value}</div>
      {hint && <div className="faint small">{hint}</div>}
    </div>
  )
}

/** The last runs of a scenario as a strip, oldest first: one mark per run. */
function History({ values }: { values: number[] }) {
  return (
    <span className="histstrip" aria-label={`Son ${values.length} koşum: ${values.filter(Boolean).length} geçti`}>
      {values.map((v, i) => <span key={i} className={v ? 'ok' : 'bad'} title={v ? 'geçti' : 'kaldı'} />)}
    </span>
  )
}

/** The "Pano" tab: how the automation has been doing. */
export function AutotestDashboard({ projectId }: { projectId: number }) {
  const [days, setDays] = useState(30)
  const { data: catalog } = useCatalog()
  const { data, isLoading } = useQuery({
    queryKey: ['autotest-dashboard', projectId, days],
    queryFn: () => api.get<Dashboard>(`/api/projects/${projectId}/autotest/dashboard?days=${days}`),
    refetchInterval: 60_000,
  })
  const color = (id: number, fallback: string) => catalog?.statuses.find((s) => s.id === id)?.color ?? fallback

  if (isLoading || !data) return <div className="skeleton" style={{ width: 300, margin: 16 }} />
  const t = data.totals
  const open = (sid: number, run?: number) => href({
    page: 'autotest', project: projectId, scenario: sid,
    filters: run ? { run: String(run) } : undefined,
  })

  return (
    <div className="autodash">
      <div className="toolbar">
        <span className="small muted">Son</span>
        <div className="chiprow">
          {RANGES.map((r) => (
            <button key={r} className={`chip-toggle ${r === days ? 'on' : ''}`} onClick={() => setDays(r)}>
              {r} gün
            </button>
          ))}
        </div>
      </div>

      <div className="autotiles">
        <Tile label="Başarı oranı" value={t.pass_rate == null ? '—' : `%${t.pass_rate}`}
              hint={`${t.passed} geçti · ${t.failed} kaldı${t.error ? ` · ${t.error} hata` : ''}`}
              tone={t.pass_rate == null ? undefined : t.pass_rate >= 90 ? 'good' : 'bad'} />
        <Tile label="Koşum" value={t.runs.toLocaleString('tr-TR')} hint={`ortalama ${secs(t.avg_seconds)}`} />
        <Tile label="Oynak senaryo" value={String(t.flaky)} hint="bazen geçip bazen kalan"
              tone={t.flaky ? 'bad' : undefined} />
        <Tile label="Senaryo" value={String(t.scenarios)}
              hint={`${t.linked_to_cases} tanesi case’e bağlı · ${t.never_run} hiç koşmadı`} />
        <Tile label="Etkin plan" value={String(t.active_plans)} hint="kendiliğinden koşan" />
      </div>

      {t.runs > 0 && (
        <div className="panel" style={{ padding: '14px 16px', marginBottom: 14 }}>
          <StackBar total={t.passed + t.failed + t.error} ariaLabel="Koşumların sonuç dağılımı" segments={[
            { key: 'p', label: 'Geçti', count: t.passed, color: color(1, '#52c41a') },
            { key: 'f', label: 'Kaldı', count: t.failed, color: color(5, '#f5566e') },
            { key: 'e', label: 'Hata', count: t.error, color: color(2, '#7f92a3') },
          ]} />
        </div>
      )}

      <div className="panel" style={{ padding: '14px 16px', marginBottom: 14 }}>
        <div className="eyebrow" style={{ marginBottom: 8 }}>Günlük başarı oranı</div>
        {t.runs ? (
          <TrendChart ariaLabel={`Günlük otomasyon başarı oranı, son ${data.days} gün`}
                      points={data.trend.map((p) => ({
                        label: dayLabel(p.day), value: p.pass_rate,
                        detail: p.total ? [`${p.total} koşum`, `${p.passed} geçti, ${p.failed + p.error} kaldı`]
                          : ['koşum yok'],
                      }))}
                      tickLabel={(label, i) => (data.days <= 14 || i % Math.ceil(data.days / 10) === 0 ? label : null)} />
        ) : <div className="faint small">Bu aralıkta koşum yok.</div>}
      </div>

      <div className="panel" style={{ overflow: 'auto' }}>
        <table className="grid">
          <thead>
            <tr>
              <th>Senaryo</th>
              <th style={{ width: 110 }}>Başarı</th>
              <th style={{ width: 170 }}>Son koşumlar</th>
              <th style={{ width: 90 }}>Süre</th>
              <th>Son kalan adım</th>
            </tr>
          </thead>
          <tbody>
            {data.scenarios.map((r) => (
              <tr key={r.scenario_id} onClick={() => { location.hash = open(r.scenario_id) }}>
                <td className="title">
                  {r.name}
                  {r.flaky && <span className="badge soft" style={{ marginLeft: 6 }} title={`son koşumlarda ${r.flips} kez yön değiştirdi`}>
                    <Icon name="warning" size={11} /> oynak
                  </span>}
                  {r.case_id && <div className="faint small">C{r.case_id}</div>}
                </td>
                <td>
                  <b style={{ color: r.pass_rate >= 90 ? 'var(--passed)' : r.pass_rate < 50 ? 'var(--failed)' : undefined }}>
                    %{r.pass_rate}
                  </b>
                  <div className="faint small">{r.passed}/{r.runs}</div>
                </td>
                <td><History values={r.history} /></td>
                <td className="small">{secs(r.avg_seconds)}</td>
                <td className="small">
                  {r.last_failure ? (
                    <a href={open(r.scenario_id, r.last_failure.run_id)} onClick={(e) => e.stopPropagation()}>
                      <code>{r.last_failure.step ?? '—'}</code>
                      {r.last_failure.message && <div className="faint ellipsis" title={r.last_failure.message}>{r.last_failure.message}</div>}
                    </a>
                  ) : <span className="faint">—</span>}
                </td>
              </tr>
            ))}
            {!data.scenarios.length && (
              <tr><td colSpan={5} className="faint small" style={{ padding: 16 }}>Bu aralıkta koşan senaryo yok.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
