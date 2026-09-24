import { useState } from 'react'
import {
  useDuplicateCases, useFlakyTests, useNeverRunCases,
} from '../api/hooks'
import { Icon } from '../components/Icon'
import { href } from '../route'

/**
 * The three things the migrated data says about the case library itself.
 *
 * Not invented report templates: each of these came out of auditing what was
 * imported. A test that both passes and fails teaches people to re-run
 * rather than read; a case duplicated in its own folder is executed twice
 * every regression; a case nobody has ever run is a case nobody maintains.
 */

type Tab = 'flaky' | 'duplicates' | 'never'

const TABS: [Tab, string][] = [
  ['flaky', 'Kararsız testler'],
  ['duplicates', 'Yinelenen başlıklar'],
  ['never', 'Hiç koşulmamış'],
]

function fmtDate(value: string | null) {
  if (!value) return '—'
  return new Date(value).toLocaleDateString('tr-TR')
}

export function QualityReport({ projectId }: { projectId?: number }) {
  const [tab, setTab] = useState<Tab>('flaky')
  const [days, setDays] = useState(90)

  const flaky = useFlakyTests(projectId, tab === 'flaky' ? days : 0)
  const duplicates = useDuplicateCases(tab === 'duplicates' ? projectId : undefined)
  const neverRun = useNeverRunCases(tab === 'never' ? projectId : undefined)

  return (
    <>
      <div className="section-rule">Case kütüphanesinin sağlığı</div>

      <div className="subtabs">
        {TABS.map(([key, label]) => (
          <button key={key} className={tab === key ? 'active' : ''}
                  onClick={() => setTab(key)}>{label}</button>
        ))}
      </div>

      {tab === 'flaky' && (
        <>
          <div className="toolbar">
            <span className="faint small grow">
              Hem geçen hem kalan testler — seçilen dönemde en az 3 kez her iki
              sonucu da vermiş olanlar.
            </span>
            <select style={{ width: 150 }} value={days}
                    onChange={(e) => setDays(Number(e.target.value))}>
              <option value={30}>Son 30 gün</option>
              <option value={90}>Son 90 gün</option>
              <option value={365}>Son 1 yıl</option>
            </select>
          </div>

          {flaky.isFetching ? (
            <div className="skeleton" style={{ width: 280 }} />
          ) : !flaky.data?.items.length ? (
            <div className="panel empty">
              <b>Kararsız test yok</b>
              Seçilen dönemde hem geçip hem kalan bir test bulunmuyor.
            </div>
          ) : (
            <div className="panel" style={{ overflow: 'auto' }}>
              <table>
                <thead>
                  <tr>
                    <th style={{ width: 90 }}>Case</th>
                    <th>Başlık</th>
                    <th style={{ width: 120, textAlign: 'right' }}>Kararsızlık</th>
                    <th style={{ width: 150 }}>Geçti / Kaldı</th>
                    <th style={{ width: 110 }}>Son görülme</th>
                  </tr>
                </thead>
                <tbody>
                  {flaky.data.items.map((f) => (
                    <tr key={f.case_id} onClick={() => {
                      location.hash = href({ page: 'cases', project: projectId,
                                             case: f.case_id })
                    }}>
                      <td className="cid">C{f.case_id}</td>
                      <td className="title">{f.title}</td>
                      <td style={{ textAlign: 'right' }}>
                        <b style={{ color: f.flip_rate >= 35 ? 'var(--danger)'
                          : f.flip_rate >= 20 ? 'var(--warn)' : 'var(--text-dim)' }}>
                          %{f.flip_rate}
                        </b>
                      </td>
                      <td>
                        <span className="flakybar" title={`${f.runs} sonuç`}>
                          <span style={{ width: `${100 * f.passed / f.runs}%`,
                                         background: 'var(--passed)' }} />
                          <span style={{ width: `${100 * f.failed / f.runs}%`,
                                         background: 'var(--failed)' }} />
                        </span>
                        <span className="small muted" style={{ marginLeft: 8 }}>
                          {f.passed} / {f.failed}
                        </span>
                      </td>
                      <td className="small muted">{fmtDate(f.last_seen)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {tab === 'duplicates' && (
        <>
          <div className="toolbar">
            <span className="faint small grow">
              Aynı bölümde aynı başlığı taşıyan case’ler. Her regresyonda iki
              kez koşuluyorlar.
            </span>
          </div>
          {!duplicates.data?.items.length ? (
            <div className="panel empty">
              <b>Yinelenen başlık yok</b>
              Bu projede aynı bölümde aynı başlıkla duran case bulunmuyor.
            </div>
          ) : (
            <div className="panel" style={{ overflow: 'auto' }}>
              <table>
                <thead>
                  <tr>
                    <th>Başlık</th>
                    <th style={{ width: 220 }}>Bölüm</th>
                    <th style={{ width: 70, textAlign: 'right' }}>Adet</th>
                    <th style={{ width: 260 }}>Case’ler</th>
                  </tr>
                </thead>
                <tbody>
                  {duplicates.data.items.map((d) => (
                    <tr key={`${d.section_id}-${d.title}`} style={{ cursor: 'default' }}>
                      <td className="title">{d.title}</td>
                      <td className="small muted">{d.section_name}</td>
                      <td style={{ textAlign: 'right' }}>
                        <b style={{ color: d.count > 2 ? 'var(--danger)' : undefined }}>
                          {d.count}
                        </b>
                      </td>
                      <td className="small">
                        {d.case_ids.slice(0, 6).map((id) => (
                          <a key={id} style={{ marginRight: 8 }}
                             href={href({ page: 'cases', project: projectId, case: id })}>
                            C{id}
                          </a>
                        ))}
                        {d.count > 6 && <span className="faint">+{d.count - 6}</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {tab === 'never' && (
        <>
          <div className="toolbar">
            <span className="faint small grow">
              Hiçbir koşuma girmemiş aktif case’ler. Bir özellikten önce
              yazılmış olabilirler; kimse koşmuyorsa kimse de bakmıyor
              demektir.
            </span>
            {neverRun.data && (
              <span className="faint small nowrap">
                {neverRun.data.total.toLocaleString('tr-TR')} case
              </span>
            )}
          </div>
          {!neverRun.data?.items.length ? (
            <div className="panel empty">
              <b>Hepsi koşulmuş</b>
              Bu projedeki her aktif case en az bir koşuma girmiş.
            </div>
          ) : (
            <div className="panel" style={{ overflow: 'auto' }}>
              <table>
                <thead>
                  <tr>
                    <th style={{ width: 90 }}>Case</th>
                    <th>Başlık</th>
                    <th style={{ width: 260 }}>Bölüm</th>
                    <th style={{ width: 120 }}>Oluşturuldu</th>
                  </tr>
                </thead>
                <tbody>
                  {neverRun.data.items.map((c) => (
                    <tr key={c.case_id} onClick={() => {
                      location.hash = href({ page: 'cases', project: projectId,
                                             case: c.case_id })
                    }}>
                      <td className="cid">C{c.case_id}</td>
                      <td className="title">{c.title}</td>
                      <td className="small muted">{c.section_name}</td>
                      <td className="small muted">{fmtDate(c.created_on)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {neverRun.data.total > neverRun.data.items.length && (
                <div className="faint small" style={{ padding: 10 }}>
                  <Icon name="list" size={12} /> İlk {neverRun.data.items.length}{' '}
                  gösteriliyor, toplam {neverRun.data.total.toLocaleString('tr-TR')}.
                </div>
              )}
            </div>
          )}
        </>
      )}
    </>
  )
}
