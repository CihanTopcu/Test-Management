import { useState } from 'react'
import {
  useAdminFields, useAdminSummary, useAdminUsers, useCatalog, useProjects,
  useRoles, useSaveField, useSaveRole, useSaveUser,
} from '../api/hooks'
import { Dialog } from '../components/Dialog'
import { AuditLog } from '../components/AuditLog'
import { SyncStatus } from '../components/SyncStatus'
import { ProjectAdmin } from '../components/ProjectAdmin'
import { GroupAdminTab, UserAccessTable, UserGroups } from '../components/AccessAdmin'
import { Icon } from '../components/Icon'
import { Tokens } from './Tokens'
import type { CustomField, UserAdmin } from '../api/types'
import { inkOn } from '../components/Status'

type Tab = 'ozet' | 'projeler' | 'kullanicilar' | 'gruplar' | 'alanlar' | 'listeler'
  | 'tokenlar' | 'denetim' | 'esitleme'

const FIELD_TYPES = [
  'string', 'integer', 'text', 'url', 'checkbox', 'dropdown', 'user', 'date',
  'multiselect',
]

function UserDialog({ user, onClose, onCreated }: {
  user: UserAdmin | 'new' | null
  onClose: () => void
  /** a new account stays open, so its projects and groups are set in the same go */
  onCreated: (user: UserAdmin) => void
}) {
  const { data: rolesData } = useRoles()
  const roles = rolesData?.roles ?? []
  const save = useSaveUser()
  const isNew = user === 'new'
  const row = isNew ? null : user

  const [name, setName] = useState(row?.name ?? '')
  const [email, setEmail] = useState(row?.email ?? '')
  const [roleId, setRoleId] = useState<number | ''>(row?.role_id ?? '')
  const [active, setActive] = useState(row?.is_active ?? true)
  const [password, setPassword] = useState('')

  const submit = () => {
    const body: Record<string, unknown> = {
      name, email, role_id: roleId === '' ? null : roleId, is_active: active,
    }
    if (password) body.password = password
    save.mutate({ id: row?.id, body }, {
      onSuccess: (saved) => (isNew ? onCreated(saved) : onClose()),
    })
  }

  return (
    <Dialog open={!!user} title={isNew ? 'Kullanıcı ekle' : `Kullanıcı: ${row?.name}`}
            onClose={onClose} width={isNew ? 520 : 1080}
            footer={<>
              <button onClick={onClose}>Vazgeç</button>
              <button className="primary" onClick={submit}
                      disabled={save.isPending || !name || !email}>
                {save.isPending ? 'Kaydediliyor…' : 'Kaydet'}
              </button>
            </>}>
      <div className={isNew ? 'stack' : 'user-dialog'}>
      <div className="stack">
        <div className="field">
          <label>Ad soyad</label>
          <input value={name} onChange={(e) => setName(e.target.value)} autoFocus />
        </div>
        <div className="field">
          <label>E-posta</label>
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
        </div>
        <div className="field">
          <label>Rol</label>
          <select value={roleId} onChange={(e) =>
            setRoleId(e.target.value === '' ? '' : Number(e.target.value))}>
            <option value="">— yok —</option>
            {roles.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
          </select>
        </div>
        <div className="field">
          <label>{isNew ? 'Parola' : 'Yeni parola (boş bırakılırsa değişmez)'}</label>
          <input type="password" value={password}
                 onChange={(e) => setPassword(e.target.value)} />
          {!isNew && row && !row.has_password && (
            <div className="small faint" style={{ marginTop: 4 }}>
              Bu hesabın parolası yok — TestRail parolaları API ile taşınamaz,
              giriş yapabilmesi için burada bir parola tanımlanmalı.
            </div>
          )}
        </div>
        <label className="row small" style={{ gap: 8 }}>
          <input type="checkbox" checked={active} style={{ width: 'auto' }}
                 onChange={(e) => setActive(e.target.checked)} />
          Aktif
        </label>
        {save.isError && <div className="error">{String((save.error as Error).message)}</div>}
        {isNew && (
          <div className="faint small">
            Kaydettikten sonra bu pencerede grupları ve proje yetkilerini
            ayarlayabilirsiniz.
          </div>
        )}
      </div>

      {/* beside the account rather than under it: the access table is the
          reason most people open this dialog */}
      {!isNew && row && (
        <div className="stack">
          <div className="section-rule" style={{ marginTop: 0 }}>Gruplar</div>
          <UserGroups userId={row.id} />
          <div className="section-rule">Projeler ve yetkiler</div>
          <UserAccessTable userId={row.id} />
        </div>
      )}
      </div>
    </Dialog>
  )
}

function FieldDialog({ field, onClose }: {
  field: CustomField | 'new' | null; onClose: () => void
}) {
  const { data: projects = [] } = useProjects()
  const save = useSaveField()
  const isNew = field === 'new'
  const row = isNew ? null : field

  const ctx = row?.configs?.[0]?.context ?? {}
  const [label, setLabel] = useState(row?.label ?? '')
  const [systemName, setSystemName] = useState('')
  const [type, setType] = useState(row?.field_type ?? 'string')
  const [isGlobal, setIsGlobal] = useState(ctx.is_global ?? true)
  const [projectIds, setProjectIds] = useState<number[]>(ctx.project_ids ?? [])
  const [options, setOptions] = useState(
    (row && (row.configs?.[0]?.options as { items?: string })?.items) || '')

  const parsed = options.split('\n').map((line, i) => {
    const [v, ...rest] = line.split(',')
    return { value: Number(v.trim()) || i + 1, label: rest.join(',').trim() }
  }).filter((o) => o.label)

  const submit = () => {
    const body: Record<string, unknown> = {
      label, is_global: isGlobal, project_ids: projectIds,
    }
    if (type === 'dropdown' || type === 'multiselect') body.options = parsed
    if (isNew) {
      body.system_name = systemName || label.toLowerCase().replace(/\W+/g, '_')
      body.field_type = type
      body.entity = 'case'
    }
    save.mutate({ id: row?.id, body }, { onSuccess: onClose })
  }

  return (
    <Dialog open={!!field} width={600}
            title={isNew ? 'Özel alan ekle' : `Alanı düzenle: ${row?.system_name}`}
            onClose={onClose}
            footer={<>
              <button onClick={onClose}>Vazgeç</button>
              <button className="primary" onClick={submit}
                      disabled={save.isPending || !label}>
                {save.isPending ? 'Kaydediliyor…' : 'Kaydet'}
              </button>
            </>}>
      <div className="stack">
        <div className="field">
          <label>Etiket</label>
          <input value={label} onChange={(e) => setLabel(e.target.value)} autoFocus />
        </div>
        {isNew && (
          <>
            <div className="field">
              <label>Sistem adı (boş bırakılırsa etiketten üretilir)</label>
              <input value={systemName} placeholder="custom_..."
                     onChange={(e) => setSystemName(e.target.value)} />
            </div>
            <div className="field">
              <label>Tip</label>
              <select value={type} onChange={(e) => setType(e.target.value)}>
                {FIELD_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
          </>
        )}
        <label className="row small" style={{ gap: 8 }}>
          <input type="checkbox" checked={isGlobal} style={{ width: 'auto' }}
                 onChange={(e) => setIsGlobal(e.target.checked)} />
          Tüm projelerde geçerli
        </label>
        {!isGlobal && (
          <div className="field">
            <label>Projeler</label>
            <div className="chiprow">
              {projects.map((p) => (
                <button key={p.id} type="button"
                        className={`chip-toggle ${projectIds.includes(p.id) ? 'on' : ''}`}
                        onClick={() => setProjectIds(
                          projectIds.includes(p.id)
                            ? projectIds.filter((x) => x !== p.id)
                            : [...projectIds, p.id])}>
                  {p.name}
                </button>
              ))}
            </div>
          </div>
        )}
        {(type === 'dropdown' || type === 'multiselect') && (
          <div className="field">
            <label>Seçenekler — her satır “değer, etiket”</label>
            <textarea value={options} rows={6}
                      onChange={(e) => setOptions(e.target.value)}
                      placeholder={'1, DataCheck\n2, URLCheck'} />
            <div className="small faint">{parsed.length} seçenek okundu</div>
          </div>
        )}
        {save.isError && <div className="error">{String((save.error as Error).message)}</div>}
      </div>
    </Dialog>
  )
}


const CAPABILITY_LABELS: Record<string, string> = {
  read: 'Görüntüleme',
  write_cases: 'Case yazma',
  write_runs: 'Koşum açma',
  write_results: 'Sonuç girme',
  manage_project: 'Proje yönetimi',
  admin: 'Sistem yönetimi',
}

/** Roles arrived from TestRail as names with nothing attached; this is where
 *  the team decides what each one may actually do. */
function RoleTable() {
  const { data } = useRoles()
  const saveRole = useSaveRole()
  const all = data?.capabilities ?? []

  return (
    <div className="panel">
      <table>
        <thead>
          <tr>
            <th style={{ width: 210 }}>Rol</th>
            <th>Yetkiler</th>
          </tr>
        </thead>
        <tbody>
          {(data?.roles ?? []).map((role) => (
            <tr key={role.id} style={{ cursor: 'default' }}>
              <td>
                <b>{role.name}</b>
                <div className="small faint">
                  {role.customised ? 'özelleştirildi' : 'varsayılan'}
                </div>
              </td>
              <td>
                <div className="chiprow">
                  {all.map((cap) => {
                    const on = role.capabilities.includes(cap)
                    return (
                      <button key={cap} type="button"
                              className={`chip-toggle ${on ? 'on' : ''}`}
                              disabled={saveRole.isPending}
                              onClick={() => saveRole.mutate({
                                id: role.id,
                                capabilities: on
                                  ? role.capabilities.filter((c) => c !== cap)
                                  : [...role.capabilities, cap],
                              })}>
                        {CAPABILITY_LABELS[cap] ?? cap}
                      </button>
                    )
                  })}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function Admin() {
  const [tab, setTab] = useState<Tab>('ozet')
  const { data: summary, isError } = useAdminSummary()
  const { data: users = [] } = useAdminUsers()
  const { data: rolesData } = useRoles()
  const roles = rolesData?.roles ?? []
  const { data: fields = [] } = useAdminFields()
  const { data: catalog } = useCatalog()
  const [editUser, setEditUser] = useState<UserAdmin | 'new' | null>(null)
  const [editField, setEditField] = useState<CustomField | 'new' | null>(null)

  if (isError) {
    return (
      <main className="main">
        <div className="panel empty">
          <b>Yetkiniz yok</b>
          Yönetim alanına yalnızca Admin rolündeki kullanıcılar erişebilir.
        </div>
      </main>
    )
  }

  return (
    <main className="main">
      <div className="page-title">
        <h1>Yönetim</h1>
      </div>

      <div className="subtabs">
        {([['ozet', 'Genel'], ['projeler', 'Projeler'],
           ['kullanicilar', 'Kullanıcılar ve Roller'], ['gruplar', 'Gruplar'],
           ['alanlar', 'Özel Alanlar'], ['listeler', 'Listeler'],
           ['tokenlar', 'API Tokenları'],
           ['denetim', 'Denetim Kaydı'],
           ['esitleme', 'TestRail Eşitleme']] as [Tab, string][])
          .map(([key, label]) => (
            <button key={key} className={tab === key ? 'active' : ''}
                    onClick={() => setTab(key)}>{label}</button>
          ))}
      </div>

      {tab === 'ozet' && summary && (
        <div className="cards">
          {[
            { n: summary.users, k: `kullanıcı (${summary.active_users} aktif)` },
            { n: summary.roles, k: 'rol' },
            { n: summary.projects, k: 'proje' },
            { n: summary.case_fields, k: 'case özel alanı' },
            { n: summary.result_fields, k: 'sonuç özel alanı' },
            { n: summary.case_types, k: 'case tipi' },
            { n: summary.priorities, k: 'öncelik' },
            { n: summary.statuses, k: 'statü' },
          ].map((t) => (
            <div className="panel tile lift" key={t.k}>
              <div className="n">{t.n}</div>
              <div className="k">{t.k}</div>
            </div>
          ))}
        </div>
      )}

      {tab === 'projeler' && <ProjectAdmin />}

      {tab === 'gruplar' && <GroupAdminTab />}

      {tab === 'kullanicilar' && (
        <>
          <div className="toolbar">
            <span className="faint small">{users.length} kullanıcı</span>
            <button className="primary right" onClick={() => setEditUser('new')}>
              <Icon name="plus" size={14} /> Kullanıcı ekle
            </button>
          </div>
          <div className="panel">
            <table>
              <thead>
                <tr>
                  <th>Ad</th><th>E-posta</th>
                  <th style={{ width: 150 }}>Rol</th>
                  <th style={{ width: 110 }}>Durum</th>
                  <th style={{ width: 120 }}>Parola</th>
                </tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u.id} onClick={() => setEditUser(u)}>
                    <td><b>{u.name}</b></td>
                    <td className="small muted">{u.email}</td>
                    <td className="small muted">
                      {roles.find((r) => r.id === u.role_id)?.name ?? '—'}
                    </td>
                    <td>
                      <span className="badge"
                            style={{ background: u.is_active ? 'var(--passed)' : 'var(--blocked)',
                                     color: u.is_active ? '#0a0f1e' : undefined }}>
                        {u.is_active ? 'Aktif' : 'Pasif'}
                      </span>
                    </td>
                    <td className="small">
                      {u.has_password
                        ? <span className="muted">tanımlı</span>
                        : <span style={{ color: 'var(--warn)' }}>yok</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="section-rule">Roller ve yetkiler</div>
          <RoleTable />
        </>
      )}

      {tab === 'alanlar' && (
        <>
          <div className="toolbar">
            <span className="faint small">{fields.length} alan</span>
            <button className="primary right" onClick={() => setEditField('new')}>
              <Icon name="plus" size={14} /> Özel alan ekle
            </button>
          </div>
          <div className="panel">
            <table>
              <thead>
                <tr>
                  <th style={{ width: 90 }}>Nesne</th>
                  <th>Etiket</th>
                  <th>Sistem adı</th>
                  <th style={{ width: 120 }}>Tip</th>
                  <th style={{ width: 160 }}>Kapsam</th>
                </tr>
              </thead>
              <tbody>
                {fields.map((f) => {
                  const ctx = f.configs?.[0]?.context ?? {}
                  return (
                    <tr key={f.id} onClick={() => setEditField(f)}>
                      <td className="small muted">{f.entity}</td>
                      <td><b>{f.label}</b></td>
                      <td className="cid">{f.system_name}</td>
                      <td className="small muted">{f.field_type}</td>
                      <td className="small muted">
                        {ctx.is_global ? 'tüm projeler'
                          : `${(ctx.project_ids ?? []).length} proje`}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </>
      )}

      {tab === 'listeler' && catalog && (
        <div className="cards">
          {[
            { title: 'Case tipleri', rows: catalog.case_types.map((t) => t.name) },
            { title: 'Öncelikler', rows: catalog.priorities.map((p) => p.name) },
            { title: 'Şablonlar', rows: catalog.templates.map((t) => t.name) },
          ].map((box) => (
            <div className="panel report-card" key={box.title}>
              <h3>{box.title} ({box.rows.length})</h3>
              <div className="chiprow">
                {box.rows.map((r) => <span className="chip-toggle" key={r}>{r}</span>)}
              </div>
            </div>
          ))}
          <div className="panel report-card">
            <h3>Statüler ({catalog.statuses.length})</h3>
            <div className="chiprow">
              {catalog.statuses.map((s) => (
                <span className="badge" key={s.id}
                      style={{ background: s.color ?? 'var(--untested)',
                               color: inkOn(s.color ?? '') }}>
                  {s.label}
                </span>
              ))}
            </div>
            <div className="small faint" style={{ marginTop: 10 }}>
              Renkler TestRail’den olduğu gibi taşındı.
            </div>
          </div>
        </div>
      )}

      {tab === 'tokenlar' && <Tokens />}

      {tab === 'denetim' && <AuditLog />}

      {tab === 'esitleme' && <SyncStatus />}

      {editUser && (
        <UserDialog key={editUser === 'new' ? 'new' : editUser.id} user={editUser}
                    onClose={() => setEditUser(null)} onCreated={setEditUser} />
      )}
      {editField && <FieldDialog field={editField} onClose={() => setEditField(null)} />}
    </main>
  )
}
