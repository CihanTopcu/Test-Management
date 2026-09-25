import { Fragment, useCallback, useEffect, useRef, useState } from 'react'
import { useAddResult } from '../api/hooks'
import type { Catalog, Test, User } from '../api/types'
import { Icon } from '../components/Icon'
import { StatusBadge, statusColor } from '../components/Status'

/**
 * The screen a tester spends the day in.
 *
 * It used to take five actions to record one verdict: click the row, read
 * the side panel, pick a chip, then save. On a 200-test run that is the
 * whole job, and the biggest run here holds 10,062. So the grid itself
 * became the instrument:
 *
 *   j / k or ↑ ↓   move
 *   1 … 5          give a verdict on the focused row, immediately
 *   n              jump to the next untested test
 *   Enter          open the detail panel for notes, steps, attachments
 *   x              tick the row for a bulk action
 *
 * The panel is still there and still does everything it did; it is simply
 * no longer on the path between a tester and a verdict.
 */

/** Keys 1-5 map to the catalog's own enterable statuses, in its order. */
function shortcutStatuses(catalog?: Catalog) {
  return (catalog?.statuses ?? []).filter((s) => !s.is_untested).slice(0, 5)
}

export function RunGrid({
  tests, catalog, users, runId, archived, focusedId, onFocus, onOpen,
  picked, onPick, emptyLabel, sectionNames,
}: {
  tests: Test[]
  /** section id -> "Parent › Child"; a heading is drawn where it changes */
  sectionNames?: Map<number, string>
  catalog?: Catalog
  users: User[]
  runId?: number | null
  archived: boolean
  focusedId: number | null
  onFocus: (id: number | null) => void
  onOpen: (id: number) => void
  picked: Set<number>
  onPick: (next: Set<number>) => void
  emptyLabel: string
}) {
  const addResult = useAddResult(runId)
  const body = useRef<HTMLTableSectionElement>(null)
  const [flash, setFlash] = useState<number | null>(null)
  const statuses = shortcutStatuses(catalog)

  const index = tests.findIndex((t) => t.id === focusedId)

  const move = useCallback((delta: number) => {
    if (!tests.length) return
    const next = index < 0
      ? 0
      : Math.min(tests.length - 1, Math.max(0, index + delta))
    onFocus(tests[next].id)
  }, [index, tests, onFocus])

  const give = useCallback((testId: number, statusId: number) => {
    if (archived) return
    addResult.mutate({ testId, body: { status_id: statusId } })
    // a brief tint so a keyboard run still feels like it landed somewhere
    setFlash(testId)
    window.setTimeout(() => setFlash((f) => (f === testId ? null : f)), 420)
  }, [addResult, archived])

  const nextUntested = useCallback(() => {
    const from = index < 0 ? 0 : index + 1
    const hit = tests.findIndex(
      (t, i) => i >= from && (t.status_id == null || t.status_id === 3))
    if (hit >= 0) onFocus(tests[hit].id)
  }, [index, tests, onFocus])

  // keyboard, scoped to this grid: a global listener would fight the
  // application's own g-prefixed navigation and the search box
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null
      if (el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA'
                 || el.tagName === 'SELECT' || el.isContentEditable)) return
      if (e.ctrlKey || e.metaKey || e.altKey) return

      if (e.key === 'j' || e.key === 'ArrowDown') { e.preventDefault(); move(1); return }
      if (e.key === 'k' || e.key === 'ArrowUp') { e.preventDefault(); move(-1); return }
      if (e.key === 'n') { e.preventDefault(); nextUntested(); return }
      if (e.key === 'Enter' && focusedId != null) {
        e.preventDefault(); onOpen(focusedId); return
      }
      if (e.key === 'x' && focusedId != null) {
        e.preventDefault()
        const next = new Set(picked)
        if (next.has(focusedId)) next.delete(focusedId)
        else next.add(focusedId)
        onPick(next)
        return
      }
      const slot = Number(e.key)
      if (slot >= 1 && slot <= statuses.length && focusedId != null) {
        e.preventDefault()
        give(focusedId, statuses[slot - 1].id)
        // keep going down the list, the way a person actually works
        move(1)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [move, nextUntested, give, focusedId, picked, onPick, onOpen, statuses])

  // keep the focused row in view when the keyboard is driving
  useEffect(() => {
    if (focusedId == null) return
    body.current
      ?.querySelector(`[data-test="${focusedId}"]`)
      ?.scrollIntoView({ block: 'nearest' })
  }, [focusedId])

  return (
    <div className="panel rungrid" style={{ overflow: 'auto' }}>
      <table>
        <thead>
          <tr>
            <th style={{ width: 34 }}>
              <input type="checkbox"
                     checked={picked.size > 0 && picked.size === tests.length}
                     onChange={(e) => onPick(
                       e.target.checked ? new Set(tests.map((t) => t.id)) : new Set())} />
            </th>
            <th style={{ width: 96 }}>ID</th>
            <th>Test</th>
            <th style={{ width: 108 }}>Durum</th>
            <th style={{ width: 176 }} />
            <th style={{ width: 130 }}>Atanan</th>
          </tr>
        </thead>
        <tbody ref={body}>
          {tests.map((t, i) => {
            // tests arrive in section-tree order, so a heading wherever the
            // section changes is the TestRail grouping without a second query
            const section = t.section_id ?? null
            const heading = sectionNames && section != null
              && (i === 0 || (tests[i - 1].section_id ?? null) !== section)
              ? sectionNames.get(section) ?? `Bölüm ${section}` : null
            const done = t.status_id === 1
            const untested = t.status_id == null || t.status_id === 3
            // Anything that is neither passed nor untested gets a wash in
            // its own catalogue colour. An earlier version painted all of
            // them with the failure red, which told somebody scanning that
            // a deferred test had broken.
            const marked = !done && !untested
            return (
              <Fragment key={t.id}>
              {heading && (
                <tr className="sec-row">
                  <td colSpan={6}>
                    {heading.includes(' › ') && (
                      <span className="path">{heading.slice(0, heading.lastIndexOf(' › '))} › </span>
                    )}
                    <b>{heading.split(' › ').pop()}</b>
                  </td>
                </tr>
              )}
              <tr data-test={t.id}
                  style={marked
                    ? { '--row': statusColor(catalog, t.status_id) } as React.CSSProperties
                    : undefined}
                  className={[
                    focusedId === t.id ? 'focused' : '',
                    picked.has(t.id) ? 'selected' : '',
                    marked ? 'row-marked' : '',
                    done ? 'row-pass' : '',
                    flash === t.id ? 'row-flash' : '',
                  ].filter(Boolean).join(' ')}
                  onClick={() => onFocus(t.id)}
                  onDoubleClick={() => onOpen(t.id)}>
                <td onClick={(e) => e.stopPropagation()}>
                  <input type="checkbox" checked={picked.has(t.id)}
                         onChange={() => {
                           const next = new Set(picked)
                           if (next.has(t.id)) next.delete(t.id)
                           else next.add(t.id)
                           onPick(next)
                         }} />
                </td>
                <td className="cid">T{t.id}</td>
                <td className="title">{t.title}</td>
                <td><StatusBadge catalog={catalog} id={t.status_id} /></td>
                <td className="quickset" onClick={(e) => e.stopPropagation()}>
                  {!archived && statuses.map((s, i) => (
                    <button key={s.id} className="qs"
                            title={`${s.label}  (${i + 1})`}
                            style={{ '--qs': s.color ?? 'var(--text-dim)' } as React.CSSProperties}
                            onClick={() => { onFocus(t.id); give(t.id, s.id) }}>
                      {s.label.slice(0, 1)}
                    </button>
                  ))}
                </td>
                <td className="small muted assignee">
                  {users.find((u) => u.id === t.assignedto_id)?.name ?? '—'}
                </td>
              </tr>
              </Fragment>
            )
          })}
          {!tests.length && (
            <tr><td colSpan={6} className="faint">{emptyLabel}</td></tr>
          )}
        </tbody>
      </table>

      {!archived && tests.length > 0 && (
        <div className="gridhint">
          <kbd>j</kbd><kbd>k</kbd> gez
          <span />
          {statuses.map((s, i) => <kbd key={s.id}>{i + 1}</kbd>)} sonuç ver
          <span />
          <kbd>n</kbd> sonraki untested
          <span />
          <kbd>Enter</kbd> detay
          <span />
          <kbd>x</kbd> seç
          {addResult.isError && (
            <span className="err">
              <Icon name="warning" size={12} /> kaydedilemedi
            </span>
          )}
        </div>
      )}
    </div>
  )
}
