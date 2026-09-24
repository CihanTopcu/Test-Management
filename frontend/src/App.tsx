import { useEffect, useState } from 'react'
import { api, getToken } from './api/client'
import { useMe, useProjectStats, useProjects } from './api/hooks'
import { Icon, type IconName } from './components/Icon'
import { Logo } from './components/Logo'
import { Notifications } from './components/Notifications'
import { Omnibox } from './components/Omnibox'
import { Shortcuts } from './components/Shortcuts'
import { Admin } from './pages/Admin'
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
import { SharedSteps } from './pages/SharedSteps'
import { SuiteView } from './pages/SuiteView'
import { Today } from './pages/Today'
import { Suites } from './pages/Suites'
import { Todo } from './pages/Todo'
import { projectColor } from './projectColor'
import { href, useRoute, type Page, type Route } from './route'

const THEME_KEY = 'tm.theme'
const PROJECT_KEY = 'tm.project'

const NAV: { page: Page; label: string; icon: IconName }[] = [
  { page: 'overview', label: 'Proje Özeti', icon: 'grid' },
  { page: 'todo', label: 'Yapılacaklar', icon: 'check-circle' },
  { page: 'suites', label: 'Test Case’leri', icon: 'list' },
  { page: 'runs', label: 'Koşumlar ve Sonuçlar', icon: 'play' },
  { page: 'plans', label: 'Test Planları', icon: 'folder' },
  { page: 'milestones', label: 'Milestone’lar', icon: 'flag' },
  { page: 'shared', label: 'Paylaşılan Adımlar', icon: 'file' },
  { page: 'reports', label: 'Raporlar', icon: 'chart' },
]

function readStored(key: string) {
  try { return localStorage.getItem(key) } catch { return null }
}

function Rail({ route, projectName }: { route: Route; projectName: string }) {
  const { data: stats } = useProjectStats(route.project)
  // the case page has no nav entry of its own; it belongs under the suites tab
  const active: Page = route.page === 'cases' ? 'suites' : route.page
  // the rail carries the project's identity colour: with sixteen projects
  // that all look alike, this is what stops people reading the wrong one
  const colour = projectColor(route.project)

  return (
    <aside className="rail" style={{
      '--project': colour.ink, '--project-soft': colour.soft,
    } as React.CSSProperties}>
      <div className="proj">
        <span className="chip">{projectName.slice(0, 1) || '?'}</span>
        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{projectName}</span>
      </div>
      {NAV.map((item) => (
        <a key={item.page}
           className={active === item.page ? 'active' : ''}
           href={href({ page: item.page, project: route.project })}>
          <Icon name={item.icon} size={16} />
          {item.label}
        </a>
      ))}
      {stats && (
        <div className="note">
          {stats.suites} suite · {stats.cases.toLocaleString('tr-TR')} case
          <br />
          {stats.runs.toLocaleString('tr-TR')} koşum · {stats.milestones} milestone
        </div>
      )}
    </aside>
  )
}

function Shell() {
  const { data: me } = useMe()
  const { data: projects = [] } = useProjects()
  const [route, go] = useRoute()
  const [dark, setDark] = useState(() => readStored(THEME_KEY) === 'dark')

  useEffect(() => {
    document.documentElement.dataset.theme = dark ? 'dark' : 'light'
    try { localStorage.setItem(THEME_KEY, dark ? 'dark' : 'light') } catch { /* ignore */ }
  }, [dark])

  // a link without a project falls back to the last one used, then the first
  useEffect(() => {
    if (route.page === 'dashboard' || route.page === 'settings'
        || route.page === 'today') return
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
      case 'cases': return <CaseView route={route} projectName={projectName} />
      case 'runs': return <Runs route={route} projectName={projectName} />
      case 'milestones': return route.milestone
        ? <MilestoneView route={route} projectName={projectName} />
        : <Milestones route={route} projectName={projectName} />
      case 'plans': return <Plans route={route} projectName={projectName} />
      case 'shared': return <SharedSteps route={route} projectName={projectName} />
      case 'todo': return <Todo />
      case 'reports': return <Reports route={route} projectName={projectName} />
      case 'admin': return <Admin />
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
                  page: route.page === 'cases' || route.page === 'dashboard'
                    ? 'suites' : route.page,
                  project: Number(e.target.value),
                })}>
          {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>

        <a className={`masthead-link ${route.page === 'today' ? 'active' : ''}`}
           href={href({ page: 'today' })}>
          <Icon name="check-circle" size={15} /> Bugün
        </a>
        <a className={`masthead-link ${route.page === 'dashboard' ? 'active' : ''}`}
           href={href({ page: 'dashboard' })}>
          <Icon name="grid" size={15} /> Tüm Projeler
        </a>

        <Omnibox projectId={route.project} />

        <div className="spacer" />

        <Notifications />
        <button className="ghost icon-only" title="Tema" onClick={() => setDark(!dark)}>
          <Icon name={dark ? 'sun' : 'moon'} size={16} />
        </button>
        <a href={href({ page: 'admin', project: route.project })}
           className="who" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <Icon name="settings" size={15} /> Yönetim
        </a>
        <a className="who" href={href({ page: 'settings' })}
           title="Bildirim ve rapor ayarları">
          {me?.name}
        </a>
        <button className="ghost icon-only" title="Çıkış"
                onClick={() => api.logout().then(() => location.reload())}>
          <Icon name="logout" size={16} />
        </button>
      </header>

      <Shortcuts route={route} />

      <div className="body">
        {route.project && route.page !== 'dashboard'
          && route.page !== 'settings' && route.page !== 'today' && (
          <Rail route={route} projectName={projectName} />
        )}
        {page()}
      </div>
    </div>
  )
}

export default function App() {
  const [authed, setAuthed] = useState(() => !!getToken())
  if (!authed) return <Login onDone={() => setAuthed(true)} />
  return <Shell />
}
