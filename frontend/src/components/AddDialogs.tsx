import { useState } from 'react'
import {
  useCatalog, useCreateCase, useCreateMilestone, useCreateRun, useCreateSection,
  useMilestones, useSections, useSuites, useUsers,
} from '../api/hooks'
import type { SectionNode } from '../api/types'
import { Dialog } from './Dialog'
import { FieldInput, scopedFields } from './FieldInput'
import { Icon } from './Icon'
import { StepsEditor, type StepDraft } from './StepsEditor'
import { href } from '../route'

function flatten(nodes: SectionNode[], depth = 0,
                 out: { id: number; label: string; count: number }[] = []) {
  for (const n of nodes) {
    out.push({ id: n.id, label: `${' '.repeat(depth * 3)}${n.name}`, count: n.case_count })
    flatten(n.children, depth + 1, out)
  }
  return out
}

export function AddMilestoneDialog({ projectId, open, onClose }: {
  projectId?: number; open: boolean; onClose: () => void
}) {
  const create = useCreateMilestone(projectId)
  const { data: milestones = [] } = useMilestones(projectId)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [parentId, setParentId] = useState<number | ''>('')
  const [dueOn, setDueOn] = useState('')

  const submit = () => create.mutate({
    name,
    description: description || null,
    parent_id: parentId === '' ? null : parentId,
    due_on: dueOn ? new Date(dueOn).toISOString() : null,
  }, { onSuccess: () => { setName(''); setDescription(''); onClose() } })

  return (
    <Dialog open={open} title="Milestone ekle" onClose={onClose}
            footer={<>
              <button onClick={onClose}>Vazgeç</button>
              <button className="primary" onClick={submit}
                      disabled={!name || create.isPending}>
                {create.isPending ? 'Ekleniyor…' : 'Ekle'}
              </button>
            </>}>
      <div className="stack">
        <div className="field">
          <label>Ad</label>
          <input value={name} autoFocus onChange={(e) => setName(e.target.value)} />
        </div>
        <div className="field">
          <label>Açıklama</label>
          <textarea value={description} onChange={(e) => setDescription(e.target.value)} />
        </div>
        <div className="field">
          <label>Üst milestone</label>
          <select value={parentId}
                  onChange={(e) => setParentId(e.target.value === '' ? '' : Number(e.target.value))}>
            <option value="">— yok —</option>
            {milestones.filter((m) => !m.parent_id).map((m) => (
              <option key={m.id} value={m.id}>{m.name}</option>
            ))}
          </select>
        </div>
        <div className="field">
          <label>Bitiş tarihi</label>
          <input type="date" value={dueOn} onChange={(e) => setDueOn(e.target.value)} />
        </div>
        {create.isError && <div className="error">Eklenemedi</div>}
      </div>
    </Dialog>
  )
}

