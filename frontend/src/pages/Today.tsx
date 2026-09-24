import { useMe, useToday } from '../api/hooks'
import { Icon } from '../components/Icon'
import { projectColor } from '../projectColor'
import { href } from '../route'

/**
 * The front door.
 *
 * The application used to open on project statistics, which tell you how
 * things are but never what to do. This answers the other question, and it
 * is the one somebody opening a test tool in the morning actually has.
 *
 * The sections follow how this team works rather than how a test tool
 * usually assumes people work. Nobody here assigns tests and runs are
 * opened by automation, so "assigned to you" and "runs you started" would
 * both be empty for everyone; what is live is automation posting results
 * and things breaking. Assignment is still here, but it is not the
 * headline, and when it is empty it says why.
 */

function greeting() {
  const hour = new Date().getHours()
  if (hour < 6) return 'İyi geceler'
  if (hour < 12) return 'Günaydın'
  if (hour < 18) return 'İyi günler'
  return 'İyi akşamlar'
}

function when(value: string) {
  const minutes = Math.round((Date.now() - new Date(value).getTime()) / 60000)
  if (minutes < 60) return `${minutes} dk önce`
  if (minutes < 60 * 24) return `${Math.round(minutes / 60)} saat önce`
  return `${Math.round(minutes / 1440)} gün önce`
}

function ProjectTag({ id, name }: { id: number; name: string }) {
  const colour = projectColor(id)
  return (
    <span className="ptag" style={{
      color: colour.ink, background: colour.soft,
    }}>{name}</span>
  )
}

export function Today() {
  const { data: me } = useMe()
  const { data, isLoading } = useToday()

  if (isLoading || !data) {
    return (
      <main className="main">
        <div className="stack">
          <div className="skeleton" style={{ width: 280, height: 30 }} />
          <div className="skeleton" style={{ width: '60%' }} />
        </div>
      </main>
    )
  }

  return (
    <main className="main today">
      <div className="today-head">
        <h1>{greeting()}, {(me?.name ?? '').split(' ')[0]}</h1>
        <span className="faint small">
          {new Date().toLocaleDateString('tr-TR', {
            weekday: 'long', day: 'numeric', month: 'long' })}
        </span>
      </div>

      {data.projects.length > 0 && (
        <div className="projstrip">
          {data.projects.map((p) => {
            const colour = projectColor(p.project_id)
            return (
              <a key={p.project_id} className="projcard"
                 href={href({ page: 'overview', project: p.project_id })}
                 style={{ '--project': colour.ink,
                          '--project-soft': colour.soft } as React.CSSProperties}>
                <span className="edge" />
                <span className="name">{p.name}</span>
                <span className="meta">
                  {p.cases.toLocaleString('tr-TR')} case
                  {p.open_runs > 0 && ` · ${p.open_runs} açık koşum`}
                </span>
              </a>
            )
          })}
        </div>
      )}

      <div className="today-grid">
        {/* ---- what broke ------------------------------------------- */}
        {data.failures.length > 0 && (
          <section className="today-card wide">
            <header>
              <span className="dot fail" />
              <h2>Dünden beri kırılanlar</h2>
              <b className="count">{data.failures_total}</b>
            </header>
            <div className="rows">
              {data.failures.map((f) => (
                <a key={`${f.test_id}-${f.at}`} className="row"
                   href={href({ page: 'runs', project: f.project_id,
                                run: f.run_id, test: f.test_id })}>
                  <ProjectTag id={f.project_id} name={f.project_name} />
                  <span className="title">{f.title}</span>
                  <span className="meta">{f.run_name}</span>
                  <span className="when">{when(f.at)}</span>
                </a>
              ))}
            </div>
          </section>
        )}

        {/* ---- runs that moved -------------------------------------- */}
        {data.my_runs.length > 0 && (
          <section className="today-card wide">
            <header>
              <span className="dot run" />
              <h2>Son hareket eden koşumlar</h2>
            </header>
            <div className="rows">
              {data.my_runs.map((r) => (
                <a key={r.run_id} className="row"
                   href={href({ page: 'runs', project: r.project_id,
                                run: r.run_id })}>
                  <ProjectTag id={r.project_id} name={r.project_name} />
                  <span className="title">{r.run_name}</span>
                  <span className="runbar"
                        title={`${r.passed} passed · ${r.failed} failed`
                               + (r.other ? ` · ${r.other} diğer` : '')
                               + ` · ${r.untested} untested`}>
                    <span style={{ width: `${100 * r.passed / (r.total || 1)}%`,
                                   background: 'var(--passed)' }} />
                    <span style={{ width: `${100 * r.failed / (r.total || 1)}%`,
                                   background: 'var(--failed)' }} />
                    {/* deferred, blocked, retouch: entered, but not a failure */}
                    <span style={{ width: `${100 * r.other / (r.total || 1)}%`,
                                   background: 'var(--warn)' }} />
                  </span>
                  <span className="when">
                    {r.is_completed ? 'tamamlandı' : `%${r.percent}`}
                    {r.last_result_on && (
                      <span className="faint"> · {when(r.last_result_on)}</span>
                    )}
                  </span>
                </a>
              ))}
            </div>
          </section>
        )}

        {/* ---- assigned to me --------------------------------------- */}
        <section className="today-card">
          <header>
            <span className="dot mine" />
            <h2>Size atananlar</h2>
            {data.assigned_total > 0 && (
              <b className="count">{data.assigned_total}</b>
            )}
          </header>
          {data.assigned.length === 0 ? (
            <p className="hint">
              {data.assignment_in_use
                ? 'Size atanmış, sonuç bekleyen test yok.'
                : 'Bu instance’ta test ataması kullanılmıyor. Bir koşumu '
                  + 'açıp testi birine atadığınızda burada görünür.'}
            </p>
          ) : (
            <div className="rows">
              {data.assigned.map((a) => (
                <a key={a.run_id} className="row"
                   href={href({ page: 'runs', project: a.project_id,
                                run: a.run_id })}>
                  <ProjectTag id={a.project_id} name={a.project_name} />
                  <span className="title">{a.run_name}</span>
                  <span className="when">{a.pending} test</span>
                </a>
              ))}
            </div>
          )}
        </section>

        {/* ---- milestones ------------------------------------------- */}
        <section className="today-card">
          <header>
            <span className="dot ms" />
            <h2>Yaklaşan milestone’lar</h2>
          </header>
          {data.milestones.length === 0 ? (
            <p className="hint">Önümüzdeki hafta dolan milestone yok.</p>
          ) : (
            <div className="rows">
              {data.milestones.map((m) => (
                <a key={m.milestone_id} className="row"
                   href={href({ page: 'milestones', project: m.project_id,
                                milestone: m.milestone_id })}>
                  <ProjectTag id={m.project_id} name={m.project_name} />
                  <span className="title">{m.name}</span>
                  <span className={`when ${m.days < 0 ? 'late' : ''}`}>
                    {m.days < 0 ? `${-m.days} gün geçti` : `${m.days} gün`}
                  </span>
                </a>
              ))}
            </div>
          )}
        </section>
      </div>

      <div className="faint small" style={{ marginTop: 16 }}>
        <Icon name="clock" size={12} />{' '}
        {data.scoped_to_memberships
          ? 'Yalnızca üye olduğunuz projeler gösteriliyor.'
          : 'Hiçbir projeye üye olmadığınız için tüm projeler gösteriliyor.'}
      </div>
    </main>
  )
}
