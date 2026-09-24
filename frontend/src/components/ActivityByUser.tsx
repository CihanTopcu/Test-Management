import { useState } from 'react'
import { useActivityByUser } from '../api/hooks'
import { Icon } from './Icon'

/**
 * Who produced what, by account.
 *
 * The caveat is part of the report rather than a footnote somebody has to
 * find: in the migrated data five of the six active accounts are shared team
 * logins named after the domain they cover, and the sixth holds the
 * automation's API key. So this measures the output of a domain, not of a
 * person.
 *
 * The one thing that does separate a pipeline from a human is the mix. An
 * account that only posts results is a robot; one that writes and edits
 * cases is somebody at a keyboard. That ratio gets its own column.
 */

function bar(part: number, total: number) {
  return total ? `${Math.round((100 * part) / total)}%` : '0%'
}

export function ActivityByUser() {
  const [days, setDays] = useState(365)
  const { data, isFetching } = useActivityByUser(days)

  const items = data?.items ?? []
  const totals = data?.totals

  return (
    <>
      <div className="section-rule">
        Kim ne üretti
        <select style={{ width: 150 }} value={days}
                onChange={(e) => setDays(Number(e.target.value))}>
          <option value={30}>Son 30 gün</option>
          <option value={90}>Son 90 gün</option>
          <option value={365}>Son 1 yıl</option>
          <option value={3650}>Tüm zamanlar</option>
        </select>
      </div>

      <div className="panel" style={{ padding: '10px 14px', marginBottom: 12 }}>
        <div className="row small" style={{ gap: 10, alignItems: 'flex-start' }}>
          <span style={{ color: 'var(--warn)', flexShrink: 0, marginTop: 1 }}>
            <Icon name="warning" size={14} />
          </span>
          <span className="muted">
            Bu tablo <b>kişileri değil alanları</b> ölçer. TestRail’den gelen
            hesapların çoğu paylaşımlı takım girişidir (<code>testrail1…5</code>)
            ve isimleri zaten kapsadıkları alandır. Bir hesabın robot mu insan
            mı olduğunu ayıran tek işaret <b>yazım payı</b>: yalnızca sonuç
            basan bir hesap boru hattıdır, case yazıp düzenleyen bir hesabın
            başında biri vardır.
          </span>
        </div>
      </div>

      {isFetching && !data ? (
        <div className="skeleton" style={{ width: 300 }} />
      ) : !items.length ? (
        <div className="panel empty">
          <b>Bu dönemde hareket yok</b>
          Seçilen aralıkta hiçbir hesap sonuç girmemiş ya da case yazmamış.
        </div>
      ) : (
        <div className="panel" style={{ overflow: 'auto' }}>
          <table>
            <thead>
              <tr>
                <th>Hesap</th>
                <th style={{ width: 110, textAlign: 'right' }}>Sonuç</th>
                <th style={{ width: 100, textAlign: 'right' }}>Case yazdı</th>
                <th style={{ width: 110, textAlign: 'right' }}>Düzenledi</th>
                <th style={{ width: 90, textAlign: 'right' }}>Koşum</th>
                <th style={{ width: 170 }}>Yazım payı</th>
                <th style={{ width: 230 }}>En çok çalıştığı alan</th>
              </tr>
            </thead>
            <tbody>
              {items.map((u) => (
                <tr key={u.user_id} style={{ cursor: 'default' }}>
                  <td className="title">
                    {u.name}
                    {!u.is_active && (
                      <span className="badge soft" style={{ marginLeft: 6 }}>
                        pasif
                      </span>
                    )}
                    <div className="small faint">{u.email}</div>
                  </td>
                  <td style={{ textAlign: 'right' }}>
                    {u.results.toLocaleString('tr-TR')}
                    {totals?.results ? (
                      <div className="small faint">
                        {bar(u.results, totals.results)}
                      </div>
                    ) : null}
                  </td>
                  <td style={{ textAlign: 'right' }}>
                    {u.cases_created.toLocaleString('tr-TR')}
                  </td>
                  <td style={{ textAlign: 'right' }}>
                    {u.cases_edited.toLocaleString('tr-TR')}
                  </td>
                  <td style={{ textAlign: 'right' }}>
                    {u.runs_created.toLocaleString('tr-TR')}
                  </td>
                  <td className="nowrap">
                    <span className="flakybar" title="case yazma ve düzenlemenin payı">
                      <span style={{ width: `${u.authoring_share}%`,
                                     background: 'var(--accent)' }} />
                    </span>
                    <span className="small muted nowrap"
                          style={{ marginLeft: 8 }}>
                      %{u.authoring_share}
                      {u.authoring_share <= 15 && (
                        <span className="faint"> · boru hattı</span>
                      )}
                    </span>
                  </td>
                  <td className="small muted">
                    {u.projects.length === 0 ? '—' : (
                      <>
                        {u.projects[0].project}
                        {u.projects.length > 1 && (
                          <span className="faint">
                            {' '}+{u.projects.length - 1} alan
                          </span>
                        )}
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}
