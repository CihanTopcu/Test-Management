import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import { href } from '../route'
import { Icon } from './Icon'

interface Hit { id: number; title?: string; name?: string; suite_id?: number; exact?: boolean }
interface Results { cases: Hit[]; runs: Hit[]; milestones: Hit[]; total: number }

/**
 * Search in the masthead.
 *
 * With 64k cases nobody finds anything by walking the tree, and the one
 * lookup people do constantly is "what is C15477" -- so a bare id jumps
 * straight there instead of being treated as a phrase.
 */
export function Omnibox({ projectId }: { projectId?: number }) {
  const [term, setTerm] = useState('')
  const [results, setResults] = useState<Results | null>(null)
  const [open, setOpen] = useState(false)
  const box = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (term.trim().length < 2) { setResults(null); return }
    const timer = setTimeout(async () => {
      try {
        const params = new URLSearchParams({ q: term.trim() })
        if (projectId) params.set('project_id', String(projectId))
        setResults(await api.get<Results>(`/api/search?${params}`))
        setOpen(true)
      } catch {
        setResults(null)
      }
    }, 220)
    return () => clearTimeout(timer)
  }, [term, projectId])

  useEffect(() => {
    const away = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', away)
    return () => document.removeEventListener('mousedown', away)
  }, [])

  // ctrl+k / cmd+k, because everyone reaches for it
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        box.current?.querySelector('input')?.focus()
      }
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('keydown', key)
    return () => document.removeEventListener('keydown', key)
  }, [])

  const go = (url: string) => {
    location.hash = url
    setOpen(false)
    setTerm('')
  }

  return (
    <div className="omnibox" ref={box}>
      <Icon name="search" size={15} />
      <input value={term} placeholder="Ara…  (Ctrl+K)"
             onChange={(e) => setTerm(e.target.value)}
             onFocus={() => results && setOpen(true)} />

      {open && results && (
        <div className="results">
          {results.total === 0 && (
            <div className="grp" style={{ textTransform: 'none' }}>Sonuç yok</div>
          )}

          {results.cases.length > 0 && <div className="grp">Test case</div>}
          {results.cases.slice(0, 12).map((c) => (
            <a key={c.id} href="#"
               onClick={(e) => { e.preventDefault(); go(href({ page: 'cases', project: projectId, case: c.id })) }}>
              <span className="cid">C{c.id}</span>{' '}{c.title}
              {c.exact && <span className="hint"> · tam eşleşme</span>}
            </a>
          ))}

          {results.runs.length > 0 && <div className="grp">Koşum</div>}
          {results.runs.map((r) => (
            <a key={r.id} href="#"
               onClick={(e) => { e.preventDefault(); go(href({ page: 'runs', project: projectId, run: r.id })) }}>
              {r.name}
            </a>
          ))}

          {results.milestones.length > 0 && <div className="grp">Milestone</div>}
          {results.milestones.map((m) => (
            <a key={m.id} href="#"
               onClick={(e) => { e.preventDefault(); go(href({ page: 'milestones', project: projectId })) }}>
              {m.name}
            </a>
          ))}
        </div>
      )}
    </div>
  )
}
