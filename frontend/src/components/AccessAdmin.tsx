import { useState } from 'react'
import {
  useAdminGroups, useAdminUsers, useDeleteGroup, useProjects, useRemoveMember,
  useRoles, useSaveGroup, useSaveMember, useUserAccess,
} from '../api/hooks'
import type { GroupAdmin, Role, UserAccessRow } from '../api/types'
import { Confirm } from './Confirm'
import { Dialog } from './Dialog'
import { Icon } from './Icon'

/**
 * "What can this person do, and where?" -- and the groups that answer it
 * for many people at once.
 *
 * Until this existed, memberships could only be read one project at a time,
 * and nothing showed what a global role, a group and a project's default
 * access added up to. The table reads the server's own resolution, so it
 * shows what is enforced rather than a second opinion about it.
 */

const SOURCE_TONE: Record<string, string> = {
  admin: 'var(--accent)', member: 'var(--eyebrow)', group: 'var(--retest)',
  default: 'var(--text-dim)', global: 'var(--text-faint)',
}

const roleName = (r: Role) => (r.name.trim().toLowerCase() === 'no access' ? 'Erişim yok' : r.name)

/** One project row; its own component so each can hold its own mutations. */
function AccessRow({ userId, row, roles }: {
  userId: number
  row: UserAccessRow
  roles: Role[]
}) {
  const save = useSaveMember(row.project_id)
  const remove = useRemoveMember(row.project_id)
  const busy = save.isPending || remove.isPending

  return (
    <tr style={{ cursor: 'default' }} className={row.can_read ? '' : 'muted-row'}>
      <td className="title">
        {row.name}
        {row.is_completed && <span className="faint small"> · kapalı</span>}
      </td>
      <td>
        {row.can_read
          ? <b>{row.roles.join(' + ') || '—'}</b>
          : <span className="faint">erişemez</span>}
      </td>
      <td className="small">
        <span style={{ color: SOURCE_TONE[row.source] }}>{row.source_label}</span>
        {row.groups.length > 0 && row.source !== 'group' && (
          <div className="faint">grup: {row.groups.join(', ')}</div>
        )}
        {row.source === 'group' && (
          <div className="faint">{row.groups.join(', ')}</div>
        )}
      </td>
      <td>
        {row.source === 'admin' ? (
          <span className="faint small">yönetici her yere erişir</span>
        ) : (
          <select value={row.member_role_id ?? ''} disabled={busy}
                  onChange={(e) => {
                    if (e.target.value === '') remove.mutate(userId)
                    else save.mutate({ user_id: userId, role_id: Number(e.target.value) })
                  }}>
            <option value="">— kişiye özel rol yok —</option>
            {roles.map((r) => <option key={r.id} value={r.id}>{roleName(r)}</option>)}
          </select>
        )}
      </td>
    </tr>
  )
}