export function AddRunDialog({ projectId, open, onClose, defaultSuiteId }: {
  projectId?: number; open: boolean; onClose: () => void; defaultSuiteId?: number
}) {
  const { data: suites = [] } = useSuites(projectId)
  const { data: milestones = [] } = useMilestones(projectId)
  const { data: users = [] } = useUsers()
  const create = useCreateRun(projectId)

  const [suiteId, setSuiteId] = useState<number | ''>(defaultSuiteId ?? '')
  const [name, setName] = useState('')
  const [milestoneId, setMilestoneId] = useState<number | ''>('')
  const [assignee, setAssignee] = useState<number | ''>('')
  const [includeAll, setIncludeAll] = useState(true)
  const [sectionIds, setSectionIds] = useState<number[]>([])

  const effectiveSuite = suiteId === '' ? (suites[0]?.id ?? undefined) : suiteId
  const { data: sections = [] } = useSections(includeAll ? undefined : effectiveSuite)
  const flat = flatten(sections)
  const selectedCases = flat
    .filter((s) => sectionIds.includes(s.id))
    .reduce((n, s) => n + s.count, 0)
  const suite = suites.find((s) => s.id === effectiveSuite)

  const submit = () => create.mutate({
    suite_id: effectiveSuite,
    name,
    milestone_id: milestoneId === '' ? null : milestoneId,
    assignedto_id: assignee === '' ? null : assignee,
    include_all: includeAll,
    section_ids: includeAll ? [] : sectionIds,
  }, {
    onSuccess: (run) => {
      setName('')
      onClose()
      location.hash = href({ page: 'runs', project: projectId, run: run.id })
    },
  })

  return (
    <Dialog open={open} title="Test koşumu ekle" onClose={onClose} width={620}
            footer={<>
              <button onClick={onClose}>Vazgeç</button>
              <button className="primary" onClick={submit}
                      disabled={!name || !effectiveSuite || create.isPending}>
                {create.isPending ? 'Oluşturuluyor…' : 'Koşumu oluştur'}
              </button>
            </>}>
      <div className="stack">
        <div className="field">
          <label>Ad</label>
          <input value={name} autoFocus onChange={(e) => setName(e.target.value)}
                 placeholder="ör. TRKART Web - Genel Regresyon" />
        </div>
        <div className="field">
          <label>Test suite</label>
          <select value={effectiveSuite ?? ''}
                  onChange={(e) => { setSuiteId(Number(e.target.value)); setSectionIds([]) }}>
            {suites.map((s) => (
              <option key={s.id} value={s.id}>{s.name} ({s.case_count} case)</option>
            ))}
          </select>
        </div>
        <div className="field">
          <label>Milestone</label>
          <select value={milestoneId}
                  onChange={(e) => setMilestoneId(e.target.value === '' ? '' : Number(e.target.value))}>
            <option value="">— yok —</option>
            {milestones.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
          </select>
        </div>
        <div className="field">
          <label>Atanan</label>
          <select value={assignee}
                  onChange={(e) => setAssignee(e.target.value === '' ? '' : Number(e.target.value))}>
            <option value="">— yok —</option>
            {users.filter((u) => u.is_active).map((u) => (
              <option key={u.id} value={u.id}>{u.name}</option>
            ))}
          </select>
        </div>

        <div className="field">
          <label>Kapsam</label>
          <div className="chiprow">
            <button type="button" className={`chip-toggle ${includeAll ? 'on' : ''}`}
                    onClick={() => setIncludeAll(true)}>
              Tüm case’ler{suite ? ` (${suite.case_count})` : ''}
            </button>
            <button type="button" className={`chip-toggle ${!includeAll ? 'on' : ''}`}
                    onClick={() => setIncludeAll(false)}>
              Bölüm seç
            </button>
          </div>
        </div>

        {!includeAll && (
          <div className="field">
            <label>Bölümler — {selectedCases} case seçildi</label>
            <div style={{ maxHeight: 220, overflow: 'auto', border: '1px solid var(--border)',
                          borderRadius: 'var(--radius-sm)', padding: 8 }}>
              {flat.map((s) => (
                <label key={s.id} className="row small"
                       style={{ gap: 8, padding: '3px 2px' }}>
                  <input type="checkbox" style={{ width: 'auto' }}
                         checked={sectionIds.includes(s.id)}
                         onChange={() => setSectionIds(
                           sectionIds.includes(s.id)
                             ? sectionIds.filter((x) => x !== s.id)
                             : [...sectionIds, s.id])} />
                  <span style={{ flex: 1 }}>{s.label}</span>
                  <span className="faint">{s.count}</span>
                </label>
              ))}
              {flat.length === 0 && <span className="faint small">Bölüm yok.</span>}
            </div>
          </div>
        )}
        {create.isError && <div className="error">Koşum oluşturulamadı</div>}
      </div>
    </Dialog>
  )
}

export function AddCaseDialog({ suiteId, sectionId, open, onClose, projectId }: {
  suiteId?: number; sectionId?: number; open: boolean; onClose: () => void
  projectId?: number
}) {
  const { data: sections = [] } = useSections(suiteId)
  const { data: catalog } = useCatalog()
  const { data: users = [] } = useUsers()
  const { data: milestones = [] } = useMilestones(projectId)
  const create = useCreateCase(suiteId)
  const createSection = useCreateSection(suiteId)

  const flat = flatten(sections)
  const [target, setTarget] = useState<number | ''>(sectionId ?? '')
  const [title, setTitle] = useState('')
  const [typeId, setTypeId] = useState<number | ''>('')
  const [priorityId, setPriorityId] = useState<number | ''>('')
  const [templateId, setTemplateId] = useState<number | ''>('')
  const [milestoneId, setMilestoneId] = useState<number | ''>('')
  const [estimate, setEstimate] = useState('')
  const [refs, setRefs] = useState('')
  const [custom, setCustom] = useState<Record<string, unknown>>({})
  const [steps, setSteps] = useState<StepDraft[]>([{ content: '', expected: '' }])
  const [newSection, setNewSection] = useState('')
  const [showAll, setShowAll] = useState(false)

  const effectiveTarget = target === '' ? flat[0]?.id : target

  // Same rule the case page uses: only the fields this project is configured
  // for. The rest belong to other teams and would be noise here.
  const scoped = catalog ? scopedFields(catalog, projectId, 'case') : []
  const shortFields = scoped.filter((f) => f.field_type !== 'text')
  const longFields = scoped.filter((f) => f.field_type === 'text')
  // A create form with 23 fields is a form nobody fills in. The
  // project-specific fields are the ones this team added on purpose, so those
  // open by default and the globals wait behind a toggle.
  const visibleShort = showAll ? shortFields : shortFields.filter((f) => !f.is_global)
  const hiddenCount = shortFields.length - visibleShort.length

  const setField = (name: string, value: unknown) =>
    setCustom((c) => ({ ...c, [name]: value }))

  const submit = () => {
    const payload: Record<string, unknown> = {}
    for (const [key, value] of Object.entries(custom)) {
      if (value !== null && value !== '' &&
          !(Array.isArray(value) && value.length === 0)) {
        payload[key] = value
      }
    }
    create.mutate({
      section_id: effectiveTarget,
      title,
      type_id: typeId === '' ? null : typeId,
      priority_id: priorityId === '' ? null : priorityId,
      template_id: templateId === '' ? null : templateId,
      milestone_id: milestoneId === '' ? null : milestoneId,
      estimate: estimate || null,
      refs: refs || null,
      custom: payload,
      steps: steps.filter((s) => s.content || s.expected),
    }, {
      onSuccess: (created) => {
        setTitle(''); setRefs(''); setEstimate(''); setCustom({})
        setSteps([{ content: '', expected: '' }])
        onClose()
        location.hash = href({ page: 'cases', project: projectId, case: created.id })
      },
    })
  }

  return (
    <Dialog open={open} title="Test case ekle" onClose={onClose} width={760}
            footer={<>
              <button onClick={onClose}>Vazgeç</button>
              <button className="primary" onClick={submit}
                      disabled={!title || !effectiveTarget || create.isPending}>
                {create.isPending ? 'Ekleniyor…' : 'Case ekle'}
              </button>
            </>}>
      <div className="stack">
        <div className="field">
          <label>Başlık</label>
          <input value={title} autoFocus onChange={(e) => setTitle(e.target.value)} />
        </div>

        <div className="field">
          <label>Bölüm</label>
          <select value={effectiveTarget ?? ''}
                  onChange={(e) => setTarget(Number(e.target.value))}>
            {flat.map((s) => (
              <option key={s.id} value={s.id}>{s.label} ({s.count})</option>
            ))}
          </select>
          <div className="row small" style={{ marginTop: 6, gap: 6 }}>
            <input placeholder="yeni bölüm adı" value={newSection}
                   onChange={(e) => setNewSection(e.target.value)} />
            <button type="button" disabled={!newSection || createSection.isPending}
                    onClick={() => createSection.mutate(
                      { suite_id: suiteId, name: newSection },
                      { onSuccess: () => setNewSection('') })}>
              Bölüm ekle
            </button>
          </div>
        </div>

        <div className="fieldgrid editing" style={{ gridTemplateColumns: 'repeat(3, 1fr)' }}>
          <div className="field">
            <label>Tip</label>
            <select value={typeId}
                    onChange={(e) => setTypeId(e.target.value === '' ? '' : Number(e.target.value))}>
              <option value="">—</option>
              {catalog?.case_types.map((t) => (
                <option key={t.id} value={t.id}>{t.name}</option>
              ))}
            </select>
          </div>
          <div className="field">
            <label>Öncelik</label>
            <select value={priorityId}
                    onChange={(e) => setPriorityId(e.target.value === '' ? '' : Number(e.target.value))}>
              <option value="">—</option>
              {catalog?.priorities.map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
          </div>
          <div className="field">
            <label>Şablon</label>
            <select value={templateId}
                    onChange={(e) => setTemplateId(e.target.value === '' ? '' : Number(e.target.value))}>
              <option value="">—</option>
              {catalog?.templates.map((t) => (
                <option key={t.id} value={t.id}>{t.name}</option>
              ))}
            </select>
          </div>
          <div className="field">
            <label>Milestone</label>
            <select value={milestoneId}
                    onChange={(e) => setMilestoneId(e.target.value === '' ? '' : Number(e.target.value))}>
              <option value="">—</option>
              {milestones.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
            </select>
          </div>
          <div className="field">
            <label>Tahmini süre</label>
            <input value={estimate} placeholder="ör. 5m"
                   onChange={(e) => setEstimate(e.target.value)} />
          </div>
          <div className="field">
            <label>Referanslar</label>
            <input value={refs} placeholder="JIRA-123"
                   onChange={(e) => setRefs(e.target.value)} />
          </div>
          {catalog && visibleShort.map((f) => (
            <div className="field" key={f.system_name}>
              <label>{f.label}</label>
              <FieldInput field={f} value={custom[f.system_name]}
                          onChange={(v) => setField(f.system_name, v)}
                          catalog={catalog} users={users} />
            </div>
          ))}
        </div>

        {hiddenCount > 0 && (
          <button type="button" className="ghost small"
                  onClick={() => setShowAll(true)}>
            <Icon name="chevron-down" size={13} /> {hiddenCount} genel alanı daha göster
          </button>
        )}

        {catalog && longFields.map((f) => (
          <div className="field" key={f.system_name}>
            <label>{f.label}</label>
            <FieldInput field={f} value={custom[f.system_name]}
                        onChange={(v) => setField(f.system_name, v)}
                        catalog={catalog} users={users} />
          </div>
        ))}

        <div className="field">
          <label>Adımlar</label>
          <StepsEditor steps={steps} onChange={setSteps} />
        </div>
        {create.isError && (
          <div className="error">Case eklenemedi: {(create.error as Error).message}</div>
        )}
      </div>
    </Dialog>
  )
}
