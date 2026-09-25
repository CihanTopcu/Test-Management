import { Fragment } from 'react'
import { useJiraConfig, useJiraIssues } from '../api/hooks'
import type { JiraIssue } from '../api/types'

/** PROJECT-123, as the server recognises it. */
const KEY = /\b([A-Z][A-Z0-9]{1,9}-\d{1,7})\b/g
/** https://…/browse/PROJECT-123, possibly with a query or fragment after it */
const BROWSE = /https?:\/\/\S+?\/browse\/([A-Z][A-Z0-9]{1,9}-\d{1,7})\S*/g

export function issueKeys(text: string | null | undefined): string[] {
  return [...new Set((text ?? '').match(KEY) ?? [])]
}

const CATEGORY_LABEL: Record<string, string> = {
  new: 'açık', indeterminate: 'devam ediyor', done: 'bitti',
}

/**
 * Text with Jira keys in it -- a case's references, a result's defects --
 * with each key turned into a link and its live status beside it.
 *
 * Pass `issues` when a list renders many of these, so the page asks Jira
 * once for every key on it; without it the component asks for its own.
 * With Jira not configured it is just the text.
 */
export function IssueRefs({ text, issues, compact = false }: {
  text: string | null | undefined
  issues?: Record<string, JiraIssue>
  /** key and a status dot only, for dense tables; status in the tooltip */
  compact?: boolean
}) {
  const { data: config } = useJiraConfig()
  const own = useJiraIssues(issues ? [] : issueKeys(text))
  const found = issues ?? own.data ?? {}
  if (!text) return null
  if (!config?.enabled) return <>{text}</>

  // some defects were entered as the whole browser address; the key is
  // what matters, and the link below points back to the same page
  const parts = text.replace(BROWSE, '$1').split(KEY)
  return (
    <span className="issuerefs">
      {parts.map((part, i) => {
        // split() with a capturing group puts the keys at odd positions
        if (i % 2 === 0) return <Fragment key={i}>{part}</Fragment>
        const issue = found[part]
        const title = !issue ? `${part} · Jira'dan okunuyor`
          : issue.missing ? `${part} · Jira'da bulunamadı ya da bu hesapla görülemiyor`
          : `${part} · ${issue.status} · ${issue.type}\n${issue.summary ?? ''}`
        return (
          <a key={i} className={`issue ${issue?.category ?? (issue?.missing ? 'missing' : 'loading')}`}
             href={issue?.url ?? `${config.base_url}/browse/${part}`}
             target="_blank" rel="noreferrer" title={title}
             onClick={(e) => e.stopPropagation()}>
            <i aria-hidden="true" />
            {part}
            {!compact && issue && !issue.missing && (
              <span className="st">{issue.status ?? CATEGORY_LABEL[issue.category ?? ''] ?? ''}</span>
            )}
          </a>
        )
      })}
    </span>
  )
}
