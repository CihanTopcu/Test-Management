import { useCallback, useEffect, useState } from 'react'
import { api, getToken, setToken } from './api/client'
import { useMe, useProjectStats, useProjects } from './api/hooks'
import { Icon, type IconName } from './components/Icon'
import { Logo } from './components/Logo'
import { Notifications } from './components/Notifications'
import { Omnibox } from './components/Omnibox'
import { Shortcuts } from './components/Shortcuts'
import { Admin } from './pages/Admin'
import { CaseExplorer } from './pages/CaseExplorer'
import { CaseView } from './pages/CaseView'
import { Dashboard } from './pages/Dashboard'
import { Login } from './pages/Login'
import { MilestoneView } from './pages/MilestoneView'
import { Milestones } from './pages/Milestones'
import { Overview } from './pages/Overview'
import { Plans } from './pages/Plans'
import { Reports } from './pages/Reports'
import { Runs } from './pages/Runs'
import { Settings } from './pages/Settings'
import { SetPassword } from './pages/SetPassword'
import { SharedSteps } from './pages/SharedSteps'
import { SuiteView } from './pages/SuiteView'
import { Today } from './pages/Today'
import { Suites } from './pages/Suites'
import { Todo } from './pages/Todo'
import { projectVars } from './projectColor'
import { href, useRoute, type Page, type Route } from './route'

const THEME_KEY = 'tm.theme-choice'
const LEGACY_THEME_KEY = 'tm.theme'
const PROJECT_KEY = 'tm.project'
const RAIL_KEY = 'tm.rail'

const NAV: { page: Page; label: string; icon: IconName }[] = [
  { page: 'overview', label: 'Proje Özeti', icon: 'grid' },
  { page: 'todo', label: 'Yapılacaklar', icon: 'check-circle' },
  { page: 'suites', label: 'Test Case’leri', icon: 'list' },
  { page: 'cases', label: 'Case Gezgini', icon: 'search' },
  { page: 'runs', label: 'Koşumlar ve Sonuçlar', icon: 'play' },
  { page: 'plans', label: 'Test Planları', icon: 'folder' },
  { page: 'milestones', label: 'Milestone’lar', icon: 'flag' },
  { page: 'shared', label: 'Paylaşılan Adımlar', icon: 'file' },
  { page: 'reports', label: 'Raporlar', icon: 'chart' },
]

/** Screens about the whole workspace rather than one project: no rail, and
 *  the project picker shows no project instead of a stale one. */
const GLOBAL_PAGES: Page[] = ['dashboard', 'settings', 'today', 'admin']

function readStored(key: string) {
  try { return localStorage.getItem(key) } catch { return null }
}

/**
 * Dark by default, as dgpays.com is; the toggle stores a choice. index.html
 * applies a stored 'light' before the first paint, so this only has to keep
 * the attribute in step afterwards. The old key is dropped: it was written
 * on every visit and never recorded a decision.
 */
function useTheme(): [boolean, (dark: boolean) => void] {
  const [dark, setDark] = useState(() => readStored(THEME_KEY) !== 'light')

  useEffect(() => {
    if (dark) delete document.documentElement.dataset.theme
    else document.documentElement.dataset.theme = 'light'
  }, [dark])

  const choose = (next: boolean) => {
    setDark(next)
    try {
      localStorage.setItem(THEME_KEY, next ? 'dark' : 'light')
      localStorage.removeItem(LEGACY_THEME_KEY)
    } catch { /* ignore */ }
  }
  return [dark, choose]
}

