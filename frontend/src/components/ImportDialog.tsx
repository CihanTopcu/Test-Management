import { useRef, useState } from 'react'
import { useImportCases, useImportTargets, type ImportReport } from '../api/hooks'
import { Dialog } from './Dialog'
import { Icon } from './Icon'

/**
 * Spreadsheet import, in two passes.
 *
 * The first pass never writes: it reads the file, guesses which column means
 * what and reports exactly what would be created. Only after the mapping is
 * confirmed does the second pass insert anything -- because an import that
 * guesses wrong across 500 rows is far more work to undo than to check.
 */
export function ImportDialog({ suiteId, sectionId, open, onClose }: {
  suiteId?: number
  sectionId?: number
  open: boolean
  onClose: () => void
}) {
  const { data: targets } = useImportTargets()
  const run = useImportCases(suiteId)
  const input = useRef<HTMLInputElement>(null)

  const [file, setFile] = useState<File | null>(null)
  const [report, setReport] = useState<ImportReport | null>(null)
  const [mapping, setMapping] = useState<Record<string, string>>({})
  const [done, setDone] = useState<number | null>(null)

  const reset = () => {
    setFile(null); setReport(null); setMapping({}); setDone(null); run.reset()
  }

  const preview = (chosen: File, override?: Record<string, string>) => {
    setFile(chosen)
    setDone(null)
    run.mutate({ file: chosen, sectionId, dryRun: true, mapping: override },
               { onSuccess: (r) => { setReport(r); setMapping(r.mapping) } })
  }

  const commit = () => {
    if (!file) return
    run.mutate({ file, sectionId, dryRun: false, mapping },
               { onSuccess: (r) => setDone(r.created) })
  }

  const options = [
    ...(targets?.builtin ?? []).map((t) => ({ key: t.key, label: t.label })),
    ...(targets?.custom ?? []).map((t) => ({ key: t.key, label: t.label })),
  ]

  return (
    <Dialog open={open} title="CSV / Excel içe aktar" width={720}
            onClose={() => { reset(); onClose() }}
            footer={<>
              <button onClick={() => { reset(); onClose() }}>Kapat</button>
              {report && done === null && (
                <button className="primary" disabled={run.isPending}
                        onClick={commit}>
                  {run.isPending ? 'Aktarılıyor…'
                    : `${report.would_create} case oluştur`}
                </button>
              )}
            </>}>
      <div className="stack">
        {!report && (
          <div className="dropzone" style={{ padding: 28 }}
               onClick={() => input.current?.click()}
               onDragOver={(e) => e.preventDefault()}
               onDrop={(e) => {
                 e.preventDefault()
                 const f = e.dataTransfer.files?.[0]
                 if (f) preview(f)
               }}>
            <Icon name="upload" size={18} />
            {run.isPending ? 'Dosya okunuyor…'
              : '.csv veya .xlsx dosyasını sürükleyin ya da seçmek için tıklayın'}
            <input ref={input} type="file" hidden accept=".csv,.xlsx,.xlsm"
                   onChange={(e) => {
                     const f = e.target.files?.[0]
                     e.target.value = ''
                     if (f) preview(f)
                   }} />
          </div>
        )}

        {run.isError && (
          <div className="error">{(run.error as Error).message}</div>
        )}

        {report && done === null && (
          <>
            <div className="row small faint">
              <span>{file?.name}</span>
              <span>· {report.total_rows} satır</span>
              <button className="ghost small right" onClick={reset}>
                Başka dosya
              </button>
            </div>

            <div className="section-rule">Sütun eşleştirme</div>
            <div className="panel" style={{ padding: 12, maxHeight: 220, overflow: 'auto' }}>
              {report.headers.map((header) => (
                <div className="row" key={header} style={{ gap: 10, marginBottom: 6 }}>
                  <span className="small" style={{ flex: 1 }}>{header}</span>
                  <select style={{ maxWidth: 260 }} value={mapping[header] ?? ''}
                          onChange={(e) => setMapping({
                            ...mapping, [header]: e.target.value })}>
                    <option value="">— içe aktarma —</option>
                    {options.map((o) => (
                      <option key={o.key} value={o.key}>{o.label}</option>
                    ))}
                  </select>
                </div>
              ))}
            </div>
            <button className="ghost small" disabled={!file || run.isPending}
                    onClick={() => file && preview(file, mapping)}>
              <Icon name="filter" size={13} /> Eşleştirmeyi uygula ve yeniden önizle
            </button>

            {report.new_sections.length > 0 && (
              <div className="small muted">
                Yeni açılacak bölümler: {report.new_sections.join(', ')}
              </div>
            )}

            <div className="section-rule">Önizleme</div>
            <table>
              <thead>
                <tr><th>Başlık</th><th style={{ width: 160 }}>Bölüm</th>
                    <th style={{ width: 70 }}>Adım</th></tr>
              </thead>
              <tbody>
                {report.sample.map((row, i) => (
                  <tr key={i}>
                    <td className="title">{row.title}</td>
                    <td className="small muted">{row.section || '—'}</td>
                    <td className="small">{row.steps}</td>
                  </tr>
                ))}
              </tbody>
            </table>

            {report.skipped.length > 0 && (
              <div className="error" style={{ marginTop: 8 }}>
                <b>{report.skipped.length} satır atlanacak</b>
                <ul style={{ margin: '6px 0 0 16px' }}>
                  {report.skipped.slice(0, 5).map((s, i) => <li key={i}>{s}</li>)}
                </ul>
              </div>
            )}
          </>
        )}

        {done !== null && (
          <div className="panel empty">
            <b>{done} case içe aktarıldı</b>
            <span className="faint small">Listeyi yenilemek için pencereyi kapatın.</span>
          </div>
        )}
      </div>
    </Dialog>
  )
}
