import { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, getToken } from '../api/client'
import { Crumbs } from '../components/Crumbs'
import { Dialog } from '../components/Dialog'
import { Icon } from '../components/Icon'
import { href, type Route } from '../route'

interface RunSummary {
  id: number
  scenario_id: number
  status: 'queued' | 'running' | 'passed' | 'failed' | 'error' | 'stopped'
  message: string | null
  created_on: string
  started_on: string | null
  finished_on: string | null
  started_by: string | null
  passed: number
  total: number
}

interface StepLog {
  line: number
  text: string
  status: 'pending' | 'running' | 'passed' | 'failed' | 'skipped'
  message?: string
  note?: string
  ms?: number
  shot?: number
  depth?: number
  row?: number
  kind?: 'row'
}

interface RunDetail extends RunSummary {
  log: StepLog[]
  steps: string
}

interface Scenario {
  id: number
  project_id: number
  name: string
  description: string | null
  steps: string
  updated_on: string
  updated_by: string | null
  last_run: RunSummary | null
  case_id: number | null
  case_title: string | null
  data: string | null
}

interface Variable {
  id: number
  name: string
  is_secret: boolean
  value: string | null
  has_value: boolean
  readable: boolean
  updated_by: string | null
}

interface Config { ai: boolean; headless: boolean; commands: string[]; builtins: string[] }
interface LineError { line: number; message: string }

const LIVE = new Set(['queued', 'running'])

const RUN_LABEL: Record<RunSummary['status'], string> = {
  queued: 'Başlıyor', running: 'Koşuyor', passed: 'Geçti', failed: 'Kaldı',
  error: 'Hata', stopped: 'Durduruldu',
}

const STARTER = `# Her satıra bir komut. Sağdaki listeden komut ekleyebilirsiniz.
Git https://www.dgpays.com
Gör "DGPays"
`

