import { useEffect, useMemo, useState } from 'react'
import {
  useBulkUpdateCases, useCases, useCatalog, useCopyMoveCases, useDeleteFilter,
  useDeleteSection, useDeleteSuite, useSaveFilter, useSaveSection, useSaveSuite,
  useSavedFilters, useSections, useSuites, useUsers,
} from '../api/hooks'
import { AddCaseDialog, AddRunDialog } from '../components/AddDialogs'
import { Confirm } from '../components/Confirm'
import { Dialog } from '../components/Dialog'
import { Icon } from '../components/Icon'
import { ImportDialog } from '../components/ImportDialog'
import { SectionTree } from '../components/SectionTree'
import type { CaseSummary, SectionNode } from '../api/types'
import { href, type Route } from '../route'
import { Crumbs } from '../components/Crumbs'
import { MoreMenu } from '../components/MoreMenu'

const PAGE = 250

interface SectionInfo { name: string; path: string }

function indexSections(nodes: SectionNode[], prefix: string[] = [],
                       into: Map<number, SectionInfo> = new Map()) {
  for (const node of nodes) {
    into.set(node.id, { name: node.name, path: prefix.join(' › ') })
    indexSections(node.children, [...prefix, node.name], into)
  }
  return into
}

function countCases(nodes: SectionNode[]): number {
  return nodes.reduce((sum, n) => sum + n.case_count + countCases(n.children), 0)
}

