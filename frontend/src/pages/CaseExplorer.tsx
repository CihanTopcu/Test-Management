import { useMemo } from 'react'
import { useCaseExplorer, useCatalog, useSuites } from '../api/hooks'
import { Icon } from '../components/Icon'
import { href, type Route } from '../route'

/**
 * The case library across a whole project, filtered.
 *
 * Every number on the reports page used to be a dead end. You could read
 * that a third of the library has never been run, or that 11% of it is
 * linked to a requirement, and there was no way to see which third or which
 * 11% -- cases live under suites, so the only case list was suite-scoped.
 *
 * The filters live in the address, which is what lets a chart link here and
 * a person paste the result into Jira.
 */

const REFS: Record<string, string> = {
  with: 'gereksinime bağlı', without: 'gereksinimsiz',
}
const EXECUTED: Record<string, string> = {
  yes: 'en az bir kez koşulmuş', no: 'hiç koşulmamış',
}
const SORTS: Record<string, string> = {
  title: 'başlık', runs: 'en çok koşulan', updated: 'son değişen', id: 'id',
}

export function CaseExplorer({ route, projectName }: {
  route: Route; projectName: string
}) {
  const { data: catalog } = useCatalog()
  const { data: suites = [] } = useSuites(route.project)
  const filters = route.filters ?? {}

  const params = useMemo(
    () => ({ limit: '100', sort: 'title', ...filters }), [filters])
  const { data, isLoading, isFetching } = useCaseExplorer(route.project, params)

  const go = (patch: Record<string, string | undefined>) => {
    const next: Record<string, string> = { ...filters }
    for (const [k, v] of Object.entries(patch)) {
      if (v === undefined || v === '') delete next[k]
      else next[k] = v
    }
    // any change to what is being asked invalidates where you were in it
    if (!('offset' in patch)) delete next.offset
    location.hash = href({ ...route, filters: next })
  }

  const offset = Number(filters.offset ?? 0)
  const total = data?.total ?? 0
  const typeName = (id: number | null) =>
    catalog?.case_types.find((t) => t.id === id)?.name
  const priorityName = (id: number | null) =>
    catalog?.priorities.find((p) => p.id === id)?.name

  // what the current filter actually says, in words, so a link arriving from
  // a chart explains itself
  const chips = [
    filters.suite_id && {
      k: 'suite_id',
      t: suites.find((s) => s.id === Number(filters.suite_id))?.name
        ?? `Suite ${filters.suite_id}`,
    },
    filters.type_id && {
      k: 'type_id', t: typeName(Number(filters.type_id)) ?? 'Tip' },
    filters.priority_id && {
      k: 'priority_id',
      t: priorityName(Number(filters.priority_id)) ?? 'Öncelik' },
    filters.refs && { k: 'refs', t: REFS[filters.refs] },
    filters.executed && { k: 'executed', t: EXECUTED[filters.executed] },
    filters.q && { k: 'q', t: `“${filters.q}”` },
  ].filter(Boolean) as { k: string; t: string }[]

  return (
    <main className="main explorer">
      <div className="crumbs">
        <a href={href({ page: 'reports', project: route.project })}>{projectName}</a>
        {' › '}<b>Case gezgini</b>
      </div>
      <div className="page-title">
        <h1>Case&apos;ler</h1>
        <span className="faint small">
          {isLoading ? 'yükleniyor…' : `${total.toLocaleString('tr-TR')} case`}
          {isFetching && !isLoading && ' · yenileniyor'}
        </span>
      </div>

      <div className="panel explorer-bar">
        <input className="grow" placeholder="Başlıkta ara…"
               defaultValue={filters.q ?? ''}
               onKeyDown={(e) => {
                 if (e.key === 'Enter') go({ q: e.currentTarget.value })
               }} />

        <select value={filters.suite_id ?? ''}
                onChange={(e) => go({ suite_id: e.target.value })}>
          <option value="">Tüm suite&apos;ler</option>
          {suites.map((s) => (
            <option key={s.id} value={s.id}>{s.name}</option>
          ))}
        </select>

        <select value={filters.type_id ?? ''}
                onChange={(e) => go({ type_id: e.target.value })}>
          <option value="">Tüm tipler</option>
          {(catalog?.case_types ?? []).map((t) => (
            <option key={t.id} value={t.id}>{t.name}</option>
          ))}
        </select>

        <select value={filters.priority_id ?? ''}
                onChange={(e) => go({ priority_id: e.target.value })}>
          <option value="">Tüm öncelikler</option>
          {(catalog?.priorities ?? []).map((p) => (
            <option key={p.id} value={p.id}>{p.name}</option>
          ))}
        </select>

        <select value={filters.executed ?? ''}
                onChange={(e) => go({ executed: e.target.value })}>
          <option value="">Koşum farketmez</option>
          <option value="no">Hiç koşulmamış</option>
          <option value="yes">En az bir kez koşulmuş</option>
        </select>

        <select value={filters.refs ?? ''}
                onChange={(e) => go({ refs: e.target.value })}>
          <option value="">Gereksinim farketmez</option>
          <option value="without">Gereksinimsiz</option>
          <option value="with">Gereksinime bağlı</option>
        </select>

        <select value={filters.sort ?? 'title'}
                onChange={(e) => go({ sort: e.target.value })}>
          {Object.entries(SORTS).map(([k, label]) => (
            <option key={k} value={k}>{label}</option>
          ))}
        </select>
      </div>

      {chips.length > 0 && (
        <div className="chiprow" style={{ margin: '10px 0' }}>
          {chips.map((c) => (
            <button key={c.k} className="chip-toggle on"
                    onClick={() => go({ [c.k]: undefined })}>
              {c.t} <Icon name="close" size={11} />
            </button>
          ))}
          <button className="chip-toggle"
                  onClick={() => { location.hash = href({ ...route, filters: {} }) }}>
            filtreleri temizle
          </button>
        </div>
      )}

      <div className="panel" style={{ overflow: 'auto' }}>
        <table className="explorer-table">
          <thead>
            <tr>
              <th style={{ width: 92 }}>ID</th>
              <th>Başlık</th>
              <th style={{ width: 200 }}>Suite</th>
              <th style={{ width: 110 }}>Tip</th>
              <th style={{ width: 96 }}>Öncelik</th>
              <th style={{ width: 130 }}>Gereksinim</th>
              <th style={{ width: 80, textAlign: 'right' }}>Koşum</th>
            </tr>
          </thead>
          <tbody>
            {(data?.items ?? []).map((c) => (
              <tr key={c.id} onClick={() => {
                location.hash = href({ page: 'cases', project: route.project,
                                       case: c.id })
              }}>
                <td className="cid">C{c.id}</td>
                <td className="title">{c.title}</td>
                <td className="small muted">{c.suite_name}</td>
                <td className="small muted">{typeName(c.type_id) ?? '—'}</td>
                <td className="small muted">{priorityName(c.priority_id) ?? '—'}</td>
                <td className="small">
                  {c.refs
                    ? <span className="ref">{c.refs}</span>
                    : <span className="faint">—</span>}
                </td>
                <td style={{ textAlign: 'right' }}>
                  {c.runs === 0
                    ? <span className="faint small">hiç</span>
                    : <b>{c.runs}</b>}
                </td>
              </tr>
            ))}
            {!isLoading && !data?.items.length && (
              <tr><td colSpan={7} className="faint">
                Bu filtreyle case yok.
              </td></tr>
            )}
          </tbody>
        </table>
      </div>

      {total > 100 && (
        <div className="row small" style={{ marginTop: 10, gap: 10 }}>
          <button disabled={offset === 0}
                  onClick={() => go({ offset: String(Math.max(0, offset - 100)) })}>
            ‹ Önceki
          </button>
          <span className="faint">
            {(offset + 1).toLocaleString('tr-TR')}–
            {Math.min(offset + 100, total).toLocaleString('tr-TR')}
            {' / '}{total.toLocaleString('tr-TR')}
          </span>
          <button disabled={offset + 100 >= total}
                  onClick={() => go({ offset: String(offset + 100) })}>
            Sonraki ›
          </button>
        </div>
      )}
    </main>
  )
}
