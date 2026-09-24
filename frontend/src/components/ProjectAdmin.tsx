import { useState } from 'react'
import {
  useMembers, useProjects, useRemoveMember, useRoles, useSaveMember,
  useSaveProject, useUsers,
} from '../api/hooks'
import type { Project } from '../api/types'
import { Dialog } from './Dialog'
import { Icon } from './Icon'

/**
 * Projects and who works on them.
 *
 * A project role overrides the global one, which is how somebody leads one
 * product and only reads another -- the same arrangement TestRail called
 * project-level permissions.
 */

const SUITE_MODES: [number, string][] = [
  [1, 'Tek suite'],
  [2, 'Tek suite + baseline'],
  [3, 'Çoklu suite'],
]

function ProjectDialog({ project, onClose }: {
  project: Project | 'new' | null
  onClose: () => void
}) {
  const save = useSaveProject()
  const isNew = project === 'new'
  const current = isNew ? null : project
  const [name, setName] = useState(current?.name ?? '')
  const [announcement, setAnnouncement] = useState(current?.announcement ?? '')
  const [suiteMode, setSuiteMode] = useState(current?.suite_mode ?? 3)
  const [completed, setCompleted] = useState(current?.is_completed ?? false)

  if (!project) return null

  const submit = () => save.mutate({
    id: current?.id,
    body: {
      name,
      announcement: announcement || null,
      ...(isNew ? { suite_mode: suiteMode } : { is_completed: completed }),
    },
  }, { onSuccess: onClose })

  return (
    <Dialog open title={isNew ? 'Proje ekle' : `Proje: ${current?.name}`}
            onClose={onClose} width={560}
            footer={<>
              <button onClick={onClose}>Vazgeç</button>
              <button className="primary" onClick={submit}
                      disabled={!name || save.isPending}>
                {save.isPending ? 'Kaydediliyor…' : 'Kaydet'}
              </button>
            </>}>
      <div className="stack">
        <div className="field">
          <label>Ad</label>
          <input value={name} autoFocus onChange={(e) => setName(e.target.value)} />
        </div>
        <div className="field">
          <label>Duyuru</label>
          <textarea value={announcement}
                    onChange={(e) => setAnnouncement(e.target.value)} />
        </div>
        {isNew ? (
          <div className="field">
            <label>Suite yapısı</label>
            <select value={suiteMode} onChange={(e) => setSuiteMode(Number(e.target.value))}>
              {SUITE_MODES.map(([id, label]) => (
                <option key={id} value={id}>{label}</option>
              ))}
            </select>
            {/* TestRail freezes this after creation and so do we: changing it
                would orphan every suite the project already has */}
            <span className="faint small">Oluşturduktan sonra değiştirilemez.</span>
          </div>
        ) : (
          <label className="row small" style={{ gap: 8 }}>
            <input type="checkbox" style={{ width: 'auto' }} checked={completed}
                   onChange={(e) => setCompleted(e.target.checked)} />
            Proje tamamlandı olarak işaretli
          </label>
        )}
        {save.isError && (
          <div className="error">{(save.error as Error).message}</div>
        )}
      </div>
    </Dialog>
  )
}

function MemberList({ projectId }: { projectId: number }) {
  const { data: members = [] } = useMembers(projectId)
  const { data: users = [] } = useUsers()
  const { data: rolesData } = useRoles()
  const roles = rolesData?.roles ?? []
  const save = useSaveMember(projectId)
  const remove = useRemoveMember(projectId)
  const [pick, setPick] = useState<number | ''>('')

  const free = users.filter(
    (u) => u.is_active && !members.some((m) => m.user_id === u.id))

  return (
    <div className="panel" style={{ padding: 14 }}>
      <table>
        <thead>
          <tr>
            <th>Kullanıcı</th>
            <th style={{ width: 200 }}>Projedeki rol</th>
            <th style={{ width: 44 }} />
          </tr>
        </thead>
        <tbody>
          {members.map((m) => (
            <tr key={m.user_id}>
              <td>
                {m.name}
                <div className="small faint">{m.email}</div>
              </td>
              <td>
                <select value={m.role_id ?? ''} disabled={save.isPending}
                        onChange={(e) => save.mutate({
                          user_id: m.user_id, role_id: Number(e.target.value) })}>
                  {roles.map((r) => (
                    <option key={r.id} value={r.id}>{r.name}</option>
                  ))}
                </select>
              </td>
              <td>
                <button className="ghost danger icon-only" title="Projeden çıkar"
                        onClick={() => remove.mutate(m.user_id)}>
                  <Icon name="trash" size={14} />
                </button>
              </td>
            </tr>
          ))}
          {!members.length && (
            <tr>
              <td colSpan={3} className="faint small">
                Üye yok — herkes global rolüyle erişir.
              </td>
            </tr>
          )}
        </tbody>
      </table>

      <div className="row" style={{ gap: 8, marginTop: 12 }}>
        <select value={pick} style={{ maxWidth: 320 }}
                onChange={(e) => setPick(e.target.value === '' ? '' : Number(e.target.value))}>
          <option value="">— kullanıcı seçin —</option>
          {free.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
        </select>
        <button disabled={pick === '' || !roles.length || save.isPending}
                onClick={() => {
                  const tester = roles.find((r) => r.name === 'Tester') ?? roles[0]
                  save.mutate({ user_id: Number(pick), role_id: tester.id },
                              { onSuccess: () => setPick('') })
                }}>
          <Icon name="plus" size={13} /> Üye ekle
        </button>
      </div>
    </div>
  )
}

export function ProjectAdmin() {
  const { data: projects = [] } = useProjects()
  const [editing, setEditing] = useState<Project | 'new' | null>(null)
  const [open, setOpen] = useState<number | null>(null)

  return (
    <>
      <div className="row" style={{ marginBottom: 10 }}>
        <span className="faint small">{projects.length} proje</span>
        <button className="primary right" onClick={() => setEditing('new')}>
          <Icon name="plus" size={14} /> Proje ekle
        </button>
      </div>

      <div className="panel" style={{ overflow: 'auto' }}>
        <table>
          <thead>
            <tr>
              <th style={{ width: 60 }}>ID</th>
              <th>Ad</th>
              <th style={{ width: 130 }}>Suite yapısı</th>
              <th style={{ width: 110 }}>Durum</th>
              <th style={{ width: 170 }} />
            </tr>
          </thead>
          <tbody>
            {projects.map((p) => (
              <tr key={p.id}>
                <td className="cid">P{p.id}</td>
                <td className="title">{p.name}</td>
                <td className="small muted">
                  {SUITE_MODES.find(([id]) => id === p.suite_mode)?.[1] ?? p.suite_mode}
                </td>
                <td>
                  {p.is_completed
                    ? <span className="badge soft">tamamlandı</span>
                    : <span className="small muted">aktif</span>}
                </td>
                <td>
                  <div className="row" style={{ gap: 6, justifyContent: 'flex-end' }}>
                    <button className="ghost small" onClick={() => setEditing(p)}>
                      <Icon name="edit" size={13} /> Düzenle
                    </button>
                    <button className="ghost small"
                            onClick={() => setOpen(open === p.id ? null : p.id)}>
                      <Icon name="user" size={13} /> Üyeler
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {open != null && (
        <>
          <div className="section-rule">
            {projects.find((p) => p.id === open)?.name} — üyeler
          </div>
          <MemberList projectId={open} />
        </>
      )}

      <ProjectDialog project={editing} onClose={() => setEditing(null)} />
    </>
  )
}
