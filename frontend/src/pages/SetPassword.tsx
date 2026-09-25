import { useEffect, useState } from 'react'
import { ApiError, api, setToken } from '../api/client'
import { Logo } from '../components/Logo'

interface TokenInfo {
  purpose: 'invite' | 'reset'
  email: string
  name: string
  min_length: number
}

/** The token from #/set-password?token=… */
function tokenFromHash() {
  const cut = location.hash.indexOf('?')
  return cut < 0 ? '' : new URLSearchParams(location.hash.slice(cut + 1)).get('token') ?? ''
}

/**
 * Where an invitation or reset link lands.
 *
 * It sits outside the signed-in shell, like the sign-in page, and signs the
 * person in once the password is set: they have just proved who they are.
 */
export function SetPassword({ onDone }: { onDone: () => void }) {
  const [token] = useState(tokenFromHash)
  const [info, setInfo] = useState<TokenInfo | null>(null)
  const [invalid, setInvalid] = useState(false)
  const [password, setPassword] = useState('')
  const [repeat, setRepeat] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!token) { setInvalid(true); return }
    api.get<TokenInfo>(`/api/auth/password-token?token=${encodeURIComponent(token)}`)
      .then(setInfo)
      .catch(() => setInvalid(true))
  }, [token])

  const min = info?.min_length ?? 10
  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    if (password.length < min) { setError(`Parola en az ${min} karakter olmalı.`); return }
    if (password !== repeat) { setError('İki parola aynı değil.'); return }
    setBusy(true)
    setError('')
    try {
      const data = await api.post<{ access_token: string }>(
        '/api/auth/set-password', { token, password })
      setToken(data.access_token)
      onDone()
    } catch (e) {
      // used or expired while the page was open
      if (e instanceof ApiError && e.status === 404) setInvalid(true)
      else setError(`Parola kaydedilemedi: ${(e as Error).message}`)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="signin">
      <header className="signin-top"><Logo size={30} /></header>

      <div className="signin-body single">
        {invalid ? (
          <div className="signin-card">
            <div className="eyebrow">Bağlantı</div>
            <h2>Bu bağlantı geçerli değil</h2>
            <p className="muted" style={{ margin: 0 }}>
              Süresi dolmuş, daha önce kullanılmış ya da yerine yenisi
              gönderilmiş olabilir. Yöneticinizden yeni bir davet isteyin veya
              giriş ekranındaki “Parolamı unuttum” ile yeni bir bağlantı alın.
            </p>
            <a className="button-link" href="#/">Giriş ekranına dön</a>
          </div>
        ) : !info ? (
          <div className="signin-card"><div className="skeleton" style={{ width: 200 }} /></div>
        ) : (
          <form className="signin-card" onSubmit={submit}>
            <div className="eyebrow">{info.purpose === 'invite' ? 'Hoş geldiniz' : 'Parola'}</div>
            <h2>{info.purpose === 'invite' ? `Merhaba ${info.name}` : 'Yeni parolanızı belirleyin'}</h2>
            <p className="muted" style={{ margin: '-6px 0 0' }}>
              {info.email} hesabı için bir parola belirleyin; ardından
              doğrudan giriş yapılır.
            </p>

            <label className="field">
              <span>Parola</span>
              <input type="password" value={password} required autoFocus
                     autoComplete="new-password" minLength={min}
                     onChange={(e) => setPassword(e.target.value)} />
            </label>
            <label className="field">
              <span>Parola (tekrar)</span>
              <input type="password" value={repeat} required
                     autoComplete="new-password"
                     onChange={(e) => setRepeat(e.target.value)} />
            </label>
            <div className="small muted">En az {min} karakter.</div>

            {error && <div className="error">{error}</div>}

            <button className="primary big" type="submit" disabled={busy}>
              {busy ? 'Kaydediliyor…' : 'Parolayı kaydet ve giriş yap'}
            </button>
          </form>
        )}
      </div>

      <footer className="signin-foot"><span>DGPays</span><span>DGTest</span></footer>
    </div>
  )
}
