import { useState } from 'react'
import { api } from '../api/client'
import { Logo } from '../components/Logo'

const VERSION = 'v0.1.0'

export function Login({ onDone }: { onDone: () => void }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [remember, setRemember] = useState(true)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      await api.login(email, password)
      onDone()
    } catch {
      setError('E-posta veya parola hatalı')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="signin">
      <div className="signin-inner">
        <div className="wordmark">
          <Logo size={26} subtitle={false} />
        </div>

        <form className="signin-card" onSubmit={submit}>
          {/* the name is already on the wordmark above; repeating it here
              wastes the line that should say what to do next */}
          <h1>Hesabınıza giriş yapın</h1>
          <h2>DGPays test yönetim sistemi</h2>

          <label className="float">
            <input type="email" value={email} required autoFocus
                   placeholder=" " autoComplete="username"
                   onChange={(e) => setEmail(e.target.value)} />
            <span>E-posta</span>
          </label>

          <label className="float">
            <input type="password" value={password} required
                   placeholder=" " autoComplete="current-password"
                   onChange={(e) => setPassword(e.target.value)} />
            <span>Parola</span>
          </label>

          <div className="row small" style={{ justifyContent: 'flex-end', marginTop: -6 }}>
            <a href="#" onClick={(e) => {
              e.preventDefault()
              setError('Parolanızı sıfırlamak için sistem yöneticinize başvurun.')
            }}>Parolanızı mı unuttunuz?</a>
          </div>

          <label className="check">
            <input type="checkbox" checked={remember}
                   onChange={(e) => setRemember(e.target.checked)} />
            Oturumum açık kalsın
          </label>

          {error && <div className="error">{error}</div>}

          <button className="primary big" type="submit" disabled={busy}>
            {busy ? 'Giriş yapılıyor…' : 'Giriş yap'}
          </button>
        </form>

        <div className="version">{VERSION}</div>
      </div>
    </div>
  )
}
