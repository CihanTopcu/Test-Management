import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import { Dialog } from '../components/Dialog'
import { Icon } from '../components/Icon'
import { RichText } from '../components/RichText'
import type { Route } from '../route'
import { Crumbs } from '../components/Crumbs'

interface Shared {
  id: number
  title: string
  steps: { content?: string; expected?: string }[]
  step_count: number
  used_by: number
  updated_on: string | null
}

/**
 * Shared steps: a block of steps reused across cases.
 *
 * The usage count matters more than it looks -- editing a block that 400
 * cases point at is a different act from editing one nobody uses, and the
 * screen should say so before somebody finds out afterwards.
 */
export function SharedSteps({ route, projectName }: { route: Route; projectName: string }) {
  const client = useQueryClient()
  const { data: items = [], isLoading } = useQuery({
    queryKey: ['shared-steps', route.project],
    queryFn: () => api.get<Shared[]>(`/api/projects/${route.project}/shared-steps`),
    enabled: !!route.project,
  })

  const [editing, setEditing] = useState<Shared | 'new' | null>(null)
  const isNew = editing === 'new'
  const row = isNew ? null : editing

  const [title, setTitle] = useState('')
  const [steps, setSteps] = useState<{ content: string; expected: string }[]>([])

  const open = (target: Shared | 'new') => {
    setEditing(target)
    if (target === 'new') {
      setTitle('')
      setSteps([{ content: '', expected: '' }])
    } else {
      setTitle(target.title)
      setSteps((target.steps ?? []).map((s) => ({
        content: s.content ?? '', expected: s.expected ?? '',
      })))
    }
  }

  const save = useMutation({
    mutationFn: (body: { title: string; steps: unknown[] }) =>
      row
        ? api.patch(`/api/shared-steps/${row.id}`, body)
        : api.post(`/api/projects/${route.project}/shared-steps`, body),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ['shared-steps', route.project] })
      setEditing(null)
    },
  })

  if (isLoading) {
    return <main className="main"><div className="skeleton" style={{ width: 240 }} /></main>
  }

  return (
    <main className="main">
      <Crumbs projectId={route.project} projectName={projectName} />
      <div className="page-title">
        <h1>Paylaşılan Adımlar</h1>
        <span className="faint small">{items.length} blok</span>
        <button className="primary right" onClick={() => open('new')}>
          <Icon name="plus" size={14} /> Blok ekle
        </button>
      </div>

      {items.length === 0 ? (
        <div className="panel empty">
          <Icon name="list" size={30} />
          <b>Paylaşılan adım yok</b>
          Birden çok case’te tekrar eden adım dizilerini burada bir kez yazıp
          her yerde kullanabilirsiniz.
        </div>
      ) : (
        <div className="panel">
          <table>
            <thead>
              <tr>
                <th>Başlık</th>
                <th style={{ width: 90 }}>Adım</th>
                <th style={{ width: 130 }}>Kullanan case</th>
                <th style={{ width: 120 }}>Güncellendi</th>
              </tr>
            </thead>
            <tbody>
              {items.map((s) => (
                <tr key={s.id} onClick={() => open(s)}>
                  <td className="title"><b>{s.title}</b>
                    {s.steps?.[0]?.content && (
                      <div className="small faint" style={{ marginTop: 3 }}>
                        {String(s.steps[0].content).slice(0, 90)}
                      </div>
                    )}
                  </td>
                  <td className="small muted">{s.step_count}</td>
                  <td>
                    {s.used_by > 0
                      ? <span className="badge soft">{s.used_by} case</span>
                      : <span className="faint small">kullanılmıyor</span>}
                  </td>
                  <td className="small faint">
                    {s.updated_on ? new Date(s.updated_on).toLocaleDateString('tr-TR') : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Dialog open={!!editing} width={760}
              title={isNew ? 'Paylaşılan adım ekle' : `Düzenle: ${row?.title ?? ''}`}
              onClose={() => setEditing(null)}
              footer={<>
                <button onClick={() => setEditing(null)}>Vazgeç</button>
                <button className="primary" disabled={!title || save.isPending}
                        onClick={() => save.mutate({
                          title,
                          steps: steps.filter((s) => s.content || s.expected),
                        })}>
                  {save.isPending ? 'Kaydediliyor…' : 'Kaydet'}
                </button>
              </>}>
        <div className="stack">
          {row && row.used_by > 0 && (
            <div className="error" style={{
              color: 'var(--warn)',
              background: 'color-mix(in srgb, var(--warn) 8%, transparent)',
              borderColor: 'color-mix(in srgb, var(--warn) 30%, transparent)',
            }}>
              Bu blok {row.used_by} case tarafından kullanılıyor — değişiklik
              hepsini etkiler.
            </div>
          )}
          <div className="field">
            <label>Başlık</label>
            <input value={title} autoFocus onChange={(e) => setTitle(e.target.value)} />
          </div>
          <div className="field">
            <label>Adımlar</label>
            {steps.map((step, i) => (
              <div className="steprow" key={i} style={{ marginBottom: 8 }}>
                <div className="num">{i + 1}</div>
                <textarea rows={2} placeholder="Adım" value={step.content}
                          onChange={(e) => setSteps(steps.map((s, j) =>
                            j === i ? { ...s, content: e.target.value } : s))} />
                <textarea rows={2} placeholder="Beklenen sonuç" value={step.expected}
                          onChange={(e) => setSteps(steps.map((s, j) =>
                            j === i ? { ...s, expected: e.target.value } : s))} />
              </div>
            ))}
            <div className="row">
              <button type="button"
                      onClick={() => setSteps([...steps, { content: '', expected: '' }])}>
                <Icon name="plus" size={13} /> Adım ekle
              </button>
              {steps.length > 1 && (
                <button type="button" className="ghost danger"
                        onClick={() => setSteps(steps.slice(0, -1))}>
                  Son adımı sil
                </button>
              )}
            </div>
          </div>
          {row && row.steps?.length > 0 && (
            <div className="field">
              <label>Önizleme</label>
              <div className="steps">
                {steps.filter((s) => s.content || s.expected).map((s, i) => (
                  <div className="step" key={i}>
                    <div className="no">ADIM {i + 1}</div>
                    <RichText value={s.content} />
                    {s.expected && (
                      <div className="expected">
                        <div className="no">BEKLENEN</div>
                        <RichText value={s.expected} />
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
          {save.isError && <div className="error">Kaydedilemedi</div>}
        </div>
      </Dialog>
    </main>
  )
}
