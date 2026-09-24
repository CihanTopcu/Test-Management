import { useCallback, useEffect, useState } from 'react'

/**
 * Hash routing, shaped like TestRail's own URLs.
 *
 * Everything people point each other at gets its own address:
 *   #/dashboard             (projeden bagimsiz)
 *   #/p/3/overview
 *   #/p/3/suites            #/p/3/suites/42          #/p/3/suites/42/sec/300
 *   #/p/3/cases/15477
 *   #/p/3/runs              #/p/3/runs/73150/t/9236740
 *   #/p/3/milestones        #/p/3/milestones/558
 *
 * Those TestRail links are pasted all over this company's Jira, so a UI whose
 * state lived only in React would break a daily habit on day one.
 */
export type Page = 'overview' | 'todo' | 'suites' | 'cases' | 'runs'
  | 'plans' | 'milestones' | 'shared' | 'reports' | 'admin' | 'dashboard'
  | 'settings' | 'today'

export interface Route {
  page: Page
  project?: number
  suite?: number
  section?: number
  case?: number
  run?: number
  test?: number
  plan?: number
  milestone?: number
}

const PAGES: Page[] = ['overview', 'todo', 'suites', 'cases', 'runs',
                       'plans', 'milestones', 'shared', 'reports', 'admin',
                       'dashboard', 'settings', 'today']

function parse(): Route {
  const parts = location.hash.replace(/^#\/?/, '').split('/').filter(Boolean)
  // the front door is work, not statistics
  const route: Route = { page: 'today' }

  let i = 0
  if (parts[i] === 'p') {
    route.project = Number(parts[i + 1]) || undefined
    i += 2
  }
  const page = parts[i] as Page
  if (PAGES.includes(page)) {
    route.page = page
    i += 1
  }

  const id = Number(parts[i])
  if (Number.isFinite(id) && parts[i] !== undefined) {
    if (route.page === 'suites') route.suite = id
    else if (route.page === 'cases') route.case = id
    else if (route.page === 'runs') route.run = id
    else if (route.page === 'plans') route.plan = id
    else if (route.page === 'milestones') route.milestone = id
    i += 1
  }
  // trailing key/value pairs: /sec/300, /t/9236740
  for (; i < parts.length; i += 2) {
    const value = Number(parts[i + 1])
    if (!Number.isFinite(value)) continue
    if (parts[i] === 'sec') route.section = value
    else if (parts[i] === 't') route.test = value
  }
  return route
}

export function href(route: Route): string {
  const parts: string[] = []
  if (route.project) parts.push('p', String(route.project))
  parts.push(route.page)
  if (route.page === 'suites' && route.suite) {
    parts.push(String(route.suite))
    if (route.section) parts.push('sec', String(route.section))
  } else if (route.page === 'cases' && route.case) {
    parts.push(String(route.case))
  } else if (route.page === 'runs' && route.run) {
    parts.push(String(route.run))
    if (route.test) parts.push('t', String(route.test))
  } else if (route.page === 'plans' && route.plan) {
    parts.push(String(route.plan))
  } else if (route.page === 'milestones' && route.milestone) {
    parts.push(String(route.milestone))
  }
  return '#/' + parts.join('/')
}

export function useRoute(): [Route, (next: Route) => void] {
  const [route, setRoute] = useState<Route>(parse)

  useEffect(() => {
    const onChange = () => setRoute(parse())
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])

  const go = useCallback((next: Route) => {
    const hash = href(next)
    if (hash !== location.hash) location.hash = hash
    else setRoute(next)
  }, [])

  return [route, go]
}
