import { useEffect, useMemo, useState } from 'react'
import {
  useBulkStatus, useCases, useCatalog, useDeleteRun, useProjectStats,
  useRunMembership, useRunPages, useRunSummary, useRuns, useSections, useTests, useUsers,
} from '../api/hooks'
import { AddRunDialog } from '../components/AddDialogs'
import { Confirm } from '../components/Confirm'
import { Dialog } from '../components/Dialog'
import { RunGrid } from '../components/RunGrid'
import { Icon } from '../components/Icon'
import { Donut, Legend, MiniBar, slices } from '../components/Status'
import { TestPanel } from '../components/TestPanel'
import { href, type Route } from '../route'
import { Crumbs } from '../components/Crumbs'
import { MoreMenu } from '../components/MoreMenu'

/** Run index: grouped by day, the way TestRail lists them. */
function RunList({ route, projectName }: { route: Route; projectName: string }) {
  const [archived, setArchived] = useState(false)
  const [search, setSearch] = useState('')
  const [query, setQuery] = useState('')
  const pages = useRunPages(route.project, archived, query)
  const { isLoading, isFetching } = pages
  const runs = useMemo(() => pages.data?.pages.flat() ?? [], [pages.data])
  const { data: stats } = useProjectStats(route.project)
  const { data: catalog } = useCatalog()
  const [adding, setAdding] = useState(false)

  useEffect(() => {
    const timer = setTimeout(() => setQuery(search), 300)
    return () => clearTimeout(timer)
  }, [search])

  const byDay = useMemo(() => {
    const out: { day: string; runs: typeof runs }[] = []
    for (const run of runs) {
      const day = run.created_on
        ? new Date(run.created_on).toLocaleDateString('tr-TR',
            { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })
        : 'tarihsiz'
      const last = out[out.length - 1]
      if (last && last.day === day) last.runs.push(run)
      else out.push({ day, runs: [run] })
    }
    return out
  }, [runs])

  // the tab's total, so a partly loaded list says how much is still unseen
  const tabTotal = stats && !query
    ? (archived ? stats.archived_runs : stats.runs - stats.archived_runs) : null
  const shownLabel = tabTotal !== null && runs.length < tabTotal
    ? `${runs.length.toLocaleString('tr-TR')} / ${tabTotal.toLocaleString('tr-TR')} koşum gösteriliyor`
    : `${runs.length.toLocaleString('tr-TR')} koşum`

  if (isLoading) {
    return <main className="main"><div className="skeleton" style={{ width: 280 }} /></main>
  }

  return (
    <main className="main">
      <Crumbs projectId={route.project} projectName={projectName} />
      <div className="page-title">
        <h1>Test Koşumları ve Sonuçları</h1>
        <span className="faint small">
          {isFetching && !pages.isFetchingNextPage ? 'yükleniyor…' : shownLabel}
        </span>
        <button className="primary right" onClick={() => setAdding(true)}>
          <Icon name="plus" size={14} /> Koşum ekle
        </button>
      </div>

      <AddRunDialog projectId={route.project} open={adding}
                    onClose={() => setAdding(false)} />

      <div className="subtabs">
        <button className={archived ? '' : 'active'} onClick={() => setArchived(false)}>
          Aktif{stats ? ` (${stats.runs - stats.archived_runs})` : ''}
        </button>
        <button className={archived ? 'active' : ''} onClick={() => setArchived(true)}>
          Arşiv{stats ? ` (${stats.archived_runs.toLocaleString('tr-TR')})` : ''}
        </button>
      </div>

      <div className="toolbar">
        <input className="grow" placeholder="Koşum adında ara…" value={search}
               onChange={(e) => setSearch(e.target.value)} />
        {archived && (
          <span className="faint small">
            Arşivlenmiş koşumlar salt okunurdur; sonuç eklenemez.
          </span>
        )}
      </div>

      {runs.length === 0 ? (
        <div className="panel empty">
          <Icon name="play" size={28} />
          <b>{archived ? 'Arşivlenmiş koşum yok' : 'Aktif koşum yok'}</b>
          {query
            ? 'Aramanızla eşleşen koşum bulunamadı.'
            : archived
              ? 'Bu projede arşive alınmış koşum bulunmuyor.'
              : 'Yeni bir koşum başlatabilir veya arşive bakabilirsiniz.'}
        </div>
      ) : (
        <div className="panel">
          {byDay.map((group) => (
            <div key={group.day}>
              <div className="group-head" style={{ cursor: 'default' }}>
                <span className="name">{group.day}</span>
                <span className="count">{group.runs.length}</span>
              </div>
              <table>
                <tbody>
                  {group.runs.map((run) => {
                    const pct = run.test_count
                      ? Math.round((run.passed_count / run.test_count) * 100) : 0
                    return (
                      <tr key={run.id}
                          onClick={() => {
                            location.hash = href({
                              page: 'runs', project: route.project, run: run.id })
                          }}>
                        <td className="title">
                          {run.name}
                          {run.config && <span className="faint small"> · {run.config}</span>}
                        </td>
                        <td style={{ width: 150 }}>
                          <MiniBar run={run} catalog={catalog} />
                        </td>
                        <td className="small faint nowrap" style={{ width: 90 }}>
                          {run.test_count} test
                        </td>
                        <td className="nowrap" style={{ width: 54, textAlign: 'right' }}>
                          <b>{pct}%</b>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          ))}
        </div>
      )}

      {pages.hasNextPage && (
        <div className="loadmore">
          <button onClick={() => pages.fetchNextPage()}
                  disabled={pages.isFetchingNextPage}>
            {pages.isFetchingNextPage ? 'Yükleniyor…' : 'Daha eski koşumları yükle'}
          </button>
        </div>
      )}
    </main>
  )
}

/** Rows per page in the run grid. */
const PAGE_SIZE = 200

function RunView({ route, projectName }: { route: Route; projectName: string }) {
  const { data: runs = [] } = useRuns(route.project)
  const { data: catalog } = useCatalog()
  const { data: users = [] } = useUsers()
  const { data: summary } = useRunSummary(route.run)
  const [filter, setFilter] = useState<number | null>(null)
  const [assignee, setAssignee] = useState<number | ''>('')
  const [search, setSearch] = useState('')
  const [query, setQuery] = useState('')
  const [page, setPage] = useState(0)
  const [picked, setPicked] = useState<Set<number>>(new Set())
  const [deleting, setDeleting] = useState(false)
  const [adding, setAdding] = useState(false)
  const [addSearch, setAddSearch] = useState('')
  const [addPicked, setAddPicked] = useState<Set<number>>(new Set())
  // the row the keyboard is on; separate from the route, because opening
  // the panel is a deliberate act rather than a side effect of moving
  const [focused, setFocused] = useState<number | null>(null)

  useEffect(() => {
    const timer = setTimeout(() => { setQuery(search); setPage(0) }, 300)
    return () => clearTimeout(timer)
  }, [search])

  // the filters go to the server: with 10,062 tests in the biggest run, a
  // browser-side filter can only narrow the page it happens to be holding
  const { data: testPage, isFetching } = useTests(route.run, {
    statusId: filter,
    assignee: assignee === '' ? null : assignee,
    q: query,
    offset: page * PAGE_SIZE,
    limit: PAGE_SIZE,
  })
  const tests = testPage?.items ?? []
  const matching = testPage?.total ?? 0

  // every page starts with a row under the keyboard, so the first keystroke
  // does something instead of nothing
  useEffect(() => {
    if (!tests.length) { setFocused(null); return }
    setFocused((current) => (
      current != null && tests.some((t) => t.id === current)
        ? current
        : tests[0].id))
  }, [tests])
  const bulkStatus = useBulkStatus(route.run)
  const removeRun = useDeleteRun(route.project)
  const membership = useRunMembership(route.run)

  const run = runs.find((r) => r.id === route.run)
  const data = slices(catalog, summary?.by_status ?? {})
  const total = summary?.total ?? 0
  const passed = summary?.by_status['1'] ?? 0
  const untested = (summary?.by_status['3'] ?? 0) + (summary?.by_status['untested'] ?? 0)
  const pct = total ? Math.round((passed / total) * 100) : 0
  // The bar segments are the catalogue's own statuses in its own order, in
  // their own colours. An earlier version split the run two ways and painted
  // everything that was not passed red, so a run with two deferred tests
  // read as a run with two failures.
  const bar = (catalog?.statuses ?? [])
    .filter((st) => !st.is_untested)
    .map((st) => ({ id: st.id, label: st.label, color: st.color,
                    count: summary?.by_status[String(st.id)] ?? 0 }))
    .filter((st) => st.count > 0)

  const shown = tests

  const select = (testId?: number) => {
    location.hash = href({ page: 'runs', project: route.project, run: route.run, test: testId })
  }

  return (
    <main className="main">
      <Crumbs projectId={route.project} projectName={projectName} trail={[
        { label: 'Test Koşumları', href: href({ page: 'runs', project: route.project }) },
      ]} />

      <div className="page-title">
        <span className="idbadge run">R{route.run}</span>
        <h1>{run?.name ?? 'Koşum'}</h1>
        {run?.is_completed && <span className="badge soft">tamamlandı</span>}
        {run?.is_archived && (
          <span className="badge" style={{ background: 'var(--blocked)' }}>arşiv</span>
        )}
        {!run?.is_archived && (
          <div className="right row" style={{ gap: 6 }}>
            <button onClick={() => { setAddPicked(new Set()); setAdding(true) }}>
              <Icon name="plus" size={13} /> Case ekle
            </button>
            <MoreMenu items={[
              { label: 'Koşumu sil', icon: 'trash', danger: true,
                onClick: () => setDeleting(true) },
            ]} />
          </div>
        )}
      </div>

      <Confirm open={deleting} title="Koşumu sil" busy={removeRun.isPending}
               error={removeRun.isError ? (removeRun.error as Error).message : null}
               detail={`"${run?.name ?? ''}" koşumu, içindeki ${total} test ve`
                 + ' bunlara girilmiş bütün sonuçlar kalıcı olarak silinecek.'}
               onClose={() => setDeleting(false)}
               onConfirm={() => route.run && removeRun.mutate(route.run, {
                 onSuccess: () => {
                   setDeleting(false)
                   location.hash = href({ page: 'runs', project: route.project })
                 },
               })} />

      <AddCasesDialog open={adding} onClose={() => setAdding(false)}
                      suiteId={run?.suite_id ?? undefined}
                      search={addSearch} onSearch={setAddSearch}
                      picked={addPicked} onPick={setAddPicked}
                      busy={membership.add.isPending}
                      error={membership.add.isError
                        ? (membership.add.error as Error).message : null}
                      onAdd={() => membership.add.mutate([...addPicked], {
                        onSuccess: () => setAdding(false) })} />

      {total > 0 && (
        <div className="runprogress">
          <div className="track">
            {bar.map((st) => (
              <span key={st.id} title={`${st.label}: ${st.count}`}
                    style={{ width: `${(st.count / total) * 100}%`,
                             background: st.color ?? 'var(--text-dim)' }} />
            ))}
          </div>
          <b>{(total - untested).toLocaleString('tr-TR')}</b>
          <span className="faint">/ {total.toLocaleString('tr-TR')} sonuçlandı</span>
          <span className="right"><b>%{pct}</b> <span className="faint">passed</span></span>
        </div>
      )}

      {total > 0 && (
        <div className="panel" style={{ padding: 16, marginBottom: 12 }}>
          <div className="donut-wrap">
            <Donut data={data} size={140} />
            <div className="pass-big">
              <div className="n">{pct}%</div>
              <div className="k">geçti</div>
              <div className="k">
                {(total - untested).toLocaleString('tr-TR')} / {total.toLocaleString('tr-TR')} sonuçlandı
              </div>
            </div>
            <div style={{ flex: 1, minWidth: 260 }}>
              <Legend data={data} total={total} active={filter}
                      onPick={(id) => {
                        setFilter(filter === id ? null : id)
                        setPage(0)
                        setPicked(new Set())
                      }} />
            </div>
          </div>
        </div>
      )}

      <div className="toolbar">
        <input className="grow" placeholder="Test başlığında ara…" value={search}
               onChange={(e) => setSearch(e.target.value)} />
        <select style={{ width: 170 }} value={assignee}
                onChange={(e) => {
                  setAssignee(e.target.value === '' ? '' : Number(e.target.value))
                  setPage(0)
                }}>
          <option value="">Herkes</option>
          {users.filter((u) => u.is_active).map((u) => (
            <option key={u.id} value={u.id}>{u.name}</option>
          ))}
        </select>
        {(filter != null || assignee !== '' || query) && (
          <button className="ghost" onClick={() => {
            setFilter(null); setAssignee(''); setSearch(''); setPage(0)
          }}>
            <Icon name="close" size={13} /> Filtreyi temizle
          </button>
        )}
        <span className="faint small nowrap">
          {isFetching ? 'yükleniyor…'
            : matching === total
              ? `${total.toLocaleString('tr-TR')} test`
              : `${matching.toLocaleString('tr-TR')} / ${total.toLocaleString('tr-TR')} test`}
        </span>
        <button className="ghost" disabled={page === 0}
                onClick={() => { setPage(page - 1); setPicked(new Set()) }}>
          <Icon name="chevron-left" size={14} /> Önceki
        </button>
        <span className="faint small nowrap">
          {matching ? `${page * PAGE_SIZE + 1}–${Math.min((page + 1) * PAGE_SIZE, matching)}` : '0'}
        </span>
        <button className="ghost" disabled={(page + 1) * PAGE_SIZE >= matching}
                onClick={() => { setPage(page + 1); setPicked(new Set()) }}>
          Sonraki <Icon name="chevron-right" size={14} />
        </button>
      </div>

      <div className="split">
        <div className="list">
          <RunGrid tests={shown} catalog={catalog} users={users}
                   runId={route.run} archived={Boolean(run?.is_archived)}
                   focusedId={focused} onFocus={setFocused}
                   onOpen={select} picked={picked} onPick={setPicked}
                   emptyLabel="Bu filtreyle test yok." />

          {picked.size > 0 && (
            <div className="bulkbar">
              <b>{picked.size} test seçildi</b>
              <span className="faint small">toplu sonuç:</span>
              {catalog?.statuses.filter((st) => !st.is_untested).slice(0, 5).map((st) => (
                <button key={st.id} className="chip-toggle"
                        style={{ borderColor: st.color ?? undefined }}
                        disabled={bulkStatus.isPending}
                        onClick={() => bulkStatus.mutate(
                          { test_ids: [...picked], status_id: st.id },
                          { onSuccess: () => setPicked(new Set()) })}>
                  {st.label}
                </button>
              ))}
              {!run?.is_archived && (
                <button className="ghost danger"
                        disabled={membership.remove.isPending}
                        onClick={() => membership.remove.mutate([...picked], {
                          onSuccess: () => setPicked(new Set()) })}>
                  <Icon name="trash" size={13} /> Koşumdan çıkar
                </button>
              )}
              <button className="ghost right" onClick={() => setPicked(new Set())}>
                Seçimi temizle
              </button>
            </div>
          )}
        </div>

        {route.test != null && (
          <TestPanel testId={route.test} catalog={catalog}
                     projectId={route.project} runId={route.run}
                     archived={Boolean(run?.is_archived)}
                     onClose={() => select(undefined)} />
        )}
      </div>
    </main>
  )
}

/**
 * Picking cases to add to a run that is already under way.
 *
 * A run built from a section misses everything written afterwards, and until
 * now the only way to pick those up was to start over and lose the results
 * already entered.
 */
function AddCasesDialog({ open, onClose, suiteId, search, onSearch,
                          picked, onPick, onAdd, busy, error }: {
  open: boolean
  onClose: () => void
  suiteId?: number
  search: string
  onSearch: (value: string) => void
  picked: Set<number>
  onPick: (value: Set<number>) => void
  onAdd: () => void
  busy: boolean
  error: string | null
}) {
  const { data: sections = [] } = useSections(open ? suiteId : undefined)
  const { data: page } = useCases({
    suiteId: open ? suiteId : undefined,
    sectionId: null, q: search, sort: 'title', offset: 0, limit: 200,
  })
  // Cases already in the run are not filtered out here: with the run grid
  // paged, the browser does not know what is in it. The server skips the
  // duplicates and says how many it skipped.
  const items = page?.items ?? []
  const names = new Map<number, string>()
  const walk = (nodes: typeof sections) => {
    for (const n of nodes) { names.set(n.id, n.name); walk(n.children) }
  }
  walk(sections)

  return (
    <Dialog open={open} title="Koşuma case ekle" width={680} onClose={onClose}
            footer={<>
              <button onClick={onClose}>Vazgeç</button>
              <button className="primary" disabled={!picked.size || busy}
                      onClick={onAdd}>
                {busy ? 'Ekleniyor…' : `${picked.size} case ekle`}
              </button>
            </>}>
      <div className="stack">
        <input placeholder="Başlıkta ara…" value={search} autoFocus
               onChange={(e) => onSearch(e.target.value)} />
        {error && <div className="error">{error}</div>}
        <div className="panel" style={{ maxHeight: 340, overflow: 'auto' }}>
          <table>
            <tbody>
              {items.map((c) => (
                <tr key={c.id} onClick={() => {
                  const next = new Set(picked)
                  if (next.has(c.id)) next.delete(c.id)
                  else next.add(c.id)
                  onPick(next)
                }}>
                  <td style={{ width: 32 }}>
                    <input type="checkbox" readOnly checked={picked.has(c.id)} />
                  </td>
                  <td className="cid">C{c.id}</td>
                  <td className="title">{c.title}</td>
                  <td className="small muted">{names.get(c.section_id) ?? ''}</td>
                </tr>
              ))}
              {!items.length && (
                <tr><td className="faint small">
                  Bu aramayla case bulunamadı.
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </Dialog>
  )
}

export function Runs(props: { route: Route; projectName: string }) {
  return props.route.run ? <RunView {...props} /> : <RunList {...props} />
}
