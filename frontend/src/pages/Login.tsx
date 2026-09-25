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
      <header className="signin-top">
        <Logo size={30} />
      </header>

      <div className="signin-body">
        {/* the site's hero, cut down to what someone signing in needs to
            know: where they are, and what lives here */}
        <section className="signin-hero">
          <div className="eyebrow">DGPays · Yazılım Test Yönetimi</div>
          <h1>
            <span className="grad">Her sürümü</span><br />
            kanıtıyla yayına alın
          </h1>
          <p>
            Test case’leri, koşumlar, milestone’lar ve raporlar tek yerde.
            Beş yıllık TestRail geçmişi burada, kaldığı yerden devam ediyor.
          </p>
          <div className="pills">
            <span>Test Case’ler</span>
            <span>Koşumlar</span>
            <span>Raporlar</span>
          </div>
        </section>

        <form className="signin-card" onSubmit={submit}>
          <div className="eyebrow">Giriş</div>
          <h2>Hesabınıza giriş yapın</h2>

          <label className="field">
            <span>E-posta</span>
            <input type="email" value={email} required autoFocus
                   autoComplete="username" placeholder="ad.soyad@dgpays.com"
                   onChange={(e) => setEmail(e.target.value)} />
          </label>

          <label className="field">
            <span>Parola</span>
            <input type="password" value={password} required
                   autoComplete="current-password"
                   onChange={(e) => setPassword(e.target.value)} />
          </label>

          <div className="signin-row">
            <label className="check">
              <input type="checkbox" checked={remember}
                     onChange={(e) => setRemember(e.target.checked)} />
              Oturumum açık kalsın
            </label>
            <a href="#" onClick={(e) => {
              e.preventDefault()
              setError('Parolanızı sıfırlamak için sistem yöneticinize başvurun.')
            }}>Parolamı unuttum</a>
          </div>

          {error && <div className="error">{error}</div>}

          <button className="primary big" type="submit" disabled={busy}>
            {busy ? 'Giriş yapılıyor…' : 'Giriş yap'}
          </button>
        </form>
      </div>

      <footer className="signin-foot">
        <span>DGPays</span>
        <span>{VERSION}</span>
      </footer>
    </div>
  )
}
