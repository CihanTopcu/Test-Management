import { ApiError } from '../api/client'
import { useCancelSync, useRequestSync, useSyncStatus } from '../api/hooks'
import { Icon } from './Icon'

/**
 * What the TestRail sync has been doing.
 *
 * A scheduled job nobody can see is a job nobody notices has stopped. During
 * a cut-over that is the worst failure there is: the two systems drift apart
 * quietly and it surfaces when TestRail is already gone. So this sits on the
 * admin page and says plainly when a sync is overdue.
 */

function fmt(value: string | null) {
  if (!value) return '—'
  return new Date(value).toLocaleString('tr-TR', {
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

function duration(counts: Record<string, unknown>) {
  const seconds = counts.seconds
  if (typeof seconds !== 'number') return '—'
  if (seconds < 60) return `${seconds} sn`
  return `${Math.round(seconds / 60)} dk`
}

// ink: green and amber are light enough that white on them is unreadable
const STATUS: Record<string, { label: string; colour: string; ink?: string }> = {
  queued: { label: 'sırada', colour: 'var(--retest)', ink: '#0a0f1e' },
  running: { label: 'çalışıyor', colour: 'var(--accent)' },
  ok: { label: 'başarılı', colour: 'var(--ok)', ink: '#0a0f1e' },
  failed: { label: 'hata', colour: 'var(--danger)' },
  cancelled: { label: 'iptal', colour: 'var(--blocked)' },
}

function summarise(counts: Record<string, unknown>) {
  const parts: string[] = []
  const add = (key: string, label: string) => {
    const value = counts[key]
    if (typeof value === 'number' && value > 0) parts.push(`${value} ${label}`)
  }
  add('cases', 'case')
  add('runs', 'koşum')
  add('results', 'sonuç')
  return parts.length ? parts.join(' · ') : 'değişiklik yok'
}

export function SyncStatus() {
  const { data, isLoading } = useSyncStatus()
  const request = useRequestSync()
  const cancel = useCancelSync()

  if (isLoading || !data) {
    return <div className="skeleton" style={{ width: 260 }} />
  }

  const queued = data.runs.find((r) => r.status === 'queued')
  const running = data.runs.find((r) => r.status === 'running')
  const failure = request.error instanceof ApiError ? request.error.message
    : request.error ? 'Eşitleme isteği gönderilemedi.' : ''

  const header = (
    <div className="page-title" style={{ marginBottom: 14 }}>
      <div>
        {/* lang="en": uppercased under lang="tr" it would read TESTRAİL */}
        <div className="eyebrow" lang="en">TestRail</div>
        <div className="small muted" style={{ marginTop: 6 }}>
          {data.enabled
            ? 'Zamanlanmış geçişi beklemeden TestRail’deki değişiklikleri şimdi çekin.'
            : <>Elle eşitleme için <code>TESTRAIL_SYNC_ENABLED=true</code> olmalı
                ve sync servisi çalışıyor olmalı.</>}
        </div>
      </div>
      <div className="right">
        <button className="primary"
                disabled={!data.enabled || !!queued || !!running || request.isPending}
                title={!data.enabled ? 'Eşitleme kapalı (TESTRAIL_SYNC_ENABLED)' : undefined}
                onClick={() => request.mutate()}>
          <Icon name="download" size={14} />
          {running ? 'Eşitleniyor…' : queued ? 'Sırada…' : 'Şimdi eşitle'}
        </button>
      </div>
    </div>
  )

  if (!data.enabled && data.runs.length === 0) {
    return (
      <>
      {header}
      <div className="panel empty">
        <b>TestRail eşitlemesi kapalı</b>
        TestRail kapanana kadar değişiklikleri otomatik çekmek için
        <code> TESTRAIL_SYNC_ENABLED=true</code> yapın ve sync servisini
        başlatın. Ayrıntılar DEPLOY.md’de.
      </div>
      </>
    )
  }

  return (
    <>
      {header}

      {failure && <div className="error" style={{ marginBottom: 12 }}>{failure}</div>}

      {queued && !data.stalled && (
        <div className="notice" style={{ marginBottom: 12 }}>
          <Icon name="clock" size={14} /> Eşitleme sırada; sync servisi
          birkaç saniye içinde başlatacak.
        </div>
      )}
      {queued && data.stalled && (
        <div className="error" style={{ marginBottom: 12 }}>
          <Icon name="warning" size={14} /> İstek iki dakikadır sırada bekliyor.
          Sync servisi çalışmıyor olabilir — konteyner loglarına bakın ya da
          isteği iptal edin.
        </div>
      )}
      {running && (
        <div className="notice" style={{ marginBottom: 12 }}>
          <Icon name="clock" size={14} /> Eşitleme çalışıyor
          ({fmt(running.started_on)}{' '}başladı). Büyük bir pencere birkaç dakika sürebilir.
        </div>
      )}
      <div className="cards" style={{ marginBottom: 12 }}>
        <div className="panel tile">
          <div className="n" style={{ fontSize: 20 }}>
            {data.enabled ? 'Açık' : 'Kapalı'}
          </div>
          <div className="k">eşitleme</div>
        </div>
        <div className="panel tile">
          <div className="n" style={{ fontSize: 20 }}>
            {data.interval_hours >= 24
              ? `${Math.round(data.interval_hours / 24)} gün`
              : `${data.interval_hours} saat`}
          </div>
          <div className="k">aralık</div>
        </div>
        <div className="panel tile">
          <div className="n" style={{ fontSize: 20 }}>{fmt(data.last_ok)}</div>
          <div className="k">son başarılı eşitleme</div>
        </div>
      </div>

      {data.overdue && (
        <div className="error" style={{ marginBottom: 12 }}>
          <Icon name="warning" size={14} /> Son başarılı eşitlemenin üzerinden
          iki aralıktan fazla geçti. Sync servisi çalışmıyor olabilir —
          konteyner loglarına bakın.
        </div>
      )}

      {data.runs.length === 0 ? (
        <div className="panel empty">
          <b>Henüz eşitleme yapılmadı</b>
          Servis açık ama ilk geçiş henüz tamamlanmadı.
        </div>
      ) : (
        <div className="panel" style={{ overflow: 'auto' }}>
          <table>
            <thead>
              <tr>
                <th style={{ width: 150 }}>Başladı</th>
                <th style={{ width: 90 }}>Durum</th>
                <th style={{ width: 80 }}>Süre</th>
                <th style={{ width: 150 }}>Pencere başı</th>
                <th>Alınanlar</th>
                <th style={{ width: 90 }} />
              </tr>
            </thead>
            <tbody>
              {data.runs.map((r) => (
                <tr key={r.id} style={{ cursor: 'default' }}>
                  <td className="small muted nowrap">{fmt(r.started_on)}</td>
                  <td>
                    <span className="badge" style={{
                      background: STATUS[r.status]?.colour ?? 'var(--blocked)',
                      color: STATUS[r.status]?.ink }}>
                      {STATUS[r.status]?.label ?? r.status}
                    </span>
                    {r.trigger === 'manual' && <span className="faint small"> · elle</span>}
                  </td>
                  <td className="small muted">{duration(r.counts)}</td>
                  <td className="small muted nowrap">{fmt(r.window_from)}</td>
                  <td className="small">
                    {r.error
                      ? <span style={{ color: 'var(--danger)' }}>{r.error}</span>
                      : r.status === 'queued' || r.status === 'running'
                          || r.status === 'cancelled'
                        ? <span className="faint">—</span>
                        : summarise(r.counts)}
                  </td>
                  <td style={{ textAlign: 'right' }}>
                    {r.status === 'queued' && (
                      <button className="ghost danger small"
                              disabled={cancel.isPending}
                              onClick={() => cancel.mutate(r.id)}>
                        İptal
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="faint small" style={{ marginTop: 10 }}>
        TestRail’in API’si silmeleri bildirmez: orada silinen bir case bu
        tarafta kalır. Fark, geçiş öncesi <code>migration/delta.py --report</code>
        ile karşılaştırılmalı.
      </div>
    </>
  )
}
