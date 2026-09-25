import { useState } from 'react'
import {
  useCase, useCaseHistory, useCatalog, useMilestones, useSuites, useUpdateCase,
  useUsers,
} from '../api/hooks'
import { Attachments } from '../components/Attachments'
import {
  FieldInput, FieldValue, isEmptyValue, scopedFields,
} from '../components/FieldInput'
import { Icon } from '../components/Icon'
import { RichText } from '../components/RichText'
import { StepsEditor, type StepDraft } from '../components/StepsEditor'
import type { TestCase } from '../api/types'
import { href, type Route } from '../route'
import { Crumbs } from '../components/Crumbs'
import { IssueRefs, issueKeys } from '../components/IssueRefs'

/**
 * The case page is generated from the field catalog, not hard-coded.
 *
 * This instance carries 23 custom case fields (JmeterId, IsAutomated,
 * RTTS_Bileşen, Sprint, AI Model ...) and an admin can add another without a
 * deploy, exactly as they could in TestRail. Hard-coding the form would mean
 * a code change every time the process changes -- so the editor is built from
 * the same definitions the read-only view renders.
 */

function fmt(value?: string | null) {
  if (!value) return '—'
  return new Date(value).toLocaleString('tr-TR', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit',
  })
}

interface Draft {
  title: string
  type_id: number | ''
  priority_id: number | ''
  template_id: number | ''
  milestone_id: number | ''
  estimate: string
  refs: string
  custom: Record<string, unknown>
  steps: StepDraft[]
}

function toDraft(item: TestCase): Draft {
  return {
    title: item.title,
    type_id: item.type_id ?? '',
    priority_id: item.priority_id ?? '',
    template_id: item.template_id ?? '',
    milestone_id: item.milestone_id ?? '',
    estimate: item.estimate ?? '',
    refs: item.refs ?? '',
    custom: { ...(item.custom as Record<string, unknown>) },
    steps: item.steps.map((s) => ({
      content: s.content ?? '', expected: s.expected ?? '',
    })),
  }
}