const time = (value: string | null) => value
  ? new Date(value).toLocaleString('tr-TR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
  : '—'

function RunPill({ run }: { run: Pick<RunSummary, 'status' | 'passed' | 'total'> }) {
  return (
    <span className={`runpill ${run.status}`}>
      {LIVE.has(run.status) && <span className="pulse" />}
      {RUN_LABEL[run.status]}
      {run.total > 0 && !LIVE.has(run.status) && <span className="faint"> · {run.passed}/{run.total}</span>}
    </span>
  )
}

/** A step's screenshot. Fetched with the bearer token, since an <img> alone
 *  cannot send it. */
function Shot({ runId, index, onOpen, large = false }: {
  runId: number; index: number; onOpen?: () => void; large?: boolean
}) {
  const [url, setUrl] = useState<string | null>(null)
  useEffect(() => {
    let alive = true
    let made: string | null = null
    fetch(`/api/autotest/runs/${runId}/shots/${index}`, {
      headers: { Authorization: `Bearer ${getToken() ?? ''}` },
    }).then((r) => (r.ok ? r.blob() : null)).then((blob) => {
      if (!alive || !blob) return
      made = URL.createObjectURL(blob)
      setUrl(made)
    }).catch(() => {})
    return () => { alive = false; if (made) URL.revokeObjectURL(made) }
  }, [runId, index])
  if (!url) return <div className={large ? 'shot-large skeleton' : 'shot-thumb skeleton'} />
  return large
    ? <img className="shot-large" src={url} alt={`${index + 1}. adımın ekran görüntüsü`} />
    : (
      <button className="shot-thumb" onClick={onOpen} title="Büyüt">
        <img src={url} alt={`${index + 1}. adımın ekran görüntüsü`} />
      </button>
    )
}

function StepIcon({ status }: { status: StepLog['status'] }) {
  if (status === 'passed') return <span className="stepicon passed" aria-label="geçti"><Icon name="check-circle" size={15} /></span>
  if (status === 'failed') return <span className="stepicon failed" aria-label="kaldı"><Icon name="warning" size={15} /></span>
  if (status === 'running') return <span className="stepicon running" aria-label="koşuyor"><span className="pulse" /></span>
  return <span className={`stepicon ${status}`} aria-label={status === 'skipped' ? 'atlandı' : 'sırada'}>·</span>
}

function RunView({ runId, onStop }: { runId: number; onStop: () => void }) {
  const { data: run } = useQuery({
    queryKey: ['autotest-run', runId],
    queryFn: () => api.get<RunDetail>(`/api/autotest/runs/${runId}`),
    refetchInterval: (q) => (q.state.data && !LIVE.has(q.state.data.status) ? false : 700),
  })
  const [zoom, setZoom] = useState<StepLog | null>(null)
  if (!run) return <div className="skeleton" style={{ width: 260, margin: 16 }} />

  const took = run.started_on && run.finished_on
    ? ((new Date(run.finished_on).getTime() - new Date(run.started_on).getTime()) / 1000).toFixed(1)
    : null
  return (
    <div className="autorun">
      <div className="autorun-head">
        <RunPill run={run} />
        <span className="small muted">
          #{run.id} · {run.started_by ?? '—'} · {time(run.created_on)}
          {took && <> · {took} sn</>}
        </span>
        {LIVE.has(run.status) && (
          <button className="ghost danger small right" onClick={onStop}>
            <Icon name="close" size={12} /> Durdur
          </button>
        )}
      </div>
      {run.message && <div className="error small" style={{ margin: '0 0 10px' }}>{run.message}</div>}
      {run.status === 'queued' && (
        <div className="faint small" style={{ padding: '6px 2px' }}>Tarayıcı açılıyor…</div>
      )}
      <ol className="steplog">
        {run.log.map((s, i) => (
          s.kind === 'row' ? (
            <li key={i} className={`rowhead ${s.status}`}>
              <StepIcon status={s.status} />
              <b className="small">{s.text}</b>
            </li>
          ) : (
          <li key={i} className={s.status}
              style={s.depth ? { paddingLeft: 4 + s.depth * 20 } : undefined}>
            <StepIcon status={s.status} />
            <div className="steplog-body">
              <code>{s.text}</code>
              {s.message && <div className="steplog-msg">{s.message}</div>}
              {s.note && <div className="faint small ellipsis" title={s.note}>{s.note}</div>}
            </div>
            <span className="faint small nowrap">{s.ms != null ? `${(s.ms / 1000).toFixed(1)} sn` : ''}</span>
            {s.shot != null
              ? <Shot runId={run.id} index={s.shot} onOpen={() => setZoom(s)} />
              : <span className="shot-thumb empty-shot" />}
          </li>
          )
        ))}
      </ol>
      <Dialog open={zoom != null} title={zoom ? `${zoom.line}. satır: ${zoom.text}` : ''}
              onClose={() => setZoom(null)} width={1100}>
        {zoom?.shot != null && <Shot runId={run.id} index={zoom.shot} large />}
      </Dialog>
    </div>
  )
}

function Editor({ scenario, config, projectId, varsVersion, onSaved, onDeleted }: {
  scenario: Scenario | null
  config: Config | undefined
  projectId: number
  /** bumps when the variables change, so undefined-name errors refresh */
  varsVersion: number
  onSaved: (s: Scenario) => void
  onDeleted: () => void
}) {
  const client = useQueryClient()
  const [name, setName] = useState(scenario?.name ?? '')
  const [steps, setSteps] = useState(scenario?.steps ?? STARTER)
  const [description, setDescription] = useState(scenario?.description ?? '')
  const [caseRef, setCaseRef] = useState(scenario?.case_id ? `C${scenario.case_id}` : '')
  const caseId = caseRef.trim() ? Number(caseRef.trim().replace(/^c/i, '')) || null : null
  const [startUrl, setStartUrl] = useState('')
  const [drafting, setDrafting] = useState(!scenario)
  const [errors, setErrors] = useState<LineError[]>([])
  const [data, setData] = useState(scenario?.data ?? '')
  const [dataInfo, setDataInfo] = useState<{ rows: number; error: string | null }>({ rows: 0, error: null })
  const [runId, setRunId] = useState<number | null>(scenario?.last_run?.id ?? null)
  const area = useRef<HTMLTextAreaElement>(null)
  const gutter = useRef<HTMLDivElement>(null)

  const dirty = !scenario || name !== scenario.name || steps !== scenario.steps
    || caseId !== scenario.case_id
    || (data || '') !== (scenario.data || '')
    || (description || '') !== (scenario.description || '')

  // the language is checked as it is typed, by the same parser the runner uses
  useEffect(() => {
    const t = setTimeout(() => {
      api.post<{ errors: LineError[]; rows: number; data_error: string | null }>(
        '/api/autotest/check', { steps, project_id: projectId, data: data || null })
        .then((r) => { setErrors(r.errors); setDataInfo({ rows: r.rows, error: r.data_error }) })
        .catch(() => {})
    }, 350)
    return () => clearTimeout(t)
  }, [steps, data, projectId, varsVersion])

  const history = useQuery({
    queryKey: ['autotest-runs', scenario?.id],
    queryFn: () => api.get<RunSummary[]>(`/api/autotest/scenarios/${scenario!.id}/runs`),
    enabled: !!scenario,
    refetchInterval: (q) => (q.state.data?.some((r) => LIVE.has(r.status)) ? 1500 : false),
  })

  const refresh = () => {
    client.invalidateQueries({ queryKey: ['autotest-scenarios', projectId] })
    client.invalidateQueries({ queryKey: ['autotest-runs', scenario?.id] })
  }

  const save = useMutation({
    mutationFn: () => scenario
      ? api.patch<Scenario>(`/api/autotest/scenarios/${scenario.id}`, { name, steps, description: description || null, case_id: caseId, data: data || null })
      : api.post<Scenario>(`/api/projects/${projectId}/autotest/scenarios`, { name, steps, description: description || null, case_id: caseId, data: data || null }),
    onSuccess: (s) => { refresh(); onSaved(s) },
  })

  const run = useMutation({
    mutationFn: async () => {
      const saved = dirty ? await save.mutateAsync() : scenario!
      return api.post<RunDetail>(`/api/autotest/scenarios/${saved.id}/runs`, {})
    },
    onSuccess: (r) => { setRunId(r.id); refresh() },
  })

  const stop = useMutation({
    mutationFn: (id: number) => api.post(`/api/autotest/runs/${id}/stop`, {}),
    onSuccess: () => { client.invalidateQueries({ queryKey: ['autotest-run', runId] }); refresh() },
  })

  const remove = useMutation({
    mutationFn: () => api.del(`/api/autotest/scenarios/${scenario!.id}`),
    onSuccess: () => { refresh(); onDeleted() },
  })

  const draft = useMutation({
    mutationFn: () => api.post<{ steps: string; errors: LineError[] }>('/api/autotest/draft', {
      project_id: projectId, text: description, start_url: startUrl || null,
    }),
    onSuccess: (r) => {
      const hasOwn = steps.trim() && steps !== STARTER
      if (!hasOwn || confirm('Mevcut adımların yerine yapay zekânın taslağı yazılsın mı?')) {
        setSteps(r.steps)
      }
    },
  })

  const insert = (usage: string) => {
    const line = usage.split(' — ')[0]
    const el = area.current
    const at = el ? el.selectionEnd : steps.length
    const before = steps.slice(0, at)
    const lead = before && !before.endsWith('\n') ? '\n' : ''
    setSteps(before + lead + line + '\n' + steps.slice(at))
    requestAnimationFrame(() => el?.focus())
  }

  const lines = steps.split('\n').length
  const bad = new Set(errors.map((e) => e.line))
  const live = history.data?.find((r) => LIVE.has(r.status))
  const busy = run.isPending || !!live
  const problem = (save.error || run.error || draft.error || remove.error) as Error | null

  return (
    <div className="autoedit">
      <div className="autoedit-top">
        <input className="autoname" value={name} onChange={(e) => setName(e.target.value)}
               placeholder="Senaryo adı, ör. Kart ile giriş" aria-label="Senaryo adı" />
        <button className="ghost" disabled={!dirty || !name.trim() || save.isPending}
                onClick={() => save.mutate()}>
          Kaydet
        </button>
        <button className="primary" disabled={!name.trim() || errors.length > 0 || busy}
                onClick={() => run.mutate()}
                title={errors.length ? 'Önce hatalı satırları düzeltin' : undefined}>
          <Icon name="play" size={14} /> {busy ? 'Koşuyor…' : 'Test et'}
        </button>
        {scenario && (
          <button className="ghost danger" aria-label="Senaryoyu sil" title="Sil"
                  onClick={() => confirm(`"${scenario.name}" silinsin mi? Koşum geçmişi de silinir.`) && remove.mutate()}>
            <Icon name="trash" size={14} />
          </button>
        )}
      </div>
      {problem && <div className="error small" style={{ marginBottom: 10 }}>{problem.message}</div>}

      <details className="panel autodraft" open={drafting}
               onToggle={(e) => setDrafting((e.target as HTMLDetailsElement).open)}>
        <summary>
          <Icon name="sparkle" size={14} /> Düz metinden oluştur
          <span className="faint small"> — ne test edileceğini yazın, adımlara yapay zekâ çevirsin</span>
        </summary>
        <textarea rows={4} value={description} onChange={(e) => setDescription(e.target.value)}
                  placeholder="ör. dgpays.com'a git, İletişim sayfasını aç, formu boş gönder ve zorunlu alan uyarısını gör" />
        <div className="toolbar" style={{ margin: '8px 0 0' }}>
          <input className="grow" value={startUrl} onChange={(e) => setStartUrl(e.target.value)}
                 placeholder="Başlangıç adresi (isteğe bağlı), ör. https://www.dgpays.com" />
          <button className="ghost" disabled={!config?.ai || description.trim().length < 3 || draft.isPending}
                  onClick={() => draft.mutate()}
                  title={config?.ai ? undefined : 'Sunucuda ANTHROPIC_API_KEY tanımlı değil'}>
            <Icon name="sparkle" size={14} /> {draft.isPending ? 'Çevriliyor…' : 'Komutlara çevir'}
          </button>
        </div>
        {!config?.ai && (
          <div className="faint small" style={{ marginTop: 6 }}>
            Yapay zekâ henüz ayarlı değil; komutları aşağıya kendiniz yazabilirsiniz.
            Metin yine de senaryonun açıklaması olarak kaydedilir.
          </div>
        )}
      </details>

      <div className="autogrid">
        <div>
          <div className="eyebrow" style={{ marginBottom: 6 }}>Adımlar</div>
          <div className={`codebox ${errors.length ? 'has-errors' : ''}`}>
            <div className="gutter" ref={gutter} aria-hidden>
              {Array.from({ length: lines }, (_, i) => (
                <div key={i} className={bad.has(i + 1) ? 'bad' : ''}>{i + 1}</div>
              ))}
            </div>
            <textarea ref={area} value={steps} spellCheck={false} aria-label="Senaryo adımları"
                      onChange={(e) => setSteps(e.target.value)}
                      onKeyDown={(e) => {
                        // Tab indents inside a block instead of leaving the editor
                        if (e.key !== 'Tab' || e.shiftKey) return
                        e.preventDefault()
                        const el = e.currentTarget
                        const at = el.selectionStart
                        setSteps(steps.slice(0, at) + '  ' + steps.slice(el.selectionEnd))
                        requestAnimationFrame(() => el.setSelectionRange(at + 2, at + 2))
                      }}
                      onScroll={(e) => { if (gutter.current) gutter.current.scrollTop = e.currentTarget.scrollTop }}
                      rows={Math.max(10, Math.min(lines + 2, 26))} />
          </div>
          {errors.length > 0 && (
            <ul className="lineerrors">
              {errors.map((e) => <li key={`${e.line}-${e.message}`}><b>{e.line}. satır:</b> {e.message}</li>)}
            </ul>
          )}

          <details className="datasetbox" open={!!data}>
            <summary className="eyebrow">
              Veri seti {dataInfo.rows > 0 && <span className="faint">· {dataInfo.rows} satır, senaryo her satır için ayrı koşar</span>}
            </summary>
            <textarea value={data} onChange={(e) => setData(e.target.value)} spellCheck={false}
                      rows={Math.max(4, Math.min(data.split('\n').length + 1, 12))}
                      aria-label="Veri seti"
                      placeholder={'İlk satır sütun adları, sonrakiler değerler. Excel\'den kopyalayıp yapıştırabilirsiniz.\nEPOSTA;SIFRE;BEKLENEN\nali@dgpays.com;Parola1;Hoş geldiniz\nhatali@dgpays.com;yanlis;Hatalı giriş'} />
            {dataInfo.error
              ? <div className="lineerrors">{dataInfo.error}</div>
              : <div className="faint small">Sütunlar adımlarda <code>{'{{EPOSTA}}'}</code> gibi kullanılır; <code>{'{{satir}}'}</code> kaçıncı satır olduğudur.</div>}
          </details>
        </div>
        <aside className="cheats">
          <div className="eyebrow" style={{ marginBottom: 6 }}>Komutlar</div>
          <div className="cheatlist">
          {config?.commands.map((c) => {
            const [usage, what] = c.split(' — ')
            return (
              <button key={c} className="cheat" onClick={() => insert(c)} title="Satır ekle">
                <code>{usage}</code>
                {what && <span className="faint small">{what}</span>}
              </button>
            )
          })}
          </div>
          <div className="eyebrow" style={{ margin: '12px 0 6px' }}>Hazır değerler</div>
          <div className="chiprow">
            {config?.builtins.map((b) => (
              <button key={b} className="chip-toggle small" title="İmlecin olduğu yere ekle"
                      onClick={() => {
                        const el = area.current
                        const at = el ? el.selectionEnd : steps.length
                        setSteps(steps.slice(0, at) + `{{${b}}}` + steps.slice(at))
                      }}>
                {b}
              </button>
            ))}
          </div>
          <div className="faint small" style={{ marginTop: 8 }}>
            Hedef, ekranda görünen yazıdır: düğme metni, alan etiketi ya da alanın içindeki ipucu.
            Başka bir şey için <code>"css:#id"</code> kullanın.
          </div>
          <div className="faint small" style={{ marginTop: 8 }}>
            Adres, kullanıcı ya da şifre için <code>{'{{AD}}'}</code> yazın; değerini
            yukarıdaki <b>Değişkenler</b>'den verin. Gizli değerler kayıtta görünmez.
          </div>
          <div className="field" style={{ margin: '14px 0 0' }}>
            <label htmlFor="autocase">Bağlı case</label>
            <input id="autocase" value={caseRef} onChange={(e) => setCaseRef(e.target.value)}
                   placeholder="ör. C15477" />
            {scenario?.case_id && scenario.case_id === caseId && (
              <a className="small ellipsis" style={{ display: 'block', marginTop: 4 }}
                 href={href({ page: 'cases', project: projectId, case: scenario.case_id })}>
                {scenario.case_title ?? `C${scenario.case_id}`}
              </a>
            )}
            <div className="faint small" style={{ marginTop: 4 }}>
              Bağlıysa, koşumlarda bu case’in testinde “Otomasyonla koş” çıkar ve sonuç teste yazılır.
            </div>
          </div>
        </aside>
      </div>

      {config && !config.headless && (
        <div className="faint small" style={{ margin: '10px 0 4px' }}>
          <Icon name="external" size={12} /> Test et dediğinizde tarayıcı bu bilgisayarda açılır ve adımları siz izlerken uygular.
        </div>
      )}

      {runId != null && (
        <>
          <div className="eyebrow" style={{ margin: '18px 0 8px' }}>Koşum</div>
          <RunView key={runId} runId={runId} onStop={() => stop.mutate(runId)} />
        </>
      )}

      {(history.data?.length ?? 0) > 1 && (
        <>
          <div className="eyebrow" style={{ margin: '18px 0 8px' }}>Geçmiş</div>
          <div className="chiprow">
            {history.data!.map((r) => (
              <button key={r.id} className={`chip-toggle ${r.id === runId ? 'on' : ''}`}
                      onClick={() => setRunId(r.id)}>
                #{r.id} <RunPill run={r} /> <span className="faint">{time(r.created_on)}</span>
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

function VariablesDialog({ open, projectId, onClose, onChanged }: {
  open: boolean; projectId: number; onClose: () => void; onChanged: () => void
}) {
  const client = useQueryClient()
  const key = ['autotest-variables', projectId]
  const { data: items = [] } = useQuery({
    queryKey: key,
    queryFn: () => api.get<Variable[]>(`/api/projects/${projectId}/autotest/variables`),
    enabled: open,
  })
  const [name, setName] = useState('')
  const [value, setValue] = useState('')
  const [secret, setSecret] = useState(false)
  const [editing, setEditing] = useState<number | null>(null)
  const [draft, setDraft] = useState('')

  const changed = () => { client.invalidateQueries({ queryKey: key }); onChanged() }
  const add = useMutation({
    mutationFn: () => api.post(`/api/projects/${projectId}/autotest/variables`,
                               { name: name.trim(), value, is_secret: secret }),
    onSuccess: () => { setName(''); setValue(''); setSecret(false); changed() },
  })
  const update = useMutation({
    mutationFn: ({ id, body }: { id: number; body: Record<string, unknown> }) =>
      api.patch(`/api/autotest/variables/${id}`, body),
    onSuccess: () => { setEditing(null); setDraft(''); changed() },
  })
  const remove = useMutation({
    mutationFn: (id: number) => api.del(`/api/autotest/variables/${id}`),
    onSuccess: changed,
  })
  const problem = (add.error || update.error || remove.error) as Error | null

  return (
    <Dialog open={open} title="Değişkenler" onClose={onClose} width={640}>
      <p className="small muted" style={{ marginTop: 0 }}>
        Senaryoda <code>{'{{AD}}'}</code> olarak kullanılır. Aynı senaryoyu başka bir ortamda
        koşmak için yalnızca değeri değiştirin. <b>Gizli</b> değerler şifreli saklanır, bir daha
        gösterilmez ve koşum kaydında •••• olarak görünür.
      </p>
      {items.length > 0 && (
        <table className="grid" style={{ marginBottom: 14 }}>
          <tbody>
            {items.map((v) => (
              <tr key={v.id} style={{ cursor: 'default' }}>
                <td style={{ width: 170 }}><code>{`{{${v.name}}}`}</code></td>
                <td>
                  {editing === v.id ? (
                    <div className="row" style={{ gap: 6 }}>
                      <input autoFocus type={v.is_secret ? 'password' : 'text'} value={draft}
                             onChange={(e) => setDraft(e.target.value)} style={{ flex: 1 }}
                             placeholder={v.is_secret ? 'Yeni değer' : ''}
                             onKeyDown={(e) => { if (e.key === 'Enter') update.mutate({ id: v.id, body: { value: draft } }) }} />
                      <button className="primary small" onClick={() => update.mutate({ id: v.id, body: { value: draft } })}>Kaydet</button>
                      <button className="ghost small" onClick={() => setEditing(null)}>Vazgeç</button>
                    </div>
                  ) : v.is_secret ? (
                    <span className="faint">
                      {v.readable ? (v.has_value ? '•••••••• (gizli)' : 'boş (gizli)')
                        : <span className="error">okunamıyor, yeniden girin</span>}
                    </span>
                  ) : (
                    <span className="ellipsis" title={v.value ?? ''}>{v.value || <span className="faint">boş</span>}</span>
                  )}
                </td>
                <td style={{ width: 150, textAlign: 'right' }}>
                  {editing !== v.id && (
                    <>
                      <button className="ghost small" title="Değiştir"
                              onClick={() => { setEditing(v.id); setDraft(v.is_secret ? '' : v.value ?? '') }}>
                        <Icon name="edit" size={12} />
                      </button>
                      <button className="ghost danger small" title="Sil"
                              onClick={() => confirm(`{{${v.name}}} silinsin mi? Kullanan senaryolar koşamaz.`) && remove.mutate(v.id)}>
                        <Icon name="trash" size={12} />
                      </button>
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <div className="eyebrow" style={{ marginBottom: 6 }}>Yeni değişken</div>
      <div className="row" style={{ gap: 6, flexWrap: 'wrap' }}>
        <input value={name} onChange={(e) => setName(e.target.value.replace(/\s/g, '_'))}
               placeholder="AD, ör. TEST_SIFRE" style={{ width: 170 }} aria-label="Değişken adı" />
        <input type={secret ? 'password' : 'text'} value={value} onChange={(e) => setValue(e.target.value)}
               placeholder="Değer" style={{ flex: 1, minWidth: 160 }} aria-label="Değer" />
        <label className="small row" style={{ gap: 4 }}>
          <input type="checkbox" checked={secret} onChange={(e) => setSecret(e.target.checked)} /> Gizli
        </label>
        <button className="primary small" disabled={!name.trim() || add.isPending}
                onClick={() => add.mutate()}>
          <Icon name="plus" size={12} /> Ekle
        </button>
      </div>
      {problem && <div className="error small" style={{ marginTop: 8 }}>{problem.message}</div>}
    </Dialog>
  )
}

/**
 * Test automation without code: a scenario in plain Turkish commands, run
 * in a real browser with a screenshot per step. Scenarios can be drafted
 * from a free-text description by the AI; what is saved and run is always
 * the commands, so a run does the same thing every time.
 */
export function Autotest({ route, projectName }: { route: Route; projectName: string }) {
  const projectId = route.project!
  const { data: scenarios = [], isLoading } = useQuery({
    queryKey: ['autotest-scenarios', projectId],
    queryFn: () => api.get<Scenario[]>(`/api/projects/${projectId}/autotest/scenarios`),
    refetchInterval: (q) => (q.state.data?.some((s) => s.last_run && LIVE.has(s.last_run.status)) ? 1500 : false),
  })
  const { data: config } = useQuery({
    queryKey: ['autotest-config'],
    queryFn: () => api.get<Config>('/api/autotest/config'),
    staleTime: 10 * 60 * 1000,
  })
  const [creating, setCreating] = useState(false)
  const [filter, setFilter] = useState('')
  const [showVars, setShowVars] = useState(false)
  const [varsVersion, setVarsVersion] = useState(0)

  const selected = scenarios.find((s) => s.id === route.scenario) ?? null
  const shown = useMemo(() => {
    const q = filter.trim().toLocaleLowerCase('tr')
    return q ? scenarios.filter((s) => s.name.toLocaleLowerCase('tr').includes(q)) : scenarios
  }, [scenarios, filter])

  const open = (id: number | undefined) => {
    setCreating(false)
    location.hash = href({ page: 'autotest', project: projectId, scenario: id })
  }

  return (
    <main className="main">
      <Crumbs projectId={projectId} projectName={projectName} />
      <div className="page-title">
        <h1>Test Otomasyonu</h1>
        <span className="faint small">{scenarios.length} senaryo</span>
        <button className="ghost right" onClick={() => setShowVars(true)}>
          <Icon name="key" size={14} /> Değişkenler
        </button>
        <button className="primary" onClick={() => { open(undefined); setCreating(true) }}>
          <Icon name="plus" size={14} /> Yeni senaryo
        </button>
      </div>

      <VariablesDialog open={showVars} projectId={projectId}
                       onClose={() => setShowVars(false)}
                       onChanged={() => setVarsVersion((v) => v + 1)} />

      <div className="autolayout">
        <nav className="panel autolist" aria-label="Senaryolar">
          {scenarios.length > 6 && (
            <input value={filter} onChange={(e) => setFilter(e.target.value)}
                   placeholder="Senaryo ara" className="autolist-filter" />
          )}
          {isLoading && <div className="skeleton" style={{ margin: 12, width: 160 }} />}
          {!isLoading && scenarios.length === 0 && !creating && (
            <div className="empty" style={{ padding: 24 }}>
              <b>Henüz senaryo yok</b>
              Yeni senaryo ile başlayın.
            </div>
          )}
          {creating && <div className="autolist-item active"><span className="title">Yeni senaryo</span></div>}
          {shown.map((s) => (
            <button key={s.id} className={`autolist-item ${s.id === selected?.id && !creating ? 'active' : ''}`}
                    onClick={() => open(s.id)}>
              <span className="title ellipsis">{s.name}</span>
              {s.last_run
                ? <RunPill run={s.last_run} />
                : <span className="faint small">koşulmadı</span>}
            </button>
          ))}
        </nav>

        <section className="panel autopane">
          {creating || selected ? (
            <Editor key={creating ? 'new' : selected!.id} scenario={creating ? null : selected}
                    config={config} projectId={projectId} varsVersion={varsVersion}
                    onSaved={(s) => { if (creating) open(s.id) }}
                    onDeleted={() => open(undefined)} />
          ) : (
            <div className="empty">
              <Icon name="sparkle" size={36} className="icon" />
              <b>Tarayıcıda koşan senaryolar</b>
              Soldan bir senaryo seçin ya da yeni bir tane yazın. Adımlar
              <code> Git</code>, <code>Tıkla</code>, <code>Yaz</code>, <code>Gör</code> gibi
              Türkçe komutlardır; Test et dediğinizde tarayıcı açılıp adımları uygular.
            </div>
          )}
        </section>
      </div>
    </main>
  )
}
