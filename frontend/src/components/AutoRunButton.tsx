import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import { href } from '../route'
import { Icon } from './Icon'

interface Linked {
  id: number
  name: string
  last_run: { id: number; status: string } | null
}

interface RunState {
  id: number
  status: 'queued' | 'running' | 'passed' | 'failed' | 'error' | 'stopped'
  message: string | null
  passed: number
  total: number
  result_id: number | null
}

const LIVE = new Set(['queued', 'running'])
const LABEL: Record<RunState['status'], string> = {
  queued: 'Tarayıcı açılıyor…', running: 'Koşuyor…', passed: 'Geçti', failed: 'Kaldı',
  error: 'Hata', stopped: 'Durduruldu',
}

/**
 * "Run the automation" on a test whose case has a browser scenario. The
 * runner writes the outcome to this test as a result, so when it ends the
 * panel's result list and the run grid are refreshed.
 */
export function AutoRunButton({ caseId, testId, projectId, runId, archived }: {
  caseId: number
  testId: number
  projectId?: number
  runId?: number | null
  archived: boolean
}) {
  const client = useQueryClient()
  const { data: linked = [] } = useQuery({
    queryKey: ['case-autotest', caseId],
    queryFn: () => api.get<Linked[]>(`/api/cases/${caseId}/autotest`),
    staleTime: 60_000,
  })
  const [active, setActive] = useState<number | null>(null)

  const start = useMutation({
    mutationFn: (scenarioId: number) =>
      api.post<RunState>(`/api/autotest/scenarios/${scenarioId}/runs`, { test_id: testId }),
    onSuccess: (r) => setActive(r.id),
  })

  const { data: run } = useQuery({
    queryKey: ['autotest-run-brief', active],
    queryFn: () => api.get<RunState>(`/api/autotest/runs/${active}`),
    enabled: active != null,
    refetchInterval: (q) => (q.state.data && !LIVE.has(q.state.data.status) ? false : 900),
  })

  const done = run && !LIVE.has(run.status)
  useEffect(() => {
    if (!done) return
    client.invalidateQueries({ queryKey: ['results', testId] })
    client.invalidateQueries({ queryKey: ['test', testId] })
    client.invalidateQueries({ queryKey: ['tests', runId] })
    client.invalidateQueries({ queryKey: ['case-autotest', caseId] })
  }, [done, client, testId, runId, caseId])

  if (!linked.length) return null
  const busy = start.isPending || (run != null && LIVE.has(run.status))

  return (
    <div className="autorunbox">
      {linked.map((s) => (
        <div key={s.id} className="row">
          <button className="ghost small" disabled={archived || busy}
                  onClick={() => start.mutate(s.id)}
                  title={archived ? 'Arşivlenmiş koşuma sonuç eklenemez'
                    : 'Senaryoyu tarayıcıda koşar, sonucu bu teste yazar'}>
            <Icon name="play" size={12} /> Otomasyonla koş
          </button>
          <a className="small ellipsis"
             href={href({ page: 'autotest', project: projectId, scenario: s.id })}>{s.name}</a>
        </div>
      ))}
      {run && (
        <div className={`small autorunstate ${run.status}`}>
          {LIVE.has(run.status) && <span className="pulse" />}
          {LABEL[run.status]}
          {run.total > 0 && !LIVE.has(run.status) && <> · {run.passed}/{run.total} adım</>}
          {run.result_id && <span className="faint"> · sonuç teste yazıldı</span>}
          {run.message && <div className="faint">{run.message}</div>}
        </div>
      )}
      {start.error && <div className="error small">{(start.error as Error).message}</div>}
    </div>
  )
}