export function SuiteView({ route, projectName }: { route: Route; projectName: string }) {
  const { data: suites = [] } = useSuites(route.project)
  const suite = suites.find((s) => s.id === route.suite)
  const { data: catalog } = useCatalog()
  const { data: users = [] } = useUsers()
  const bulk = useBulkUpdateCases()
  const copyMove = useCopyMoveCases()
  const { data: savedFilters = [] } = useSavedFilters(route.project)
  const saveFilter = useSaveFilter(route.project)
  const deleteFilter = useDeleteFilter(route.project)

  const [search, setSearch] = useState('')
  const [query, setQuery] = useState('')
  const [page, setPage] = useState(0)
  const [collapsed, setCollapsed] = useState<Set<number>>(new Set())
  const [picked, setPicked] = useState<Set<number>>(new Set())
  const [addingCase, setAddingCase] = useState(false)
  const [addingRun, setAddingRun] = useState(false)
  const [showFilters, setShowFilters] = useState(false)
  const [typeId, setTypeId] = useState<number | ''>('')
  const [priorityId, setPriorityId] = useState<number | ''>('')
  const [createdBy, setCreatedBy] = useState<number | ''>('')
  const [sort, setSort] = useState('section')
  const [moveTarget, setMoveTarget] = useState<number | ''>('')
  const [filterName, setFilterName] = useState('')
  const [savingFilter, setSavingFilter] = useState(false)
  const [importing, setImporting] = useState(false)
  const [renaming, setRenaming] = useState<'suite' | 'section' | null>(null)
  const [renameText, setRenameText] = useState('')
  const [movingSection, setMovingSection] = useState(false)
  const [moveParent, setMoveParent] = useState<number | ''>('')
  const [deleting, setDeleting] = useState<'suite' | 'section' | null>(null)

  const saveSuite = useSaveSuite(route.project)
  const deleteSuite = useDeleteSuite(route.project)
  const saveSection = useSaveSection(route.suite)
  const removeSection = useDeleteSection(route.suite)

  useEffect(() => {
    const timer = setTimeout(() => { setQuery(search); setPage(0) }, 300)
    return () => clearTimeout(timer)
  }, [search])

  useEffect(() => {
    setCollapsed(new Set()); setPage(0); setPicked(new Set())
  }, [route.suite, route.section])

  const { data: sections = [], isLoading: sectionsLoading } = useSections(route.suite)
  const { data: pageData, isFetching } = useCases({
    suiteId: route.suite,
    sectionId: route.section ?? null,
    q: query,
    typeId: typeId === '' ? undefined : typeId,
    priorityId: priorityId === '' ? undefined : priorityId,
    createdBy: createdBy === '' ? undefined : createdBy,
    sort,
    offset: page * PAGE,
    limit: PAGE,
  })

  const sectionIndex = useMemo(() => indexSections(sections), [sections])
  const treeTotal = useMemo(() => countCases(sections), [sections])
  const total = pageData?.total ?? 0
  const rows = useMemo(() => pageData?.items ?? [], [pageData])

  const groups = useMemo(() => {
    const out: { sectionId: number; rows: CaseSummary[] }[] = []
    for (const row of rows) {
      const last = out[out.length - 1]
      if (last && last.sectionId === row.section_id) last.rows.push(row)
      else out.push({ sectionId: row.section_id, rows: [row] })
    }
    return out
  }, [rows])

  const types = catalog?.case_types ?? []
  const priorities = catalog?.priorities ?? []
  const filtersOn = typeId !== '' || priorityId !== '' || createdBy !== ''

  const toggleGroup = (id: number) => setCollapsed((prev) => {
    const next = new Set(prev)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    return next
  })

  const togglePick = (id: number) => setPicked((prev) => {
    const next = new Set(prev)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    return next
  })

  const openCase = (id: number) => {
    location.hash = href({ page: 'cases', project: route.project, case: id })
  }

  const applyBulk = (patch: Record<string, unknown>) =>
    bulk.mutate({ case_ids: [...picked], ...patch },
                { onSuccess: () => setPicked(new Set()) })

  const flatSections: { id: number; label: string }[] = []
  const walkSections = (nodes: typeof sections, depth = 0) => {
    for (const n of nodes) {
      flatSections.push({ id: n.id, label: '\u00a0'.repeat(depth * 3) + n.name })
      walkSections(n.children, depth + 1)
    }
  }
  walkSections(sections)

  const applySaved = (criteria: Record<string, unknown>) => {
    setTypeId((criteria.type_id as number) ?? '')
    setPriorityId((criteria.priority_id as number) ?? '')
    setCreatedBy((criteria.created_by as number) ?? '')
    setSort((criteria.sort as string) ?? 'section')
    setSearch((criteria.q as string) ?? '')
    setPage(0)
    setShowFilters(true)
  }

  const currentCriteria = () => ({
    type_id: typeId === '' ? undefined : typeId,
    priority_id: priorityId === '' ? undefined : priorityId,
    created_by: createdBy === '' ? undefined : createdBy,
    sort,
    q: query || undefined,
  })

  const exportCsv = () => {
    const params = route.section ? `?section_id=${route.section}` : ''
    // the download carries the session cookie, so let the browser navigate
    window.open(`/api/suites/${route.suite}/cases.csv${params}`, '_blank')
  }

  return (
    <>
      <aside className="sidebar">
        <h3>Bölümler</h3>
        {sectionsLoading
          ? <div className="stack">{Array.from({ length: 10 }).map((_, i) =>
              <div key={i} className="skeleton" />)}</div>
          : <SectionTree nodes={sections} selected={route.section ?? null}
                         totalCases={treeTotal}
                         onSelect={(id) => {
                           location.hash = href({
                             page: 'suites', project: route.project,
                             suite: route.suite, section: id ?? undefined,
                           })
                         }} />}
      </aside>

      <main className="main">
        {/* inside a section the suite itself becomes a parent, and the
            open section is the one highlighted in the tree beside this */}
        <Crumbs projectId={route.project} projectName={projectName} trail={[
          { label: 'Test Suite’leri', href: href({ page: 'suites', project: route.project }) },
          ...(route.section && suite ? [{ label: suite.name,
            href: href({ page: 'suites', project: route.project, suite: suite.id }) }] : []),
        ]} />

        <div className="page-title">
          <span className="idbadge">S{route.suite}</span>
          <h1>{suite?.name ?? 'Suite'}</h1>
          <span className="faint small">
            {isFetching ? 'yükleniyor…' : `${total.toLocaleString('tr-TR')} case`}
          </span>
          <div className="right">
            <button className="ghost" onClick={exportCsv} title="CSV indir">
              <Icon name="download" size={14} /> CSV
            </button>
            <button className="ghost" onClick={() => setImporting(true)}>
              <Icon name="upload" size={14} /> İçe aktar
            </button>
            <button onClick={() => setAddingRun(true)}>
              <Icon name="play" size={12} /> Koşum başlat
            </button>
            <button className="primary" onClick={() => setAddingCase(true)}>
              <Icon name="plus" size={14} /> Case ekle
            </button>
            <MoreMenu items={[
              { label: 'Suite adını değiştir', icon: 'edit', onClick: () => {
                  setRenameText(suite?.name ?? ''); setRenaming('suite') } },
              { label: 'Suite’i sil', icon: 'trash', danger: true,
                onClick: () => setDeleting('suite') },
            ]} />
          </div>
        </div>

        <AddCaseDialog open={addingCase} onClose={() => setAddingCase(false)}
                       suiteId={route.suite} sectionId={route.section}
                       projectId={route.project} />
        <AddRunDialog open={addingRun} onClose={() => setAddingRun(false)}
                      projectId={route.project} defaultSuiteId={route.suite} />
        <ImportDialog open={importing} onClose={() => setImporting(false)}
                      suiteId={route.suite} sectionId={route.section} />

        {/* Section actions live here rather than in the tree: a row that
            sprouts three buttons on hover is unusable at 909 sections. */}
        {route.section != null && sectionIndex.get(route.section) && (
          <div className="toolbar" style={{ marginBottom: 10 }}>
            <Icon name="folder" size={14} />
            <b className="nowrap">{sectionIndex.get(route.section)!.name}</b>
            <span className="faint small grow">seçili bölüm</span>
            <button className="ghost small"
                    onClick={() => {
                      setRenameText(sectionIndex.get(route.section!)!.name)
                      setRenaming('section')
                    }}>
              <Icon name="edit" size={13} /> Yeniden adlandır
            </button>
            <button className="ghost small"
                    onClick={() => { setMoveParent(''); setMovingSection(true) }}>
              <Icon name="folder" size={13} /> Taşı
            </button>
            <button className="ghost small danger"
                    onClick={() => setDeleting('section')}>
              <Icon name="trash" size={13} /> Bölümü sil
            </button>
          </div>
        )}

        <Dialog open={renaming !== null}
                title={renaming === 'suite' ? 'Suite adı' : 'Bölüm adı'}
                onClose={() => setRenaming(null)}
                footer={<>
                  <button onClick={() => setRenaming(null)}>Vazgeç</button>
                  <button className="primary" disabled={!renameText}
                          onClick={() => {
                            if (renaming === 'suite' && route.suite) {
                              saveSuite.mutate(
                                { id: route.suite, patch: { name: renameText } },
                                { onSuccess: () => setRenaming(null) })
                            } else if (route.section) {
                              saveSection.mutate(
                                { id: route.section, patch: { name: renameText } },
                                { onSuccess: () => setRenaming(null) })
                            }
                          }}>
                    Kaydet
                  </button>
                </>}>
          <div className="field">
            <label>Ad</label>
            <input value={renameText} autoFocus
                   onChange={(e) => setRenameText(e.target.value)} />
          </div>
        </Dialog>

        <Dialog open={movingSection} title="Bölümü taşı"
                onClose={() => setMovingSection(false)}
                footer={<>
                  <button onClick={() => setMovingSection(false)}>Vazgeç</button>
                  <button className="primary" disabled={saveSection.isPending}
                          onClick={() => route.section && saveSection.mutate({
                            id: route.section,
                            patch: { parent_id: moveParent === '' ? null : moveParent },
                          }, { onSuccess: () => setMovingSection(false) })}>
                    Taşı
                  </button>
                </>}>
          <div className="field">
            <label>Üst bölüm</label>
            <select value={moveParent}
                    onChange={(e) => setMoveParent(
                      e.target.value === '' ? '' : Number(e.target.value))}>
              <option value="">— kök seviye —</option>
              {[...sectionIndex.entries()]
                .filter(([id]) => id !== route.section)
                .map(([id, info]) => (
                  <option key={id} value={id}>
                    {[info.path, info.name].filter(Boolean).join(' › ')}
                  </option>
                ))}
            </select>
            {saveSection.isError && (
              <div className="error" style={{ marginTop: 8 }}>
                {(saveSection.error as Error).message}
              </div>
            )}
          </div>
        </Dialog>

        <Confirm open={deleting === 'section'} title="Bölümü sil"
                 busy={removeSection.isPending}
                 error={removeSection.isError
                   ? (removeSection.error as Error).message : null}
                 detail={`"${route.section != null
                   ? sectionIndex.get(route.section)?.name ?? '' : ''}" bölümü,`
                   + ' alt bölümleri ve içindeki case’ler silinecek.'
                   + ' Case’ler silinmiş olarak işaretlenir; geçmiş koşumlardaki'
                   + ' sonuçları olduğu gibi kalır.'}
                 onClose={() => setDeleting(null)}
                 onConfirm={() => route.section && removeSection.mutate(
                   route.section, {
                     onSuccess: () => {
                       setDeleting(null)
                       location.hash = href({ page: 'suites', project: route.project,
                                              suite: route.suite })
                     },
                   })} />

        <Confirm open={deleting === 'suite'} title="Suite'i sil"
                 busy={deleteSuite.isPending}
                 error={deleteSuite.isError
                   ? (deleteSuite.error as Error).message : null}
                 detail={`"${suite?.name ?? ''}" suite'i silinecek.`
                   + ' Case ya da koşum içeren bir suite silinemez.'}
                 onClose={() => setDeleting(null)}
                 onConfirm={() => route.suite && deleteSuite.mutate(route.suite, {
                   onSuccess: () => {
                     setDeleting(null)
                     location.hash = href({ page: 'suites', project: route.project })
                   },
                 })} />

        <div className="toolbar">
          <input className="grow" placeholder="Başlıkta ara…" value={search}
                 onChange={(e) => setSearch(e.target.value)} />
          <button className={showFilters || filtersOn ? 'primary' : ''}
                  onClick={() => setShowFilters(!showFilters)}>
            <Icon name="filter" size={14} />
            Filtre{filtersOn ? ' •' : ''}
          </button>
          <select style={{ width: 155 }} value={sort}
                  onChange={(e) => { setSort(e.target.value); setPage(0) }}>
            <option value="section">Bölüme göre</option>
            <option value="title">Başlığa göre</option>
            <option value="updated">Son güncellenen</option>
            <option value="id">ID’ye göre</option>
          </select>
          <button className="ghost" disabled={page === 0} onClick={() => setPage(page - 1)}>
            <Icon name="chevron-left" size={14} /> Önceki
          </button>
          <span className="faint small nowrap">
            {total ? `${page * PAGE + 1}–${Math.min((page + 1) * PAGE, total)}` : '0'}
          </span>
          <button className="ghost" disabled={(page + 1) * PAGE >= total}
                  onClick={() => setPage(page + 1)}>
            Sonraki <Icon name="chevron-right" size={14} />
          </button>
        </div>

        {showFilters && (
          <div className="panel" style={{ padding: 16, marginBottom: 12 }}>
            <div className="row" style={{ gap: 14, flexWrap: 'wrap', alignItems: 'flex-end' }}>
              <div className="field" style={{ margin: 0, minWidth: 170 }}>
                <label>Tip</label>
                <select value={typeId}
                        onChange={(e) => { setTypeId(e.target.value === '' ? '' : Number(e.target.value)); setPage(0) }}>
                  <option value="">Hepsi</option>
                  {types.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
                </select>
              </div>
              <div className="field" style={{ margin: 0, minWidth: 170 }}>
                <label>Öncelik</label>
                <select value={priorityId}
                        onChange={(e) => { setPriorityId(e.target.value === '' ? '' : Number(e.target.value)); setPage(0) }}>
                  <option value="">Hepsi</option>
                  {priorities.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                </select>
              </div>
              <div className="field" style={{ margin: 0, minWidth: 210 }}>
                <label>Oluşturan</label>
                <select value={createdBy}
                        onChange={(e) => { setCreatedBy(e.target.value === '' ? '' : Number(e.target.value)); setPage(0) }}>
                  <option value="">Herkes</option>
                  {users.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
                </select>
              </div>
              {filtersOn && (
                <button className="ghost"
                        onClick={() => { setTypeId(''); setPriorityId(''); setCreatedBy(''); setPage(0) }}>
                  Filtreleri temizle
                </button>
              )}
              <button onClick={() => setSavingFilter(true)}>
                <Icon name="plus" size={13} /> Filtreyi kaydet
              </button>
            </div>

            {savedFilters.length > 0 && (
              <div style={{ marginTop: 14, paddingTop: 12,
                            borderTop: '1px solid var(--border)' }}>
                <div className="field" style={{ margin: 0 }}>
                  <label>Kayıtlı filtreler</label>
                  <div className="chiprow">
                    {savedFilters.map((f) => (
                      <span key={f.id} className="chip-toggle"
                            style={{ display: 'inline-flex', gap: 7, alignItems: 'center' }}>
                        <span style={{ cursor: 'pointer' }}
                              onClick={() => applySaved(f.criteria)}>
                          {f.name}{f.is_shared ? ' (paylaşık)' : ''}
                        </span>
                        {f.mine && (
                          <span style={{ cursor: 'pointer', opacity: 0.6 }}
                                onClick={() => deleteFilter.mutate(f.id)}>×</span>
                        )}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {savingFilter && (
          <div className="panel" style={{ padding: 14, marginBottom: 12 }}>
            <div className="row" style={{ gap: 10 }}>
              <input style={{ maxWidth: 280 }} autoFocus value={filterName}
                     placeholder="Filtre adı"
                     onChange={(e) => setFilterName(e.target.value)} />
              <button className="primary" disabled={!filterName || saveFilter.isPending}
                      onClick={() => saveFilter.mutate({
                        name: filterName, project_id: route.project,
                        suite_id: route.suite, criteria: currentCriteria(),
                        is_shared: true,
                      }, { onSuccess: () => { setFilterName(''); setSavingFilter(false) } })}>
                Kaydet
              </button>
              <button className="ghost" onClick={() => setSavingFilter(false)}>Vazgeç</button>
              <span className="faint small">Ekipteki herkes görebilir.</span>
            </div>
          </div>
        )}

        <div className="panel">
          {groups.length > 0 && (
            <div className="col-head">
              <span style={{ width: 34 }}>
                <input type="checkbox"
                       checked={picked.size > 0 && picked.size === rows.length}
                       onChange={(e) => setPicked(
                         e.target.checked ? new Set(rows.map((r) => r.id)) : new Set())} />
              </span>
              <span style={{ width: 86 }}>ID</span>
              <span style={{ flex: 1 }}>Başlık</span>
              <span style={{ width: 100 }}>Tip</span>
              <span style={{ width: 100 }}>Öncelik</span>
              <span style={{ width: 104 }}>Güncellendi</span>
            </div>
          )}
          {groups.length === 0 && (
            <div className="empty">
              <Icon name="list" size={30} />
              <b>Kayıt yok</b>
              {query || filtersOn
                ? 'Aramanız veya filtrelerinizle eşleşen case bulunamadı.'
                : 'Bu bölümde case yok.'}
            </div>
          )}

          {groups.map((group) => {
            const info = sectionIndex.get(group.sectionId)
            const isCollapsed = collapsed.has(group.sectionId)
            return (
              <div key={group.sectionId}>
                <div className="group-head" onClick={() => toggleGroup(group.sectionId)}>
                  <Icon name={isCollapsed ? 'chevron-right' : 'chevron-down'} size={13} />
                  <span className="name">{info?.name ?? `Bölüm ${group.sectionId}`}</span>
                  {info?.path && <span className="path">{info.path}</span>}
                  <span className="count">{group.rows.length}</span>
                </div>
                {!isCollapsed && (
                  <table className="grid">
                    <tbody>
                      {group.rows.map((row) => (
                        <tr key={row.id} className={picked.has(row.id) ? 'selected' : ''}>
                          <td style={{ width: 34 }} onClick={(e) => e.stopPropagation()}>
                            <input type="checkbox" checked={picked.has(row.id)}
                                   onChange={() => togglePick(row.id)} />
                          </td>
                          <td className="cid" style={{ width: 86 }}
                              onClick={() => openCase(row.id)}>C{row.id}</td>
                          <td className="title" onClick={() => openCase(row.id)}>{row.title}</td>
                          <td className="small muted" style={{ width: 100 }}
                              onClick={() => openCase(row.id)}>
                            {types.find((t) => t.id === row.type_id)?.name ?? '—'}
                          </td>
                          <td className="small muted" style={{ width: 100 }}
                              onClick={() => openCase(row.id)}>
                            {priorities.find((p) => p.id === row.priority_id)?.name ?? '—'}
                          </td>
                          <td className="small faint" style={{ width: 104 }}
                              onClick={() => openCase(row.id)}>
                            {row.updated_on
                              ? new Date(row.updated_on).toLocaleDateString('tr-TR')
                              : '—'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            )
          })}
        </div>

        {picked.size > 0 && (
          <div className="bulkbar">
            <b>{picked.size} case seçildi</b>
            <select style={{ width: 175 }} value=""
                    onChange={(e) => e.target.value && applyBulk({ type_id: Number(e.target.value) })}>
              <option value="">Tipi değiştir…</option>
              {types.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
            </select>
            <select style={{ width: 175 }} value=""
                    onChange={(e) => e.target.value && applyBulk({ priority_id: Number(e.target.value) })}>
              <option value="">Önceliği değiştir…</option>
              {priorities.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
            <select style={{ width: 210 }} value={moveTarget}
                    onChange={(e) => setMoveTarget(e.target.value === '' ? '' : Number(e.target.value))}>
              <option value="">Hedef bölüm…</option>
              {flatSections.map((s) => (
                <option key={s.id} value={s.id}>{s.label}</option>
              ))}
            </select>
            <button disabled={moveTarget === '' || copyMove.isPending}
                    onClick={() => copyMove.mutate(
                      { mode: 'copy', body: { case_ids: [...picked], section_id: moveTarget } },
                      { onSuccess: () => { setPicked(new Set()); setMoveTarget('') } })}>
              Kopyala
            </button>
            <button disabled={moveTarget === '' || copyMove.isPending}
                    onClick={() => copyMove.mutate(
                      { mode: 'move', body: { case_ids: [...picked], section_id: moveTarget } },
                      { onSuccess: () => { setPicked(new Set()); setMoveTarget('') } })}>
              Taşı
            </button>
            {(bulk.isPending || copyMove.isPending) &&
              <span className="faint small">kaydediliyor…</span>}
            <button className="ghost right" onClick={() => setPicked(new Set())}>
              Seçimi temizle
            </button>
          </div>
        )}
      </main>
    </>
  )
}
