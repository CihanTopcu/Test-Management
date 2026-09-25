import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import { Icon } from './Icon'

interface State {
  total: number
  live: number
  counts: Record<'queued' | 'running' | 'passed' | 'failed' | 'error' | 'stopped', number>
}

/**
 * "Run the automated tests" for a whole run: every test whose case has a
 * browser scenario, one after another, each writing its own result. Hidden
 * when nothing in the run is automated.
 */
export function RunAutomation({ runId, archived }: { runId: number; archived: boolean }) {
  const client = useQueryClient()
  const key = ['run-autotest', runId]
  const { data } = useQuery({
    queryKey: key,
    queryFn: () => api.get<State>(`/api/runs/${runId}/autotest`),
    refetchInterval: (q) => (q.state.data?.live ? 1500 : false),
  })
  const [note, setNote] = useState<string | null>(null)

  const start = useMutation({
    mutationFn: () => api.post<{ started: number; skipped: { reason: string }[] }>(
      `/api/runs/${runId}/autotest`, {}),
    onSuccess: (r) => {
      setNote(r.skipped.length
        ? `${r.started} test sıraya girdi; ${r.skipped.length} atlandı (${r.skipped[0].reason})`
        : null)
      client.invalidateQueries({ queryKey: key })
    },
  })
  const stop = useMutation({
    mutationFn: () => api.post(`/api/runs/${runId}/autotest/stop`, {}),
    onSuccess: () => client.invalidateQueries({ queryKey: key }),
  })

  // each finished test changed a row of the grid and the summary strip
  const done = data ? data.counts.passed + data.counts.failed + data.counts.error : 0
  const seen = useRef(done)
  useEffect(() => {
    if (done === seen.current) return
    seen.current = done
    client.invalidateQueries({ queryKey: ['tests', runId] })
    client.invalidateQueries({ queryKey: ['run-summary', runId] })
  }, [done, client, runId])

  if (!data?.total) return null
  const c = data.counts
  if (data.live) {
    const finished = data.total - data.live
    return (
      <span className="row small" style={{ gap: 8 }}>
        <span className="autorunstate running"><span className="pulse" />
          Otomasyon koşuyor · {finished}/{data.total}
        </span>
        {c.queued > 0 && <span className="faint">{c.queued} sırada</span>}
        <button className="ghost danger small" disabled={stop.isPending} onClick={() => stop.mutate()}>
          Durdur
        </button>
      </span>
    )
  }
  return (
    <span className="row small" style={{ gap: 8 }}>
      {(c.passed + c.failed) > 0 && (
        <span className="faint" title="Son otomasyon koşumlarının sonucu">
          son: <b style={{ color: 'var(--passed)' }}>{c.passed} geçti</b>
          {c.failed > 0 && <>, <b style={{ color: 'var(--failed)' }}>{c.failed} kaldı</b></>}
        </span>
      )}
      <button disabled={archived || start.isPending} onClick={() => start.mutate()}
              title={archived ? 'Arşivlenmiş koşuma sonuç eklenemez'
                : 'Senaryosu olan testleri sırayla tarayıcıda koşar, sonuçları testlere yazar'}>
        <Icon name="play" size={13} /> Otomasyonu koş ({data.total})
      </button>
      {note && <span className="faint">{note}</span>}
      {start.error && <span className="error">{(start.error as Error).message}</span>}
    </span>
  )
}