function Rail({ route, projectName }: { route: Route; projectName: string }) {
  const { data: stats } = useProjectStats(route.project)
  // one case belongs under the suite it lives in; the project-wide filtered
  // library is its own entry, which reports drill into
  const active: Page = route.page === 'cases' && route.case ? 'suites' : route.page
  // the suite screen is three columns wide -- rail, section tree, cases -- and
  // the cases were the ones getting squeezed; folded, the rail keeps only icons
  const [folded, setFolded] = useState(() => readStored(RAIL_KEY) === 'folded')
  const fold = (next: boolean) => {
    setFolded(next)
    try { localStorage.setItem(RAIL_KEY, next ? 'folded' : 'open') } catch { /* ignore */ }
  }
  // the rail carries the project's identity colour: with sixteen projects
  // that all look alike, this is what stops people reading the wrong one
  return (
    <aside className={`rail projvars ${folded ? 'folded' : ''}`}
           style={projectVars(route.project)}>
      <div className="proj" title={projectName}>
        <span className="chip">{projectName.slice(0, 1) || '?'}</span>
        <span className="label" style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>
          {projectName}
        </span>
      </div>
      {NAV.map((item) => (
        <a key={item.page}
           className={active === item.page ? 'active' : ''}
           title={folded ? item.label : undefined}
           href={href({ page: item.page, project: route.project })}>
          <Icon name={item.icon} size={16} />
          <span className="label">{item.label}</span>
        </a>
      ))}
      {stats && (
        <div className="note">
          {stats.suites} suite · {stats.cases.toLocaleString('tr-TR')} case
          <br />
          {stats.runs.toLocaleString('tr-TR')} koşum · {stats.milestones} milestone
        </div>
      )}
      <button className="ghost fold" onClick={() => fold(!folded)}
              title={folded ? 'Menüyü genişlet' : 'Menüyü daralt'}>
        <Icon name={folded ? 'chevron-right' : 'chevron-left'} size={14} />
        <span className="label">Menüyü daralt</span>
      </button>
    </aside>
  )
}

