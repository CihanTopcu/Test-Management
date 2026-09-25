import { useCatalog, useSyncChanges } from '../api/hooks'
import { href } from '../route'
import { IssueRefs } from './IssueRefs'
import { StatusBadge } from './Status'

const time = (value: string | null) => value
  ? new Date(value).toLocaleString('tr-TR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
  : '—'

/**
 * What one TestRail sync pass brought in: who entered which results, in
 * which runs, and which cases changed. The history row only ever said how
 * many ("6 koşum · 5 sonuç").
 */
export function SyncChanges({ syncId }: { syncId: number }) {
  const { data, isLoading, isError } = useSyncChanges(syncId)
  const { data: catalog } = useCatalog()

  if (isLoading) return <div className="skeleton" style={{ width: 240, margin: 12 }} />
  if (isError || !data) return <div className="error" style={{ margin: 12 }}>Ayrıntılar okunamadı.</div>
  if (!data.window) return <div className="faint small" style={{ padding: 12 }}>{data.note}</div>

  const nothing = !data.results.length && !data.runs.length && !data.cases.length
  return (
    <div className="syncchanges">
      <div className="small muted">
        TestRail’de <b>{time(data.window.from)}</b> ile <b>{time(data.window.to)}</b> arasında
        girilen ve değişen kayıtlar. Pencereler yarım saat örtüşür; sınırdaki bir
        kayıt art arda iki geçişte görünebilir.
      </div>

      {nothing && <div className="faint small">Bu geçişte TestRail’den yeni bir şey gelmedi.</div>}

      {data.testers.length > 0 && (
        <div className="chiprow">
          {data.testers.map((t) => (
            <span key={t.name} className="chip-toggle" style={{ cursor: 'default' }}>
              <b>{t.name}</b> · {t.results} sonuç
              <span className="faint">
                {' '}({[t.passed && `${t.passed} geçti`, t.failed && `${t.failed} kaldı`,
                      t.other && `${t.other} diğer`].filter(Boolean).join(', ')})
              </span>
            </span>
          ))}
        </div>
      )}

      {data.results.length > 0 && (
        <>
          <div className="eyebrow">
            Sonuçlar{data.results_total > data.results.length
              && ` · en yeni ${data.results.length} / ${data.results_total}`}
          </div>
          <div className="panel" style={{ overflow: 'auto' }}>
            <table className="grid">
              <thead>
                <tr>
                  <th style={{ width: 96 }}>Zaman</th>
                  <th style={{ width: 150 }}>Testçi</th>
                  <th>Test</th>
                  <th style={{ width: 100 }}>Durum</th>
                  <th>Not · hata</th>
                </tr>
              </thead>
              <tbody>
                {data.results.map((r) => (
                  <tr key={r.id} onClick={() => {
                    location.hash = href({ page: 'runs', project: r.project_id, run: r.run_id, test: r.test_id })
                  }}>
                    <td className="small muted nowrap">{time(r.created_on)}</td>
                    <td className="small ellipsis" title={r.tester}>{r.tester}</td>
                    <td className="title">
                      {r.test_title}
                      <div className="small faint ellipsis" title={r.run_name}>
                        {r.project} · {r.run_name}
                      </div>
                    </td>
                    <td><StatusBadge catalog={catalog} id={r.status_id} /></td>
                    <td className="small">
                      {r.defects && <IssueRefs text={r.defects} />}
                      {r.comment && <div className="muted">{r.comment}</div>}
                      {!r.defects && !r.comment && <span className="faint">—</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {data.runs.length > 0 && (
        <>
          <div className="eyebrow">Koşumlar</div>
          <div className="panel">
            <table className="grid">
              <tbody>
                {data.runs.map((r) => (
                  <tr key={r.id} onClick={() => {
                    location.hash = href({ page: 'runs', project: r.project_id, run: r.id })
                  }}>
                    <td className="title">
                      {r.name}
                      <div className="small faint">{r.project}</div>
                    </td>
                    <td className="small muted" style={{ width: 170 }}>
                      {r.new ? 'açıldı' : 'güncellendi'}
                      {r.created_by && <> · {r.created_by}</>}
                    </td>
                    <td className="small" style={{ width: 90, textAlign: 'right' }}>
                      {r.results ? `${r.results} sonuç` : <span className="faint">sonuç yok</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {data.cases.length > 0 && (
        <>
          <div className="eyebrow">Case’ler</div>
          <div className="panel">
            <table className="grid">
              <tbody>
                {data.cases.map((c) => (
                  <tr key={c.id} onClick={() => {
                    location.hash = href({ page: 'cases', project: c.project_id, case: c.id })
                  }}>
                    <td className="cid" style={{ width: 108 }}>C{c.id}</td>
                    <td className="title">
                      {c.title}
                      <div className="small faint">{c.project}</div>
                    </td>
                    <td className="small muted" style={{ width: 210 }}>
                      {c.new ? 'eklendi' : 'değişti'} · {c.updated_by ?? '—'} · {time(c.updated_on)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}
