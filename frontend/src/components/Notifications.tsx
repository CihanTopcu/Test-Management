import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import { Icon } from './Icon'

interface Item {
  id: number
  kind: string
  subject: string
  body: string
  link: string | null
  is_read: boolean
  created_at: string
  email_status: string
}

/** Bell in the masthead: unread count plus a dropdown of what happened. */
export function Notifications() {
  const client = useQueryClient()
  const [open, setOpen] = useState(false)
  const box = useRef<HTMLDivElement>(null)

  const { data } = useQuery({
    queryKey: ['notifications'],
    queryFn: () => api.get<{ unread: number; items: Item[] }>('/api/notifications'),
    // a poll is enough here; a socket for a bell icon is not worth the moving
    // parts on an on-prem deployment
    refetchInterval: 60_000,
  })
  const markRead = useMutation({
    mutationFn: (ids?: number[]) => api.post('/api/notifications/read', ids ?? null),
    onSuccess: () => client.invalidateQueries({ queryKey: ['notifications'] }),
  })

  useEffect(() => {
    const away = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', away)
    return () => document.removeEventListener('mousedown', away)
  }, [])

  const unread = data?.unread ?? 0
  const items = data?.items ?? []

  return (
    <div className="omnibox" style={{ width: 'auto' }} ref={box}>
      <button className="ghost icon-only" title="Bildirimler"
              onClick={() => setOpen(!open)} style={{ position: 'relative' }}>
        <Icon name="clock" size={16} />
        {unread > 0 && (
          <span style={{
            position: 'absolute', top: 2, right: 2, minWidth: 16, height: 16,
            borderRadius: 999, background: 'var(--danger)', color: '#fff',
            fontSize: 10, fontWeight: 700, display: 'grid', placeItems: 'center',
            padding: '0 4px',
          }}>{unread > 9 ? '9+' : unread}</span>
        )}
      </button>

      {open && (
        <div className="results" style={{ width: 380, right: 0, left: 'auto' }}>
          <div className="row" style={{ padding: '6px 10px' }}>
            <span className="grp" style={{ padding: 0 }}>Bildirimler</span>
            {unread > 0 && (
              <button className="ghost right small"
                      onClick={() => markRead.mutate(undefined)}>
                Tümünü okundu işaretle
              </button>
            )}
          </div>
          {items.length === 0 && (
            <div className="faint small" style={{ padding: '14px 10px' }}>
              Bildirim yok.
            </div>
          )}
          {items.map((n) => (
            <a key={n.id} href={n.link ?? '#'}
               onClick={() => { markRead.mutate([n.id]); setOpen(false) }}
               style={{ opacity: n.is_read ? 0.6 : 1 }}>
              <div style={{ fontWeight: n.is_read ? 400 : 600 }}>{n.subject}</div>
              <div className="hint">
                {new Date(n.created_at).toLocaleString('tr-TR')}
                {n.email_status === 'sent' && ' · e-posta gönderildi'}
                {n.email_status === 'failed' && ' · e-posta gönderilemedi'}
              </div>
            </a>
          ))}
        </div>
      )}
    </div>
  )
}
