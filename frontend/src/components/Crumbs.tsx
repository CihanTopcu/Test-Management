import type { ReactNode } from 'react'
import { href } from '../route'
import { Icon } from './Icon'

/**
 * The trail above a page title: the project, then the pages above this one.
 *
 * One rule everywhere, because each screen used to invent its own -- some had
 * no trail, some a bare project name, some repeated the title below them.
 * The project is always a link to its overview, and the current page is
 * never in the trail: the heading right underneath already says where you
 * are.
 */
export function Crumbs({ projectId, projectName, trail = [] }: {
  projectId?: number
  projectName: string
  trail?: { label: ReactNode; href: string }[]
}) {
  return (
    <nav className="crumbs" aria-label="Konum">
      <a className="proj" href={href({ page: 'overview', project: projectId })}>
        {projectName}
      </a>
      {trail.map((item, i) => (
        <span key={i} className="crumb-step">
          <Icon name="chevron-right" size={12} />
          <a href={item.href}>{item.label}</a>
        </span>
      ))}
    </nav>
  )
}