export function CaseView({ route, projectName }: { route: Route; projectName: string }) {
  const { data: item, isLoading } = useCase(route.case)
  const { data: catalog } = useCatalog()
  const { data: users = [] } = useUsers()
  const { data: history = [] } = useCaseHistory(route.case)
  const { data: suites = [] } = useSuites(route.project)
  const { data: milestones = [] } = useMilestones(route.project)
  const update = useUpdateCase()

  const [draft, setDraft] = useState<Draft | null>(null)
  const [tab, setTab] = useState<'detay' | 'ekler' | 'gecmis'>('detay')

  if (isLoading || !item || !catalog) {
    return <main className="main">
      <div className="stack">
        <div className="skeleton" style={{ width: '40%' }} />
        <div className="skeleton" style={{ width: '70%' }} />
      </div>
    </main>
  }

  const suite = suites.find((s) => s.id === item.suite_id)
  const type = catalog.case_types.find((t) => t.id === item.type_id)
  const priority = catalog.priorities.find((p) => p.id === item.priority_id)
  const template = catalog.templates.find((t) => t.id === item.template_id)
  const milestone = milestones.find((m) => m.id === item.milestone_id)
  const custom = item.custom as Record<string, unknown>

  // TestRail puts the short fields in a grid at the top and the long text
  // fields in their own sections below; keep that split.
  const scoped = scopedFields(catalog, route.project, 'case')
  const shortFields = scoped.filter((f) => f.field_type !== 'text')
  const longFields = scoped.filter((f) => f.field_type === 'text')
  // Reading: drop the globals this case never filled in, so the handful that
  // carry meaning are not buried under a wall of "None". Editing: show them
  // all, because an empty field is exactly the one somebody wants to fill.
  const shownShort = shortFields.filter(
    (f) => !f.is_global || !isEmptyValue(custom[f.system_name]))
  const shownLong = longFields.filter((f) => !isEmptyValue(custom[f.system_name]))

  const editing = draft !== null
  const patch = (p: Partial<Draft>) => setDraft((d) => (d ? { ...d, ...p } : d))
  const setField = (name: string, value: unknown) =>
    setDraft((d) => (d ? { ...d, custom: { ...d.custom, [name]: value } } : d))

  const save = () => {
    if (!draft) return
    // Only the scoped fields go up: sending the whole `custom` blob back
    // would let a field this project cannot even see be rewritten from here.
    const customPatch: Record<string, unknown> = {}
    for (const f of scoped) {
      const next = draft.custom[f.system_name] ?? null
      const before = custom[f.system_name] ?? null
      if (JSON.stringify(next) !== JSON.stringify(before)) {
        customPatch[f.system_name] = next
      }
    }
    update.mutate({
      id: item.id,
      patch: {
        title: draft.title,
        type_id: draft.type_id === '' ? null : draft.type_id,
        priority_id: draft.priority_id === '' ? null : draft.priority_id,
        template_id: draft.template_id === '' ? null : draft.template_id,
        milestone_id: draft.milestone_id === '' ? null : draft.milestone_id,
        estimate: draft.estimate || null,
        refs: draft.refs || null,
        ...(Object.keys(customPatch).length ? { custom: customPatch } : {}),
        steps: draft.steps.filter((s) => s.content || s.expected),
      },
    }, { onSuccess: () => setDraft(null) })
  }

  return (
    <main className="main">
      <Crumbs projectId={route.project} projectName={projectName} trail={[
        { label: 'Test Suite’leri', href: href({ page: 'suites', project: route.project }) },
        ...(suite ? [{ label: suite.name,
                       href: href({ page: 'suites', project: route.project, suite: suite.id }) }] : []),
      ]} />

      <div className="page-title">
        <span className="idbadge">C{item.id}</span>
        {editing ? (
          <input value={draft.title} onChange={(e) => patch({ title: e.target.value })}
                 autoFocus style={{ maxWidth: 640 }} />
        ) : (
          <h1>{item.title}</h1>
        )}
        {item.is_deleted && (
          <span className="badge" style={{ background: 'var(--danger)' }}>silinmiş</span>
        )}
        <div className="right row" style={{ gap: 6 }}>
          {editing ? (
            <>
              <button className="primary" onClick={save} disabled={update.isPending}>
                {update.isPending ? 'Kaydediliyor…' : 'Kaydet'}
              </button>
              <button onClick={() => setDraft(null)}>Vazgeç</button>
            </>
          ) : (
            <button onClick={() => { setDraft(toDraft(item)); setTab('detay') }}>
              <Icon name="edit" size={14} /> Düzenle
            </button>
          )}
        </div>
      </div>
      {update.isError && (
        <div className="error" style={{ marginBottom: 10 }}>
          Kaydedilemedi: {(update.error as Error).message}
        </div>
      )}

      {!editing && (
        <div className="subtabs">
          <button className={tab === 'detay' ? 'active' : ''} onClick={() => setTab('detay')}>
            Detay
          </button>
          <button className={tab === 'ekler' ? 'active' : ''} onClick={() => setTab('ekler')}>
            Ekler
          </button>
          <button className={tab === 'gecmis' ? 'active' : ''} onClick={() => setTab('gecmis')}>
            Geçmiş ({history.length})
          </button>
        </div>
      )}

      {!editing && tab === 'ekler' && (
        <div className="panel" style={{ padding: 14 }}>
          <Attachments entityType="case" entityId={item.id} projectId={route.project} />
        </div>
      )}

      {!editing && tab === 'gecmis' && (
        <div className="panel" style={{ padding: 14 }}>
          {history.length === 0
            ? <span className="faint small">Bu case için kayıtlı değişiklik yok.</span>
            : <div className="stack">
                {history.map((h) => (
                  <div className="step" key={h.id}>
                    <div className="row small faint">
                      <span>{users.find((u) => u.id === h.user_id)?.name ?? 'bilinmeyen'}</span>
                      <span className="right">{fmt(h.created_on)}</span>
                    </div>
                    {h.changes.map((c, i) => (
                      <div key={i} className="small" style={{ marginTop: 5 }}>
                        <b>{c.field}</b>
                        {c.old_text !== undefined && (
                          <div className="faint" style={{ textDecoration: 'line-through' }}>
                            {String(c.old_text).slice(0, 300)}
                          </div>
                        )}
                        {c.new_text !== undefined && (
                          <div className="muted">{String(c.new_text).slice(0, 300)}</div>
                        )}
                      </div>
                    ))}
                  </div>
                ))}
              </div>}
        </div>
      )}

      {editing && draft && (
        <>
          <div className="section-rule">Alanlar</div>
          <div className="fieldgrid editing">
            <div className="field">
              <label>Type</label>
              <select value={draft.type_id}
                      onChange={(e) => patch({ type_id: e.target.value === '' ? '' : Number(e.target.value) })}>
                <option value="">—</option>
                {catalog.case_types.map((t) => (
                  <option key={t.id} value={t.id}>{t.name}</option>
                ))}
              </select>
            </div>
            <div className="field">
              <label>Priority</label>
              <select value={draft.priority_id}
                      onChange={(e) => patch({ priority_id: e.target.value === '' ? '' : Number(e.target.value) })}>
                <option value="">—</option>
                {catalog.priorities.map((p) => (
                  <option key={p.id} value={p.id}>{p.name}</option>
                ))}
              </select>
            </div>
            <div className="field">
              <label>Template</label>
              <select value={draft.template_id}
                      onChange={(e) => patch({ template_id: e.target.value === '' ? '' : Number(e.target.value) })}>
                <option value="">—</option>
                {catalog.templates.map((t) => (
                  <option key={t.id} value={t.id}>{t.name}</option>
                ))}
              </select>
            </div>
            <div className="field">
              <label>Milestone</label>
              <select value={draft.milestone_id}
                      onChange={(e) => patch({ milestone_id: e.target.value === '' ? '' : Number(e.target.value) })}>
                <option value="">—</option>
                {milestones.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
              </select>
            </div>
            <div className="field">
              <label>Estimate</label>
              <input value={draft.estimate} placeholder="ör. 30s, 5m"
                     onChange={(e) => patch({ estimate: e.target.value })} />
            </div>
            <div className="field">
              <label>References</label>
              <input value={draft.refs} placeholder="JIRA-123"
                     onChange={(e) => patch({ refs: e.target.value })} />
            </div>
            {shortFields.map((f) => (
              <div className="field" key={f.system_name}>
                <label>{f.label}</label>
                <FieldInput field={f} value={draft.custom[f.system_name]}
                            onChange={(v) => setField(f.system_name, v)}
                            catalog={catalog} users={users} />
              </div>
            ))}
          </div>

          {longFields.map((f) => (
            <div className="field" key={f.system_name} style={{ marginTop: 12 }}>
              <div className="section-rule">{f.label}</div>
              <FieldInput field={f} value={draft.custom[f.system_name]}
                          onChange={(v) => setField(f.system_name, v)}
                          catalog={catalog} users={users} />
            </div>
          ))}

          {/* labelled in Turkish on purpose: several templates also carry a
              free-text custom field called "Steps", and the two sit next to
              each other here even though TestRail never shows both */}
          <div className="section-rule">Adımlar</div>
          <StepsEditor steps={draft.steps} onChange={(steps) => patch({ steps })} />

          <div className="section-rule">Ekler</div>
          <Attachments entityType="case" entityId={item.id} projectId={route.project} />
        </>
      )}

      {!editing && tab === 'detay' && (
        <>
          <div className="fieldgrid">
            <div><div className="k">Tip</div><div className="v">{type?.name ?? <span className="faint">—</span>}</div></div>
            <div><div className="k">Öncelik</div><div className="v">{priority?.name ?? <span className="faint">—</span>}</div></div>
            <div><div className="k">Şablon</div><div className="v">{template?.name ?? <span className="faint">—</span>}</div></div>
            <div><div className="k">Tahmini süre</div><div className="v">{item.estimate ?? <span className="faint">—</span>}</div></div>
            <div>
              <div className="k">Milestone</div>
              <div className="v">{milestone?.name ?? <span className="faint">—</span>}</div>
            </div>
            <div>
              <div className="k">Referanslar</div>
              <div className="v">
                {item.refs
                  // a plain link, unless it is a Jira address: that one
                  // gets the key and its status like any other reference
                  ? (/^https?:\/\//.test(item.refs) && !issueKeys(item.refs).length
                      ? <a href={item.refs} target="_blank" rel="noreferrer">{item.refs}</a>
                      : <IssueRefs text={item.refs} />)
                  : <span className="faint">—</span>}
              </div>
            </div>
            {shownShort.map((f) => (
              <div key={f.system_name}>
                <div className="k">{f.label}</div>
                <div className="v">
                  <FieldValue field={f} value={custom[f.system_name]}
                              catalog={catalog} users={users} />
                </div>
              </div>
            ))}
          </div>

          {shownLong.map((f) => (
            <div key={f.system_name}>
              <div className="section-rule">{f.label}</div>
              <div className="panel" style={{ padding: '10px 13px' }}>
                <RichText value={String(custom[f.system_name])} />
              </div>
            </div>
          ))}

          {item.steps.length > 0 && (
            <>
              <div className="section-rule">Steps</div>
              {item.steps.map((step) => (
                <div className="steprow" key={step.idx}>
                  <div className="num">{step.idx + 1}</div>
                  <div className="box">
                    <div className="cap">STEP DESCRIPTION</div>
                    <RichText value={step.content ?? ''} />
                  </div>
                  <div className="box">
                    <div className="cap">EXPECTED RESULT</div>
                    <RichText value={step.expected ?? ''} />
                  </div>
                </div>
              ))}
            </>
          )}

          <div className="section-rule">People &amp; Dates</div>
          <div className="fieldgrid">
            <div>
              <div className="k">Created</div>
              <div className="v">
                {users.find((u) => u.id === item.created_by)?.name ?? '—'}
                <div className="small faint">{fmt(item.created_on)}</div>
              </div>
            </div>
            <div>
              <div className="k">Updated</div>
              <div className="v">
                {users.find((u) => u.id === item.updated_by)?.name ?? '—'}
                <div className="small faint">{fmt(item.updated_on)}</div>
              </div>
            </div>
          </div>
        </>
      )}
    </main>
  )
}
