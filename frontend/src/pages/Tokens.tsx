import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import { Dialog } from '../components/Dialog'
import { Icon } from '../components/Icon'

interface Token {
  id: number
  name: string
  prefix: string
  is_active: boolean
  created_at: string
  last_used_at: string | null
  expires_at: string | null
}

function fmt(v?: string | null) {
  return v ? new Date(v).toLocaleString('tr-TR') : '—'
}

/**
 * API tokens.
 *
 * The RTTS jobs alone wrote 1332 runs into TestRail. Until a CI job can
 * authenticate here without a browser, none of that work can move -- so this
 * screen is part of the migration, not an extra.
 */
export function Tokens() {
  const client = useQueryClient()
  const { data: tokens = [] } = useQuery({
    queryKey: ['tokens'], queryFn: () => api.get<Token[]>('/api/tokens'),
  })
  const create = useMutation({
    mutationFn: (name: string) =>
      api.post<{ token: string; name: string }>('/api/tokens', { name }),
    onSuccess: () => client.invalidateQueries({ queryKey: ['tokens'] }),
  })
  const revoke = useMutation({
    mutationFn: (id: number) => api.del(`/api/tokens/${id}`),
    onSuccess: () => client.invalidateQueries({ queryKey: ['tokens'] }),
  })

  const [adding, setAdding] = useState(false)
  const [name, setName] = useState('')
  const [fresh, setFresh] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)

  const submit = () => create.mutate(name, {
    onSuccess: (data) => { setFresh(data.token); setAdding(false); setName('') },
  })

  return (
    <>
      <div className="toolbar">
        <span className="faint small">{tokens.length} token</span>
        <button className="primary right" onClick={() => setAdding(true)}>
          <Icon name="plus" size={14} /> Token üret
        </button>
      </div>

      <div className="panel">
        {tokens.length === 0 ? (
          <div className="empty">
            <Icon name="key" size={28} />
            <b>Token yok</b>
            CI işlerinizin sonuç yazabilmesi için bir token üretin.
          </div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Ad</th>
                <th style={{ width: 150 }}>Önek</th>
                <th style={{ width: 110 }}>Durum</th>
                <th style={{ width: 180 }}>Son kullanım</th>
                <th style={{ width: 90 }}></th>
              </tr>
            </thead>
            <tbody>
              {tokens.map((t) => (
                <tr key={t.id} style={{ cursor: 'default' }}>
                  <td><b>{t.name}</b>
                    <div className="small faint">oluşturuldu {fmt(t.created_at)}</div>
                  </td>
                  <td className="cid">{t.prefix}…</td>
                  <td>
                    <span className="badge"
                          style={{ background: t.is_active ? 'var(--passed)' : 'var(--blocked)' }}>
                      {t.is_active ? 'Aktif' : 'İptal'}
                    </span>
                  </td>
                  <td className="small muted">{fmt(t.last_used_at)}</td>
                  <td>
                    {t.is_active && (
                      <button className="ghost danger" onClick={() => revoke.mutate(t.id)}>
                        <Icon name="trash" size={13} /> İptal
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="section-rule">Otomasyondan sonuç yazma</div>
      <div className="panel report-card">
        <p className="small muted" style={{ marginTop: 0 }}>
          TestRail’in <code>add_results_for_cases</code> çağrısıyla aynı şekli
          kullanır; mevcut işlerinizde yalnızca adres ve kimlik bilgisi değişir.
        </p>
        <pre style={{
          background: 'var(--surface-2)', padding: '14px 16px',
          borderRadius: 'var(--radius-sm)', overflow: 'auto',
          fontSize: 12.5, lineHeight: 1.6, margin: 0,
        }}>{`curl -X POST http://<sunucu>:8010/api/runs/<run_id>/results \\
  -H "Authorization: Bearer tm_..." \\
  -H "Content-Type: application/json" \\
  -d '{"results":[
        {"case_id": 15477, "status_id": 1, "comment": "ok", "elapsed": "12s"},
        {"case_id": 15478, "status_id": 5, "defects": "JIRA-123"}
      ]}'`}</pre>
      </div>

      <Dialog open={adding} title="API token üret" onClose={() => setAdding(false)}
              footer={<>
                <button onClick={() => setAdding(false)}>Vazgeç</button>
                <button className="primary" onClick={submit}
                        disabled={!name || create.isPending}>
                  {create.isPending ? 'Üretiliyor…' : 'Üret'}
                </button>
              </>}>
        <div className="field">
          <label>Token adı</label>
          <input value={name} autoFocus onChange={(e) => setName(e.target.value)}
                 placeholder="ör. Jenkins RTTS" />
          <div className="small faint" style={{ marginTop: 6 }}>
            Token yalnızca bir kez gösterilir; yazdıktan sonra geri alınamaz.
          </div>
        </div>
      </Dialog>

      <Dialog open={!!fresh} title="Token üretildi" onClose={() => { setFresh(null); setCopied(false) }}
              width={620}
              footer={<button className="primary"
                              onClick={() => { setFresh(null); setCopied(false) }}>
                Kaydettim
              </button>}>
        <div className="stack">
          <div className="error" style={{
            color: 'var(--warn)', background: 'color-mix(in srgb, var(--warn) 8%, transparent)',
            borderColor: 'color-mix(in srgb, var(--warn) 30%, transparent)',
          }}>
            Bu değer bir daha gösterilmeyecek. Şimdi kopyalayın.
          </div>
          <code style={{
            display: 'block', padding: '14px 16px', background: 'var(--surface-2)',
            borderRadius: 'var(--radius-sm)', wordBreak: 'break-all', fontSize: 13,
          }}>{fresh}</code>
          <div>
            <button onClick={() => {
              navigator.clipboard?.writeText(fresh ?? '').then(() => setCopied(true))
            }}>
              {copied ? 'Kopyalandı' : 'Panoya kopyala'}
            </button>
          </div>
        </div>
      </Dialog>
    </>
  )
}