function Shell() {
  const { data: me } = useMe()
  const { data: projects = [] } = useProjects()
  const [route, go] = useRoute()
  const [dark, setDark] = useTheme()

  // a link without a project falls back to the last one used, then the first
  useEffect(() => {
    if (GLOBAL_PAGES.includes(route.page)) {
      // old links carry a project (#/p/1/admin, in notifications already
      // sent); keep them working, but land on the project-less address
      if (route.project) go({ ...route, project: undefined })
      return
    }
    if (!route.project && projects.length) {
      const remembered = Number(readStored(PROJECT_KEY))
      const known = projects.some((p) => p.id === remembered)
      go({ ...route, project: known ? remembered : projects[0].id })
    }
  }, [projects, route, go])

  useEffect(() => {
    if (route.project) {
      try { localStorage.setItem(PROJECT_KEY, String(route.project)) } catch { /* ignore */ }
    }
  }, [route.project])

  const project = projects.find((p) => p.id === route.project)
  const projectName = project?.name ?? ''

  const page = () => {
    // the only screen that is not about one project
    if (route.page === 'dashboard') return <Dashboard />
    if (route.page === 'settings') return <Settings />
    // users, roles and fields are workspace-wide; it used to sit under
    // #/p/N/admin with a project rail that had nothing to do with it
    if (route.page === 'admin') return <Admin />
    // the front door: work, not statistics
    if (route.page === 'today') return <Today />
    if (!route.project) {
      return <main className="main"><div className="faint">Proje yükleniyor…</div></main>
    }
    switch (route.page) {
      case 'overview': return <Overview route={route} projectName={projectName} />
      case 'suites':
        return route.suite
          ? <SuiteView route={route} projectName={projectName} />
          : <Suites route={route} projectName={projectName} />
      // a case id opens that case; without one it is the project-wide
      // filtered library, which is where every report drills into
      case 'cases': return route.case
        ? <CaseView route={route} projectName={projectName} />
        : <CaseExplorer route={route} projectName={projectName} />
      case 'runs': return <Runs route={route} projectName={projectName} />
      case 'milestones': return route.milestone
        ? <MilestoneView route={route} projectName={projectName} />
        : <Milestones route={route} projectName={projectName} />
      case 'plans': return <Plans route={route} projectName={projectName} />
      case 'shared': return <SharedSteps route={route} projectName={projectName} />
      case 'todo': return <Todo />
      case 'reports': return <Reports route={route} projectName={projectName} />
    }
  }

  return (
    <div className="app">
      <header className="masthead">
        <a className="brand" href={href({ page: 'dashboard' })}
           title="Tüm projeler">
          <Logo size={20} />
        </a>

        <select className="project" value={route.project ?? ''}
                onChange={(e) => go({
                  // same screen in the other project where that makes sense;
                  // from a workspace-wide screen, the project's overview
                  page: GLOBAL_PAGES.includes(route.page) ? 'overview'
                    : route.page === 'cases' ? 'suites' : route.page,
                  project: Number(e.target.value),
                })}>
          {!route.project && <option value="" disabled>Proje seçin…</option>}
          {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>

        <a className={`masthead-link ${route.page === 'today' ? 'active' : ''}`}
           href={href({ page: 'today' })} title="Bugün">
          <Icon name="check-circle" size={15} /> <span className="label">Bugün</span>
        </a>
        <a className={`masthead-link ${route.page === 'dashboard' ? 'active' : ''}`}
           href={href({ page: 'dashboard' })} title="Tüm Projeler">
          <Icon name="grid" size={15} /> <span className="label">Tüm Projeler</span>
        </a>

        <Omnibox projectId={route.project} />

        <div className="spacer" />

        <Notifications />
        <button className="ghost icon-only" title="Tema" onClick={() => setDark(!dark)}>
          <Icon name={dark ? 'sun' : 'moon'} size={16} />
        </button>
        <a href={href({ page: 'admin' })}
           className="who" title="Yönetim"
           style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <Icon name="settings" size={15} /> <span className="label">Yönetim</span>
        </a>
        <a className="who" href={href({ page: 'settings' })}
           title="Bildirim ve rapor ayarları"
           style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span className="icon-narrow"><Icon name="user" size={15} /></span>
          <span className="label">{me?.name}</span>
        </a>
        <button className="ghost icon-only" title="Çıkış"
                onClick={() => api.logout().then(() => location.reload())}>
          <Icon name="logout" size={16} />
        </button>
      </header>

      <Shortcuts route={route} />

      <div className="body">
        {route.project && !GLOBAL_PAGES.includes(route.page) && (
          <Rail route={route} projectName={projectName} />
        )}
        {page()}
      </div>
    </div>
  )
}

/** Why a company-account sign-in came back without signing anyone in. */
const SSO_ERRORS: Record<string, string> = {
  unknown: 'Bu hesabın DGTest’te bir kullanıcısı yok ya da pasif. Yöneticinizden hesap açmasını isteyin.',
  denied: 'Giriş, hesap sağlayıcısı tarafında iptal edildi.',
  expired: 'Giriş yarıda kaldı ya da süresi doldu; tekrar deneyin.',
  missing: 'Giriş yarıda kaldı ya da süresi doldu; tekrar deneyin.',
  state: 'Giriş isteği doğrulanamadı; tekrar deneyin.',
}

/**
 * Where the provider sends the browser back (#/sso). The server has already
 * set the session cookie; this trades it for the bearer token the app
 * keeps, so no token ever sits in the address bar.
 */
function SsoReturn({ onDone, onFail }: {
  onDone: () => void
  onFail: (message: string) => void
}) {
  useEffect(() => {
    const cut = location.hash.indexOf('?')
    const error = cut < 0 ? null : new URLSearchParams(location.hash.slice(cut + 1)).get('error')
    if (error) {
      onFail(SSO_ERRORS[error] ?? 'Kimlik doğrulanamadı; tekrar deneyin, sürerse yöneticinize bildirin.')
      return
    }
    api.post<{ access_token: string }>('/api/auth/session-token', {})
      .then((r) => { setToken(r.access_token); onDone() })
      .catch(() => onFail('Oturum açılamadı; tekrar deneyin.'))
  }, [onDone, onFail])
  return (
    <div className="signin">
      <div className="signin-body single">
        <div className="signin-card"><div className="skeleton" style={{ width: 180 }} /></div>
      </div>
    </div>
  )
}

export default function App() {
  const [authed, setAuthed] = useState(() => !!getToken())
  const [ssoReturn, setSsoReturn] = useState(() => location.hash.startsWith('#/sso'))
  const [ssoNotice, setSsoNotice] = useState<string | null>(null)
  const ssoDone = useCallback(() => {
    setSsoReturn(false); setAuthed(true); location.hash = '#/today'
  }, [])
  const ssoFail = useCallback((message: string) => {
    setSsoReturn(false); setSsoNotice(message); location.hash = '#/'
  }, [])
  // an invitation or reset link works whether or not someone is signed in
  // on this browser -- it may well be the administrator's own machine
  const [settingPassword, setSettingPassword] = useState(
    () => location.hash.startsWith('#/set-password'))

  // every hook above this line: an early return before one of them changes
  // the hook count between renders, and React blanks the page
  if (ssoReturn) return <SsoReturn onDone={ssoDone} onFail={ssoFail} />
  if (settingPassword) {
    return <SetPassword onDone={() => {
      setSettingPassword(false)
      setAuthed(true)
      location.hash = '#/today'
    }} />
  }
  if (!authed) return <Login notice={ssoNotice} onDone={() => setAuthed(true)} />
  return <Shell />
}
