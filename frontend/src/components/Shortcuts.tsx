import { useEffect, useRef, useState } from 'react'
import { Dialog } from './Dialog'
import { href, type Page, type Route } from '../route'

/**
 * Keyboard navigation, in TestRail's two-key style: g then a letter.
 *
 * Testers live on the run grid all day and reach for the mouse to change
 * screens. The sequence is deliberately the same shape TestRail used, so the
 * habit carries over.
 */

const GOTO: { key: string; page: Page; label: string }[] = [
  { key: 'o', page: 'overview', label: 'Proje özeti' },
  { key: 'y', page: 'todo', label: 'Yapılacaklar' },
  { key: 'c', page: 'suites', label: 'Test case’leri' },
  { key: 'k', page: 'runs', label: 'Koşumlar' },
  { key: 'p', page: 'plans', label: 'Test planları' },
  { key: 'm', page: 'milestones', label: 'Milestone’lar' },
  { key: 'r', page: 'reports', label: 'Raporlar' },
  { key: 'd', page: 'dashboard', label: 'Tüm projeler' },
]

/** Typing in a field must never trigger a shortcut. */
function isTyping(target: EventTarget | null) {
  const el = target as HTMLElement | null
  if (!el) return false
  const tag = el.tagName
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT'
    || el.isContentEditable
}

export function Shortcuts({ route }: { route: Route }) {
  const [help, setHelp] = useState(false)
  const [pending, setPending] = useState(false)
  // held so a forgotten sequence cannot cancel the next one: without this,
  // the timer from an earlier g fires mid-way through the following g and
  // swallows the letter after it
  const timer = useRef<number | undefined>(undefined)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.ctrlKey || e.metaKey || e.altKey) return
      if (isTyping(e.target)) return

      if (pending) {
        const hit = GOTO.find((g) => g.key === e.key.toLowerCase())
        window.clearTimeout(timer.current)
        setPending(false)
        if (hit) {
          e.preventDefault()
          location.hash = href(hit.page === 'dashboard'
            ? { page: 'dashboard' }
            : { page: hit.page, project: route.project })
        }
        return
      }

      if (e.key === 'g') {
        window.clearTimeout(timer.current)
        setPending(true)
        // a lone g is not a command; forget it if nothing follows
        timer.current = window.setTimeout(() => setPending(false), 1500)
        return
      }
      if (e.key === '?' || (e.key === '/' && e.shiftKey)) {
        e.preventDefault()
        setHelp(true)
        return
      }
      if (e.key === '/') {
        e.preventDefault()
        document.querySelector<HTMLInputElement>('.omnibox input')?.focus()
      }
    }

    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [pending, route.project])

  return (
    <>
      {pending && (
        <div className="keyhint">
          <kbd>g</kbd> …
        </div>
      )}
      <Dialog open={help} title="Klavye kısayolları" width={520}
              onClose={() => setHelp(false)}
              footer={<button onClick={() => setHelp(false)}>Kapat</button>}>
        <div className="shortcuts">
          <div className="group">Gezinme</div>
          {GOTO.map((g) => (
            <div className="row" key={g.key}>
              <span><kbd>g</kbd> <kbd>{g.key}</kbd></span>
              <span className="muted">{g.label}</span>
            </div>
          ))}
          <div className="group">Genel</div>
          <div className="row">
            <span><kbd>/</kbd></span>
            <span className="muted">Aramaya git</span>
          </div>
          <div className="row">
            <span><kbd>Ctrl</kbd> <kbd>K</kbd></span>
            <span className="muted">Aramaya git</span>
          </div>
          <div className="row">
            <span><kbd>?</kbd></span>
            <span className="muted">Bu pencere</span>
          </div>
          <div className="row">
            <span><kbd>Esc</kbd></span>
            <span className="muted">Açık pencereyi kapat</span>
          </div>
        </div>
      </Dialog>
    </>
  )
}