export function UserAccessTable({ userId }: { userId: number }) {
  const { data, isLoading } = useUserAccess(userId)
  const { data: rolesData } = useRoles()
  const roles = rolesData?.roles ?? []

  if (isLoading || !data) return <div className="skeleton" style={{ width: 240 }} />
  const readable = data.projects.filter((p) => p.can_read).length

  return (
    <div className="stack">
      <div className="small muted">
        {readable} / {data.projects.length} projeye erişebilir. Rol, önce kişiye
        özel rolden, sonra gruplardan, sonra projenin varsayılan erişiminden,
        en son global rolden gelir.
      </div>
      <div className="panel" style={{ maxHeight: '52vh', overflow: 'auto' }}>
        <table className="grid">
          <thead>
            <tr>
              <th>Proje</th>
              <th style={{ width: 150 }}>Etkin rol</th>
              <th style={{ width: 170 }}>Nereden</th>
              <th style={{ width: 210 }}>Kişiye özel rol</th>
            </tr>
          </thead>
          <tbody>
            {data.projects.map((row) => (
              <AccessRow key={row.project_id} userId={userId} row={row} roles={roles} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

/** Group membership from the person's side: tick the groups they are in. */
export function UserGroups({ userId }: { userId: number }) {
  const { data: groups = [] } = useAdminGroups()
  const save = useSaveGroup()

  if (!groups.length) {
    return <div className="faint small">Henüz grup yok; Gruplar sekmesinden oluşturabilirsiniz.</div>
  }
  return (
    <div className="chiprow">
      {groups.map((g) => {
        const on = g.user_ids.includes(userId)
        return (
          <button key={g.id} className={`chip-toggle ${on ? 'on' : ''}`}
                  disabled={save.isPending}
                  onClick={() => save.mutate({ id: g.id, body: {
                    user_ids: on ? g.user_ids.filter((u) => u !== userId)
                                 : [...g.user_ids, userId],
                  } })}>
            {on && <Icon name="check-circle" size={12} />} {g.name}
          </button>
        )
      })}
    </div>
  )
}

function GroupDialog({ group, onClose }: {
  group: GroupAdmin | 'new' | null
  onClose: () => void
}) {
  const { data: users = [] } = useAdminUsers()
  const save = useSaveGroup()
  const isNew = group === 'new'
  const row = isNew ? null : group
  const [name, setName] = useState(row?.name ?? '')
  const [members, setMembers] = useState<Set<number>>(new Set(row?.user_ids ?? []))
  const [filter, setFilter] = useState('')

  if (!group) return null
  const shown = users.filter((u) =>
    !filter || `${u.name} ${u.email}`.toLowerCase().includes(filter.toLowerCase()))

  return (
    <Dialog open title={isNew ? 'Grup ekle' : `Grup: ${row?.name}`} width={560}
            onClose={onClose}
            footer={<>
              <button onClick={onClose}>Vazgeç</button>
              <button className="primary" disabled={!name.trim() || save.isPending}
                      onClick={() => save.mutate(
                        { id: row?.id, body: { name, user_ids: [...members] } },
                        { onSuccess: onClose })}>
                {save.isPending ? 'Kaydediliyor…' : 'Kaydet'}
              </button>
            </>}>
      <div className="stack">
        <div className="field">
          <label>Ad</label>
          <input value={name} autoFocus onChange={(e) => setName(e.target.value)} />
        </div>
        <div className="field">
          <label>Üyeler ({members.size})</label>
          <input placeholder="Ada veya e-postaya göre süz…" value={filter}
                 onChange={(e) => setFilter(e.target.value)} />
        </div>
        <div className="panel" style={{ maxHeight: 260, overflow: 'auto' }}>
          <table>
            <tbody>
              {shown.map((u) => (
                <tr key={u.id} onClick={() => {
                  const next = new Set(members)
                  if (next.has(u.id)) next.delete(u.id)
                  else next.add(u.id)
                  setMembers(next)
                }}>
                  <td style={{ width: 32 }}>
                    <input type="checkbox" readOnly checked={members.has(u.id)} />
                  </td>
                  <td>
                    {u.name}
                    {!u.is_active && <span className="faint small"> · pasif</span>}
                    <div className="small faint">{u.email}</div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {save.isError && <div className="error">{(save.error as Error).message}</div>}
      </div>
    </Dialog>
  )
}

export function GroupAdminTab() {
  const { data: groups = [] } = useAdminGroups()
  const { data: projects = [] } = useProjects()
  const { data: rolesData } = useRoles()
  const roles = rolesData?.roles ?? []
  const remove = useDeleteGroup()
  const [editing, setEditing] = useState<GroupAdmin | 'new' | null>(null)
  const [deleting, setDeleting] = useState<GroupAdmin | null>(null)

  return (
    <>
      <div className="toolbar">
        <span className="faint small">
          {groups.length} grup · bir gruba bir projede rol verildiğinde, grubun
          bütün üyeleri o rolü alır
        </span>
        <button className="primary right" onClick={() => setEditing('new')}>
          <Icon name="plus" size={14} /> Grup ekle
        </button>
      </div>

      <div className="panel">
        <table>
          <thead>
            <tr>
              <th>Grup</th>
              <th style={{ width: 90 }}>Üye</th>
              <th>Projelerdeki rolü</th>
              <th style={{ width: 44 }} />
            </tr>
          </thead>
          <tbody>
            {groups.map((g) => (
              <tr key={g.id} onClick={() => setEditing(g)}>
                <td><b>{g.name}</b></td>
                <td className="small muted">{g.user_ids.length}</td>
                <td className="small">
                  {g.projects.length === 0
                    ? <span className="faint">hiçbir projede rolü yok</span>
                    : g.projects.map((p) => (
                      <span key={p.project_id} className="chip-toggle" style={{ marginRight: 6 }}>
                        {projects.find((x) => x.id === p.project_id)?.name ?? `P${p.project_id}`}
                        {' · '}
                        {roles.find((r) => r.id === p.role_id)?.name ?? p.role_id}
                      </span>
                    ))}
                </td>
                <td onClick={(e) => e.stopPropagation()}>
                  <button className="ghost danger icon-only" title="Grubu sil"
                          onClick={() => setDeleting(g)}>
                    <Icon name="trash" size={14} />
                  </button>
                </td>
              </tr>
            ))}
            {!groups.length && (
              <tr><td colSpan={4} className="faint small">Grup yok.</td></tr>
            )}
          </tbody>
        </table>
      </div>
      <div className="faint small" style={{ marginTop: 10 }}>
        Grubun hangi projede hangi rolü alacağı, Projeler sekmesinde projenin
        Erişim panelinden verilir.
      </div>

      {editing && <GroupDialog group={editing} onClose={() => setEditing(null)} />}
      <Confirm open={!!deleting} title="Grubu sil" busy={remove.isPending}
               error={remove.isError ? (remove.error as Error).message : null}
               detail={deleting
                 ? `"${deleting.name}" grubu silinecek. ${deleting.user_ids.length} üyesi`
                   + (deleting.projects.length
                     ? ` ${deleting.projects.length} projede bu grup üzerinden aldıkları rolü kaybeder.`
                     : ' etkilenmez; grubun hiçbir projede rolü yok.')
                 : ''}
               onClose={() => setDeleting(null)}
               onConfirm={() => deleting && remove.mutate(deleting.id, {
                 onSuccess: () => setDeleting(null) })} />
    </>
  )
}
