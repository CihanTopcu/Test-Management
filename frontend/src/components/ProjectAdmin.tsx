import { useState } from 'react'
import {
  useAdminGroups, useMembers, useProjectGroups, useProjects, useRemoveMember,
  useRemoveProjectGroup, useRoles, useSaveMember, useSaveProject,
  useSaveProjectGroup, useSetDefaultAccess, useUsers,
} from '../api/hooks'
import type { Project, Role } from '../api/types'
import { Dialog } from './Dialog'
import { Icon } from './Icon'

/**
 * Projects, and who may do what in each.
 *
 * Laid out like TestRail's Access tab, because that is where the people
 * moving over will look: the project's default access first, then the users
 * and the groups that override it. The order the rules apply in is spelled
 * out on the panel itself -- it is the one thing everybody gets wrong.
 */

const SUITE_MODES: [number, string][] = [
  [1, 'Tek suite'],
  [2, 'Tek suite + baseline'],
  [3, 'Çoklu suite'],
]

const isNoAccess = (role?: Role) => role?.name.trim().toLowerCase() === 'no access'

/** What the default-access select says, for the list and the panel alike. */
function defaultLabel(roles: Role[], roleId: number | null) {
  if (roleId == null) return 'Global rol'
  const role = roles.find((r) => r.id === roleId)
  if (!role) return `#${roleId}`
  return isNoAccess(role) ? 'Erişim yok' : role.name
}

function DefaultAccessSelect({ roles, value, onChange, disabled }: {
  roles: Role[]
  value: number | null
  onChange: (roleId: number | null) => void
  disabled?: boolean
}) {
  return (
    <select value={value ?? ''} disabled={disabled}
            onChange={(e) => onChange(e.target.value === '' ? null : Number(e.target.value))}>
      <option value="">Global rol — herkes kendi rolüyle erişir</option>
      {roles.map((r) => (
        <option key={r.id} value={r.id}>
          {isNoAccess(r) ? 'Erişim yok — yalnızca üyeler ve gruplar' : `Herkes: ${r.name}`}
        </option>
      ))}
    </select>
  )
}

