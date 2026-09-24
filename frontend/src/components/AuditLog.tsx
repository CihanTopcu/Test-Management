import { useState } from 'react'
import { useAdminUsers, useAuditLog } from '../api/hooks'
import { Icon, type IconName } from './Icon'

/**
 * Administrative changes, newest first.
 *
 * Case edits have their own history on the case page. This covers what
 * nothing else recorded: deletions, role capability changes, membership,
 * user accounts -- the things somebody asks about months later.
 */

const ACTION_LABEL: Record<string, string> = {
  create: 'oluşturuldu', update: 'değiştirildi', delete: 'silindi',
}

const ENTITY_LABEL: Record<string, string> = {
  run: 'Koşum', plan: 'Plan', suite: 'Suite', section: 'Bölüm',
  milestone: 'Milestone', result: 'Sonuç', user: 'Kullanıcı', role: 'Rol',
  project_member: 'Proje üyeliği',
}

const ENTITY_ICON: Record<string, IconName> = {
  run: 'play', plan: 'folder', suite: 'grid', section: 'folder',
  milestone: 'flag', result: 'check-circle', user: 'user', role: 'key',
  project_member: 'user',
}

const ACTION_COLOR: Record<string, string> = {
  delete: 'var(--danger)', create: 'var(--ok)', update: 'var(--accent)',
}

function fmt(value: string) {
  return new Date(value).toLocaleString('tr-TR', {
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

/** The one or two facts from `detail` worth putting on the row. */
function summarise(entry: { entity_type: string; detail: Record<string, unknown> }) {
  const d = entry.detail ?? {}
  const parts: string[] = []
  if (typeof d.tests === 'number') parts.push(`${d.tests} test`)
  if (typeof d.runs === 'number') parts.push(`${d.runs} koşum`)
  if (typeof d.cases === 'number') parts.push(`${d.cases} case`)
  if (typeof d.sections === 'number') parts.push(`${d.sections} bölüm`)
  if (Array.isArray(d.before) && Array.isArray(d.after)) {
    const removed = d.before.filter((c) => !(d.after as unknown[]).includes(c))
    const added = (d.after as unknown[]).filter((c) => !(d.before as unknown[]).includes(c))
    if (added.length) parts.push(`+${added.join(', ')}`)
    if (removed.length) parts.push(`−${removed.join(', ')}`)
  }
  if (d.password === 'changed') parts.push('parola değişti')
  if (typeof d.role_id === 'number') parts.push(`rol #${d.role_id}`)
  return parts.join(' · ')
}

export function AuditLog() {
  const { data: users = [] } = useAdminUsers()
  const [action, setAction] = useState('')
  const [entityType, setEntityType] = useState('')
  const [userId, setUserId] = useState<number | ''>('')
  const [days, setDays] = useState(90)
  const [offset, setOffset] = useState(0)

  const { data, isFetching } = useAuditLog({
    action: action || undefined,
    entityType: entityType || undefined,
    userId: userId === '' ? undefined : userId,
    days,
    offset,
  })

  const items = data?.items ?? []
  const total = data?.total ?? 0

  const change = (fn: () => void) => { fn(); setOffset(0) }

  return (
    <>
      <div className="toolbar">
        <select style={{ width: 150 }} value={action}
                onChange={(e) => change(() => setAction(e.target.value))}>
          <option value="">Tüm işlemler</option>
          <option value="create">Oluşturma</option>
          <option value="update">Değişiklik</option>
          <option value="delete">Silme</option>
        </select>
        <select style={{ width: 170 }} value={entityType}
                onChange={(e) => change(() => setEntityType(e.target.value))}>
          <option value="">Tüm nesneler</option>
          {Object.entries(ENTITY_LABEL).map(([key, label]) => (
            <option key={key} value={key}>{label}</option>
          ))}
        </select>
        <select style={{ width: 190 }} value={userId}
                onChange={(e) => change(() => setUserId(
                  e.target.value === '' ? '' : Number(e.target.value)))}>
          <option value="">Tüm kullanıcılar</option>
          {users.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
        </select>
        <select style={{ width: 130 }} value={days}
                onChange={(e) => change(() => setDays(Number(e.target.value)))}>
          <option value={7}>Son 7 gün</option>
          <option value={30}>Son 30 gün</option>
          <option value={90}>Son 90 gün</option>
          <option value={365}>Son 1 yıl</option>
        </select>
        <span className="faint small grow">
          {isFetching ? 'yükleniyor…' : `${total.toLocaleString('tr-TR')} kayıt`}
        </span>
        <button className="ghost" disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - 100))}>
          <Icon name="chevron-left" size={14} /> Önceki
        </button>
        <button className="ghost" disabled={offset + 100 >= total}
                onClick={() => setOffset(offset + 100)}>
          Sonraki <Icon name="chevron-right" size={14} />
        </button>
      </div>

      {items.length === 0 ? (
        <div className="panel empty">
          <b>Kayıt yok</b>
          Seçilen aralıkta denetime takılan bir değişiklik bulunmuyor.
        </div>
      ) : (
        <div className="panel" style={{ overflow: 'auto' }}>
          <table>
            <thead>
              <tr>
                <th style={{ width: 150 }}>Zaman</th>
                <th style={{ width: 170 }}>Kullanıcı</th>
                <th style={{ width: 130 }}>İşlem</th>
                <th>Nesne</th>
                <th style={{ width: 150 }}>Proje</th>
                <th style={{ width: 120 }}>IP</th>
              </tr>
            </thead>
            <tbody>
              {items.map((entry) => {
                const extra = summarise(entry)
                return (
                  <tr key={entry.id} style={{ cursor: 'default' }}>
                    <td className="small muted nowrap">{fmt(entry.created_on)}</td>
                    <td className="small">
                      {entry.user_name ?? <span className="faint">silinmiş kullanıcı</span>}
                    </td>
                    <td className="small nowrap">
                      <span style={{ color: ACTION_COLOR[entry.action] }}>
                        {ACTION_LABEL[entry.action] ?? entry.action}
                      </span>
                    </td>
                    <td>
                      <Icon name={ENTITY_ICON[entry.entity_type] ?? 'file'}
                            size={13} className="faint" />{' '}
                      <b>{ENTITY_LABEL[entry.entity_type] ?? entry.entity_type}</b>
                      {entry.label && <> — {entry.label}</>}
                      {entry.entity_id && (
                        <span className="faint small"> #{entry.entity_id}</span>
                      )}
                      {extra && <div className="small muted">{extra}</div>}
                    </td>
                    <td className="small muted">{entry.project_name ?? '—'}</td>
                    <td className="small faint">{entry.ip ?? '—'}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}
