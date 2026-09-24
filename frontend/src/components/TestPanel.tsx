import { useEffect, useRef, useState } from 'react'
import {
  useAddResult, useDeleteResult, useResults, useTest, useUpdateTest, useUsers,
} from '../api/hooks'
import { Confirm } from './Confirm'
import { api } from '../api/client'
import type { Attachment, Catalog } from '../api/types'
import { FieldInput, scopedFields } from './FieldInput'
import { Icon } from './Icon'
import { RichText } from './RichText'
import { StatusBadge } from './Status'
import { href } from '../route'

/**
 * The right-hand panel of a run: what the test asks for, and what happened.
 *
 * Until now this showed a title, a status dropdown and a comment box, so a
 * tester had to open the case in another tab to find out what to do and had
 * nowhere to say which step broke. Both come from data we already migrated --
 * 147,503 case steps and the per-step results TestRail recorded against them.
 */

function fmt(value?: string | null) {
  if (!value) return '—'
  return new Date(value).toLocaleString('tr-TR')
}

interface Pending {
  id: string
  filename: string
}

export function TestPanel({ testId, catalog, projectId, runId, archived,
                            onClose }: {
  testId: number
  catalog?: Catalog
  projectId?: number
  runId?: number | null
  archived: boolean
  onClose: () => void
}) {
  const { data: test, isLoading } = useTest(testId)
  const { data: results = [] } = useResults(testId)
  const { data: users = [] } = useUsers()
  const addResult = useAddResult(runId)
  const updateTest = useUpdateTest(runId)
  const removeResult = useDeleteResult(testId, runId)

  const [statusId, setStatusId] = useState(1)
  const [comment, setComment] = useState('')
  const [elapsed, setElapsed] = useState('')
  const [version, setVersion] = useState('')
  const [defects, setDefects] = useState('')
  const [custom, setCustom] = useState<Record<string, unknown>>({})
  const [stepStatus, setStepStatus] = useState<Record<number, number>>({})
  const [stepActual, setStepActual] = useState<Record<number, string>>({})
  const [pending, setPending] = useState<Pending[]>([])
  const [uploading, setUploading] = useState(false)
  const [byStep, setByStep] = useState(false)
  const [dropping, setDropping] = useState<number | null>(null)
  const input = useRef<HTMLInputElement>(null)

  // a fresh form per test; otherwise half of the previous test's report
  // silently rides along into the next one
  useEffect(() => {
    setStatusId(1); setComment(''); setElapsed(''); setVersion(''); setDefects('')
    setCustom({}); setStepStatus({}); setStepActual({}); setPending([])
    setByStep(false)
  }, [testId])

  const steps = test?.steps ?? []
  const resultFields = catalog ? scopedFields(catalog, projectId, 'result') : []
  const enterable = catalog?.statuses.filter((s) => !s.is_untested) ?? []

  const upload = async (files: FileList | null) => {
    if (!files?.length) return
    setUploading(true)
    try {
      for (const file of Array.from(files)) {
        const up = await api.upload<Attachment>('/api/attachments', file, {
          entity_type: 'result', project_id: projectId,
        })
        setPending((prev) => [...prev, { id: up.id, filename: up.filename }])
      }
    } finally {
      setUploading(false)
    }
  }

  const submit = () => {
    const payload: Record<string, unknown> = {
      status_id: statusId,
      comment: comment || null,
      elapsed: elapsed || null,
      version: version || null,
      defects: defects || null,
    }
    const extra: Record<string, unknown> = {}
    for (const [key, value] of Object.entries(custom)) {
      if (value !== null && value !== '') extra[key] = value
    }
    if (Object.keys(extra).length) payload.custom = extra
    if (pending.length) payload.attachment_ids = pending.map((p) => p.id)
    if (byStep && steps.length) {
      payload.step_results = steps.map((s) => ({
        idx: s.idx,
        content: s.content,
        expected: s.expected,
        actual: stepActual[s.idx] || null,
        status_id: stepStatus[s.idx] ?? null,
      }))
    }
    addResult.mutate({ testId, body: payload }, {
      onSuccess: () => {
        setComment(''); setElapsed(''); setDefects(''); setCustom({})
        setPending([]); setStepActual({}); setStepStatus({})
      },
    })
  }

  // ticking a step failed is the normal way a test fails; carry it up so the
  // overall status does not have to be set twice
  const markStep = (idx: number, id: number) => {
    setStepStatus((prev) => ({ ...prev, [idx]: id }))
    const status = catalog?.statuses.find((s) => s.id === id)
    if (status && !status.is_untested && id !== 1) setStatusId(id)
  }

  if (isLoading || !test) {
    return (
      <div className="detail stack">
        <div className="skeleton" style={{ width: '60%' }} />
        <div className="skeleton" style={{ width: '90%' }} />
      </div>
    )
  }

  return (
    <div className="detail stack">
      <div className="row">
        <span className="idbadge test">T{test.id}</span>
        <b style={{ flex: 1 }}>{test.title}</b>
        <button className="ghost icon-only" onClick={onClose}>
          <Icon name="close" size={15} />
        </button>
      </div>

      <div className="row small faint">
        <StatusBadge catalog={catalog} id={test.status_id} />
        {test.case_id && (
          <a className="right"
             href={href({ page: 'cases', project: projectId, case: test.case_id })}>
            C{test.case_id} case’ine git →
          </a>
        )}
      </div>

      <div className="field" style={{ marginBottom: 0 }}>
        <label>Atanan</label>
        <select value={test.assignedto_id ?? ''} disabled={updateTest.isPending}
                onChange={(e) => updateTest.mutate({
                  testId,
                  patch: { assignedto_id: e.target.value === '' ? null : Number(e.target.value) },
                })}>
          <option value="">— atanmamış —</option>
          {users.filter((u) => u.is_active).map((u) => (
            <option key={u.id} value={u.id}>{u.name}</option>
          ))}
        </select>
      </div>

      {steps.length > 0 && (
        <>
          <div className="section-rule" style={{ marginTop: 6 }}>
            Adımlar ({steps.length})
            {!archived && (
              <label className="row small faint" style={{ gap: 6, fontWeight: 400 }}>
                <input type="checkbox" checked={byStep} style={{ width: 'auto' }}
                       onChange={(e) => setByStep(e.target.checked)} />
                adım adım sonuç gir
              </label>
            )}
          </div>
          <div className="stack">
            {steps.map((s) => (
              <div className="step" key={s.idx}>
                <div className="row small">
                  <b>Adım {s.idx + 1}</b>
                  {s.status_id != null && (
                    <span className="right">
                      <StatusBadge catalog={catalog} id={s.status_id} />
                    </span>
                  )}
                </div>
                <div style={{ marginTop: 5 }}><RichText value={s.content ?? ''} /></div>
                {s.expected && (
                  <>
                    <div className="cap" style={{ marginTop: 7 }}>BEKLENEN</div>
                    <RichText value={s.expected} />
                  </>
                )}
                {byStep && !archived && (
                  <div style={{ marginTop: 8 }}>
                    <div className="chiprow">
                      {enterable.map((st) => (
                        <button key={st.id} type="button"
                                className={`chip-toggle ${stepStatus[s.idx] === st.id ? 'on' : ''}`}
                                onClick={() => markStep(s.idx, st.id)}>
                          {st.label}
                        </button>
                      ))}
                    </div>
                    <textarea rows={2} placeholder="Gerçekleşen sonuç"
                              style={{ marginTop: 6 }}
                              value={stepActual[s.idx] ?? ''}
                              onChange={(e) => setStepActual((prev) => ({
                                ...prev, [s.idx]: e.target.value }))} />
                  </div>
                )}
              </div>
            ))}
          </div>
        </>
      )}

      {archived ? (
        <div className="error" style={{
          color: 'var(--text-dim)', background: 'var(--surface-2)',
          borderColor: 'var(--border)',
        }}>
          Bu koşum arşivde — TestRail’de de salt okunurdu, sonuç eklenemez.
        </div>
      ) : (
        <>
          <div className="section-rule" style={{ marginTop: 6 }}>Sonuç ekle</div>
          <div className="field">
            <label>Durum</label>
            <div className="chiprow">
              {enterable.map((s) => (
                <button key={s.id} type="button"
                        className={`chip-toggle ${statusId === s.id ? 'on' : ''}`}
                        onClick={() => setStatusId(s.id)}>
                  {s.label}
                </button>
              ))}
            </div>
          </div>
          <div className="field">
            <label>Yorum</label>
            <textarea value={comment} onChange={(e) => setComment(e.target.value)} />
          </div>
          <div className="row" style={{ gap: 8 }}>
            <div className="field" style={{ flex: 1 }}>
              <label>Süre</label>
              <input value={elapsed} placeholder="ör. 2m 30s"
                     onChange={(e) => setElapsed(e.target.value)} />
            </div>
            <div className="field" style={{ flex: 1 }}>
              <label>Sürüm</label>
              <input value={version} onChange={(e) => setVersion(e.target.value)} />
            </div>
            <div className="field" style={{ flex: 1 }}>
              <label>Hata kaydı</label>
              <input value={defects} placeholder="JIRA-123"
                     onChange={(e) => setDefects(e.target.value)} />
            </div>
          </div>
          {catalog && resultFields.map((f) => (
            <div className="field" key={f.system_name}>
              <label>{f.label}</label>
              <FieldInput field={f} value={custom[f.system_name]} catalog={catalog}
                          users={users}
                          onChange={(v) => setCustom((c) => ({ ...c, [f.system_name]: v }))} />
            </div>
          ))}

          <div className="field">
            <label>Ekran görüntüsü / ek</label>
            <div className="chiprow" style={{ marginBottom: 6 }}>
              {pending.map((p) => (
                <span key={p.id} className="badge soft">
                  {p.filename}
                  <button className="ghost icon-only" style={{ padding: 0, marginLeft: 4 }}
                          onClick={() => setPending(pending.filter((x) => x.id !== p.id))}>
                    <Icon name="close" size={11} />
                  </button>
                </span>
              ))}
            </div>
            <div className="dropzone" onClick={() => input.current?.click()}
                 onDragOver={(e) => e.preventDefault()}
                 onDrop={(e) => { e.preventDefault(); void upload(e.dataTransfer.files) }}>
              <Icon name="upload" size={15} />
              {uploading ? 'Yükleniyor…' : 'Dosya ekleyin'}
              <input ref={input} type="file" multiple hidden
                     onChange={(e) => { void upload(e.target.files); e.target.value = '' }} />
            </div>
          </div>

          <div>
            <button className="primary" disabled={addResult.isPending || uploading}
                    onClick={submit}>
              {addResult.isPending ? 'Kaydediliyor…' : 'Sonucu kaydet'}
            </button>
            {addResult.isError && (
              <span className="small" style={{ color: 'var(--danger)', marginLeft: 8 }}>
                {(addResult.error as Error).message}
              </span>
            )}
          </div>
        </>
      )}

      <div className="section-rule">Sonuçlar ve yorumlar ({results.length})</div>
      <div className="stack">
        {results.map((r) => (
          <div className="step" key={r.id}>
            <div className="row small">
              <StatusBadge catalog={catalog} id={r.status_id} />
              <span className="right faint">{fmt(r.created_on)}</span>
              {!archived && (
                <button className="ghost danger icon-only" title="Sonucu sil"
                        style={{ padding: 2 }} onClick={() => setDropping(r.id)}>
                  <Icon name="trash" size={12} />
                </button>
              )}
            </div>
            <div className="small faint" style={{ marginTop: 4 }}>
              {users.find((u) => u.id === r.created_by)?.name ?? '—'}
              {r.version && <> · sürüm {r.version}</>}
              {r.elapsed && <> · {r.elapsed}</>}
              {r.defects && <> · hata {r.defects}</>}
            </div>
            {r.comment && <div style={{ marginTop: 6 }}><RichText value={r.comment} /></div>}

            {r.step_results?.length > 0 && (
              <table className="stepresults">
                <tbody>
                  {r.step_results.map((s) => (
                    <tr key={s.idx}>
                      <td className="cid">{s.idx + 1}</td>
                      <td><StatusBadge catalog={catalog} id={s.status_id} /></td>
                      <td className="small">{s.actual || <span className="faint">—</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}

            {r.attachments?.length > 0 && (
              <div className="attachrow" style={{ marginTop: 8 }}>
                {r.attachments.map((a) => (
                  <a key={a.id} href={a.url} target="_blank" rel="noreferrer"
                     className="badge soft">
                    <Icon name="file" size={11} /> {a.filename}
                  </a>
                ))}
              </div>
            )}
          </div>
        ))}
        {!results.length && <span className="faint small">Sonuç yok.</span>}
      </div>

      <Confirm open={dropping !== null} title="Sonucu sil"
               busy={removeResult.isPending}
               error={removeResult.isError
                 ? (removeResult.error as Error).message : null}
               detail={'Bu sonuç ve ekleri silinecek. Testin durumu bir önceki'
                 + ' sonuca göre yeniden hesaplanır.'}
               onClose={() => setDropping(null)}
               onConfirm={() => dropping !== null && removeResult.mutate(dropping, {
                 onSuccess: () => setDropping(null) })} />
    </div>
  )
}