function ProjectDialog({ project, onClose }: {
  project: Project | 'new' | null
  onClose: () => void
}) {
  const save = useSaveProject()
  const { data: rolesData } = useRoles()
  const roles = rolesData?.roles ?? []
  const isNew = project === 'new'
  const current = isNew ? null : project
  const [name, setName] = useState(current?.name ?? '')
  const [announcement, setAnnouncement] = useState(current?.announcement ?? '')
  const [suiteMode, setSuiteMode] = useState(current?.suite_mode ?? 3)
  const [completed, setCompleted] = useState(current?.is_completed ?? false)
  const [defaultRole, setDefaultRole] = useState<number | null>(null)

  if (!project) return null

  const submit = () => save.mutate({
    id: current?.id,
    body: {
      name,
      announcement: announcement || null,
      ...(isNew
        ? { suite_mode: suiteMode, default_role_id: defaultRole }
        : { is_completed: completed }),
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
          <>
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
            <div className="field">
              <label>Varsayılan erişim</label>
              <DefaultAccessSelect roles={roles} value={defaultRole} onChange={setDefaultRole} />
              <span className="faint small">
                Gizli bir proje için “Erişim yok” seçin; kişileri ve grupları
                oluşturduktan sonra Erişim panelinden eklersiniz. Siz üye
                olarak eklenirsiniz.
              </span>
            </div>
          </>
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

/** The Access tab: default access, then the users and groups overriding it. */
function ProjectAccess({ project, roles }: { project: Project; roles: Role[] }) {
  const projectId = project.id
  const { data: members = [] } = useMembers(projectId)
  const { data: grants = [] } = useProjectGroups(projectId)
  const { data: users = [] } = useUsers()
  const { data: groups = [] } = useAdminGroups()
  const saveMember = useSaveMember(projectId)
  const removeMember = useRemoveMember(projectId)
  const saveGroup = useSaveProjectGroup(projectId)
  const removeGroup = useRemoveProjectGroup(projectId)
  const setDefault = useSetDefaultAccess(projectId)
  const [pickUser, setPickUser] = useState<number | ''>('')
  const [pickGroup, setPickGroup] = useState<number | ''>('')

  const tester = roles.find((r) => r.name === 'Tester') ?? roles[0]
  const freeUsers = users.filter(
    (u) => u.is_active && !members.some((m) => m.user_id === u.id))
  const freeGroups = groups.filter((g) => !grants.some((x) => x.group_id === g.id))
  const closed = isNoAccess(roles.find((r) => r.id === project.default_role_id))
  const failure = [saveMember, removeMember, saveGroup, removeGroup, setDefault]
    .find((m) => m.isError)?.error as Error | undefined

  const roleSelect = (value: number | null, onChange: (id: number) => void) => (
    <select value={value ?? ''} onChange={(e) => onChange(Number(e.target.value))}>
      {roles.map((r) => (
        <option key={r.id} value={r.id}>{isNoAccess(r) ? 'Erişim yok' : r.name}</option>
      ))}
    </select>
  )

  return (
    <div className="stack">
      <div className="notice">
        Bir kişinin bu projedeki rolü şu sırayla belirlenir: yönetici her yere
        erişir → kişiye verilen rol → üyesi olduğu grupların rolleri (yetkiler
        toplanır) → projenin varsayılan erişimi → kişinin global rolü.
      </div>

      {failure && <div className="error">{failure.message}</div>}

      <div className="panel" style={{ padding: 16 }}>
        <div className="eyebrow" style={{ marginBottom: 10 }}>Varsayılan erişim</div>
        <DefaultAccessSelect roles={roles} value={project.default_role_id}
                             disabled={setDefault.isPending}
                             onChange={(id) => setDefault.mutate(id)} />
        <div className="small muted" style={{ marginTop: 8 }}>
          {project.default_role_id == null
            ? 'Aşağıda listelenmeyen herkes bu projeye kendi global rolüyle erişir.'
            : closed
              ? 'Proje kapalı: yalnızca aşağıdaki kişiler ve gruplar görebilir.'
              : `Aşağıda listelenmeyen herkes bu projede ${defaultLabel(roles, project.default_role_id)} olarak çalışır.`}
        </div>
      </div>

      <div className="panel">
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
              <tr key={m.user_id} style={{ cursor: 'default' }}>
                <td>
                  {m.name}
                  <div className="small faint">{m.email}</div>
                </td>
                <td>
                  {roleSelect(m.role_id, (id) => saveMember.mutate({ user_id: m.user_id, role_id: id }))}
                </td>
                <td>
                  <button className="ghost danger icon-only" title="Projeden çıkar"
                          onClick={() => removeMember.mutate(m.user_id)}>
                    <Icon name="close" size={14} />
                  </button>
                </td>
              </tr>
            ))}
            {!members.length && (
              <tr><td colSpan={3} className="faint small">
                Kişiye özel rol yok.
              </td></tr>
            )}
          </tbody>
        </table>
        <div className="row" style={{ gap: 8, padding: 12, borderTop: '1px solid var(--border)' }}>
          <select value={pickUser} style={{ maxWidth: 320 }}
                  onChange={(e) => setPickUser(e.target.value === '' ? '' : Number(e.target.value))}>
            <option value="">— kullanıcı seçin —</option>
            {freeUsers.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
          </select>
          <button disabled={pickUser === '' || !tester || saveMember.isPending}
                  onClick={() => saveMember.mutate(
                    { user_id: Number(pickUser), role_id: tester.id },
                    { onSuccess: () => setPickUser('') })}>
            <Icon name="plus" size={13} /> Kullanıcı ekle
          </button>
        </div>
      </div>

      <div className="panel">
        <table>
          <thead>
            <tr>
              <th>Grup</th>
              <th style={{ width: 200 }}>Projedeki rol</th>
              <th style={{ width: 44 }} />
            </tr>
          </thead>
          <tbody>
            {grants.map((g) => (
              <tr key={g.group_id} style={{ cursor: 'default' }}>
                <td>
                  {g.name}
                  <div className="small faint">
                    {groups.find((x) => x.id === g.group_id)?.user_ids.length ?? 0} kişi
                  </div>
                </td>
                <td>
                  {roleSelect(g.role_id, (id) => saveGroup.mutate({ group_id: g.group_id, role_id: id }))}
                </td>
                <td>
                  <button className="ghost danger icon-only" title="Grubu çıkar"
                          onClick={() => removeGroup.mutate(g.group_id)}>
                    <Icon name="close" size={14} />
                  </button>
                </td>
              </tr>
            ))}
            {!grants.length && (
              <tr><td colSpan={3} className="faint small">
                Gruba verilmiş rol yok.
              </td></tr>
            )}
          </tbody>
        </table>
        <div className="row" style={{ gap: 8, padding: 12, borderTop: '1px solid var(--border)' }}>
          <select value={pickGroup} style={{ maxWidth: 320 }}
                  onChange={(e) => setPickGroup(e.target.value === '' ? '' : Number(e.target.value))}>
            <option value="">— grup seçin —</option>
            {freeGroups.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
          </select>
          <button disabled={pickGroup === '' || !tester || saveGroup.isPending}
                  onClick={() => saveGroup.mutate(
                    { group_id: Number(pickGroup), role_id: tester.id },
                    { onSuccess: () => setPickGroup('') })}>
            <Icon name="plus" size={13} /> Grup ekle
          </button>
        </div>
      </div>
    </div>
  )
}

export function ProjectAdmin() {
  const { data: projects = [] } = useProjects()
  const { data: rolesData } = useRoles()
  const roles = rolesData?.roles ?? []
  const [editing, setEditing] = useState<Project | 'new' | null>(null)
  const [open, setOpen] = useState<number | null>(null)
  const openProject = projects.find((p) => p.id === open)

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
              <th style={{ width: 118 }}>ID</th>
              <th>Ad</th>
              <th style={{ width: 130 }}>Suite yapısı</th>
              <th style={{ width: 150 }}>Varsayılan erişim</th>
              <th style={{ width: 110 }}>Durum</th>
              <th style={{ width: 180 }} />
            </tr>
          </thead>
          <tbody>
            {projects.map((p) => (
              <tr key={p.id} className={open === p.id ? 'selected' : ''}
                  style={{ cursor: 'default' }}>
                <td className="cid">P{p.id}</td>
                <td className="title">{p.name}</td>
                <td className="small muted">
                  {SUITE_MODES.find(([id]) => id === p.suite_mode)?.[1] ?? p.suite_mode}
                </td>
                <td className="small">
                  {isNoAccess(roles.find((r) => r.id === p.default_role_id))
                    ? <span className="badge soft">Erişim yok</span>
                    : <span className="muted">{defaultLabel(roles, p.default_role_id)}</span>}
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
                      <Icon name="key" size={13} /> Erişim
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {openProject && (
        <>
          <div className="section-rule">{openProject.name} — erişim</div>
          <ProjectAccess key={openProject.id} project={openProject} roles={roles} />
        </>
      )}

      <ProjectDialog project={editing} onClose={() => setEditing(null)} />
    </>
  )
}
