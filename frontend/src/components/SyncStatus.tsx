import { useSyncStatus } from '../api/hooks'
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

  if (isLoading || !data) {
    return <div className="skeleton" style={{ width: 260 }} />
  }

  if (!data.enabled && data.runs.length === 0) {
    return (
      <div className="panel empty">
        <b>TestRail eşitlemesi kapalı</b>
        TestRail kapanana kadar değişiklikleri otomatik çekmek için
        <code> TESTRAIL_SYNC_ENABLED=true</code> yapın ve sync servisini
        başlatın. Ayrıntılar DEPLOY.md’de.
      </div>
    )
  }

  return (
    <>
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
              </tr>
            </thead>
            <tbody>
              {data.runs.map((r) => (
                <tr key={r.id} style={{ cursor: 'default' }}>
                  <td className="small muted nowrap">{fmt(r.started_on)}</td>
                  <td>
                    <span className="badge" style={{
                      background: r.status === 'ok' ? 'var(--ok)'
                        : r.status === 'failed' ? 'var(--danger)'
                        : 'var(--blocked)',
                    }}>
                      {r.status === 'ok' ? 'başarılı'
                        : r.status === 'failed' ? 'hata' : 'çalışıyor'}
                    </span>
                  </td>
                  <td className="small muted">{duration(r.counts)}</td>
                  <td className="small muted nowrap">{fmt(r.window_from)}</td>
                  <td className="small">
                    {r.error
                      ? <span style={{ color: 'var(--danger)' }}>{r.error}</span>
                      : summarise(r.counts)}
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
