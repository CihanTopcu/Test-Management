import { useState } from 'react'
import {
  useDeleteSubscription, useNotificationPreferences, usePreviewSubscription,
  useProjects, useSavePreference, useSaveSubscription, useSubscriptions,
} from '../api/hooks'
import { Confirm } from '../components/Confirm'
import { Dialog } from '../components/Dialog'
import { Icon } from '../components/Icon'
import type { DigestPreview } from '../api/types'

/**
 * Personal settings: which events reach you, and which digests arrive.
 *
 * The notification preferences endpoint had no screen at all -- the defaults
 * were the only setting anyone could have. Digests sit next to them because
 * they are the same question asked over a longer period.
 */

const DAYS = ['Pazartesi', 'Salı', 'Çarşamba', 'Perşembe', 'Cuma',
              'Cumartesi', 'Pazar']

function fmt(value: string | null) {
  if (!value) return 'henüz gönderilmedi'
  return new Date(value).toLocaleString('tr-TR', {
    day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit',
  })
}

export function Settings() {
  const { data: preferences = [] } = useNotificationPreferences()
  const { data: subscriptions } = useSubscriptions()
  const { data: projects = [] } = useProjects()
  const savePreference = useSavePreference()
  const saveSubscription = useSaveSubscription()
  const removeSubscription = useDeleteSubscription()
  const preview = usePreviewSubscription()

  const [adding, setAdding] = useState(false)
  const [dropping, setDropping] = useState<number | null>(null)
  const [shown, setShown] = useState<DigestPreview | null>(null)

  const [kind, setKind] = useState('failures')
  const [projectId, setProjectId] = useState<number | ''>('')
  const [frequency, setFrequency] = useState('daily')
  const [hour, setHour] = useState(8)
  const [weekday, setWeekday] = useState(0)
  const [byEmail, setByEmail] = useState(true)

  const items = subscriptions?.items ?? []
  const kinds = subscriptions?.kinds ?? []

  return (
    <main className="main">
      <div className="page-title">
        <h1>Bildirimler ve Raporlar</h1>
      </div>

      <div className="section-rule">Olay bildirimleri</div>
      <div className="panel" style={{ overflow: 'auto' }}>
        <table>
          <thead>
            <tr>
              <th>Olay</th>
              <th style={{ width: 130 }}>Uygulama içi</th>
              <th style={{ width: 130 }}>E-posta</th>
            </tr>
          </thead>
          <tbody>
            {preferences.map((p) => (
              <tr key={p.kind} style={{ cursor: 'default' }}>
                <td>{p.label}</td>
                <td>
                  <input type="checkbox" checked={p.in_app}
                         onChange={(e) => savePreference.mutate({
                           kind: p.kind, in_app: e.target.checked,
                           email: p.email })} />
                </td>
                <td>
                  <input type="checkbox" checked={p.email}
                         onChange={(e) => savePreference.mutate({
                           kind: p.kind, in_app: p.in_app,
                           email: e.target.checked })} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="section-rule">
        Zamanlanmış raporlar
        <button className="primary small" onClick={() => setAdding(true)}>
          <Icon name="plus" size={13} /> Rapor ekle
        </button>
      </div>

      {items.length === 0 ? (
        <div className="panel empty">
          <b>Abonelik yok</b>
          Gece kırılan testleri ya da yaklaşan milestone’ları sabah e-postayla
          almak için bir rapor ekleyin.
        </div>
      ) : (
        <div className="panel" style={{ overflow: 'auto' }}>
          <table>
            <thead>
              <tr>
                <th>Rapor</th>
                <th style={{ width: 170 }}>Proje</th>
                <th style={{ width: 160 }}>Sıklık</th>
                <th style={{ width: 90 }}>E-posta</th>
                <th style={{ width: 160 }}>Son gönderim</th>
                <th style={{ width: 150 }} />
              </tr>
            </thead>
            <tbody>
              {items.map((s) => (
                <tr key={s.id} style={{ cursor: 'default' }}>
                  <td className="title">
                    {s.kind_label}
                    {!s.is_active && (
                      <span className="badge soft" style={{ marginLeft: 6 }}>
                        kapalı
                      </span>
                    )}
                  </td>
                  <td className="small muted">{s.project_name}</td>
                  <td className="small">
                    {s.frequency === 'daily'
                      ? `Her gün ${String(s.hour).padStart(2, '0')}:00`
                      : `${DAYS[s.weekday]} ${String(s.hour).padStart(2, '0')}:00`}
                  </td>
                  <td>{s.by_email ? 'evet' : 'hayır'}</td>
                  <td className="small muted">{fmt(s.last_sent_on)}</td>
                  <td>
                    <div className="row" style={{ gap: 6, justifyContent: 'flex-end' }}>
                      <button className="ghost small" disabled={preview.isPending}
                              onClick={() => preview.mutate(s.id, {
                                onSuccess: (data) => setShown(data) })}>
                        Önizle
                      </button>
                      <button className="ghost small danger"
                              onClick={() => setDropping(s.id)}>
                        <Icon name="trash" size={13} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="faint small" style={{ marginTop: 10 }}>
        İçinde bildirilecek bir şey olmayan rapor gönderilmez.
      </div>

      <Dialog open={adding} title="Zamanlanmış rapor" width={520}
              onClose={() => setAdding(false)}
              footer={<>
                <button onClick={() => setAdding(false)}>Vazgeç</button>
                <button className="primary" disabled={saveSubscription.isPending}
                        onClick={() => saveSubscription.mutate({
                          kind, frequency, hour, weekday, by_email: byEmail,
                          project_id: projectId === '' ? null : projectId,
                          is_active: true,
                        }, { onSuccess: () => setAdding(false) })}>
                  Kaydet
                </button>
              </>}>
        <div className="stack">
          <div className="field">
            <label>Rapor</label>
            <select value={kind} onChange={(e) => setKind(e.target.value)}>
              {kinds.map((k) => (
                <option key={k.key} value={k.key}>{k.label}</option>
              ))}
            </select>
          </div>
          <div className="field">
            <label>Proje</label>
            <select value={projectId}
                    onChange={(e) => setProjectId(
                      e.target.value === '' ? '' : Number(e.target.value))}>
              <option value="">Tüm projeler</option>
              {projects.map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
          </div>
          <div className="row" style={{ gap: 10 }}>
            <div className="field" style={{ flex: 1 }}>
              <label>Sıklık</label>
              <select value={frequency}
                      onChange={(e) => setFrequency(e.target.value)}>
                <option value="daily">Her gün</option>
                <option value="weekly">Haftada bir</option>
              </select>
            </div>
            {frequency === 'weekly' && (
              <div className="field" style={{ flex: 1 }}>
                <label>Gün</label>
                <select value={weekday}
                        onChange={(e) => setWeekday(Number(e.target.value))}>
                  {DAYS.map((d, i) => <option key={d} value={i}>{d}</option>)}
                </select>
              </div>
            )}
            <div className="field" style={{ width: 110 }}>
              <label>Saat</label>
              <select value={hour} onChange={(e) => setHour(Number(e.target.value))}>
                {Array.from({ length: 24 }, (_, h) => (
                  <option key={h} value={h}>{String(h).padStart(2, '0')}:00</option>
                ))}
              </select>
            </div>
          </div>
          <label className="row small" style={{ gap: 8 }}>
            <input type="checkbox" style={{ width: 'auto' }} checked={byEmail}
                   onChange={(e) => setByEmail(e.target.checked)} />
            E-posta olarak da gönder
          </label>
          {saveSubscription.isError && (
            <div className="error">{(saveSubscription.error as Error).message}</div>
          )}
        </div>
      </Dialog>

      <Dialog open={shown !== null} title="Rapor önizlemesi" width={640}
              onClose={() => setShown(null)}
              footer={<button onClick={() => setShown(null)}>Kapat</button>}>
        {shown?.empty ? (
          <div className="panel empty">
            <b>Şu an boş</b>
            {shown.detail}
          </div>
        ) : (
          <>
            <div className="field">
              <label>Konu</label>
              <b>{shown?.subject}</b>
            </div>
            <pre style={{
              whiteSpace: 'pre-wrap', fontSize: 13, margin: 0,
              background: 'var(--surface-2)', padding: 12,
              borderRadius: 'var(--radius-sm)', maxHeight: 420, overflow: 'auto',
            }}>{shown?.body}</pre>
          </>
        )}
      </Dialog>

      <Confirm open={dropping !== null} title="Aboneliği sil"
               busy={removeSubscription.isPending}
               detail="Bu rapor artık gönderilmeyecek."
               onClose={() => setDropping(null)}
               onConfirm={() => dropping !== null && removeSubscription.mutate(
                 dropping, { onSuccess: () => setDropping(null) })} />
    </main>
  )
}
