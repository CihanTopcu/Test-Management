import { useMemo } from 'react'
import { Icon } from './Icon'

/**
 * Renders a rich-text field that came out of TestRail.
 *
 * Two formats are mixed in the imported data: HTML written by TestRail's
 * editor (`<p><img src="index.php?/attachments/get/2269">`) and markdown
 * typed by hand (`![](index.php?/attachments/get/...)`). Both appear inside
 * the same field set, sometimes in the same project, so both are handled.
 *
 * The HTML is sanitised rather than trusted. It is internal content, but it
 * was authored over years by many people and imported verbatim; injecting it
 * straight into the DOM would make any stored script in it our problem.
 */

const ALLOWED = new Set([
  'A', 'B', 'BR', 'CODE', 'DD', 'DIV', 'DL', 'DT', 'EM', 'H1', 'H2', 'H3',
  'H4', 'H5', 'H6', 'HR', 'I', 'IMG', 'LI', 'OL', 'P', 'PRE', 'S', 'SPAN',
  'STRONG', 'SUB', 'SUP', 'TABLE', 'TBODY', 'TD', 'TFOOT', 'TH', 'THEAD',
  'TR', 'U', 'UL',
])
const ALLOWED_ATTRS = new Set(['href', 'src', 'alt', 'title', 'colspan', 'rowspan'])

function sanitize(html: string): string {
  const doc = new DOMParser().parseFromString(html, 'text/html')
  const walk = (node: Element) => {
    for (const child of Array.from(node.children)) {
      if (!ALLOWED.has(child.tagName)) {
        child.replaceWith(...Array.from(child.childNodes))
        continue
      }
      for (const attr of Array.from(child.attributes)) {
        const name = attr.name.toLowerCase()
        const value = attr.value.trim().toLowerCase()
        if (!ALLOWED_ATTRS.has(name)) {
          child.removeAttribute(attr.name)
        } else if ((name === 'href' || name === 'src') &&
                   (value.startsWith('javascript:') || value.startsWith('data:text'))) {
          child.removeAttribute(attr.name)
        }
      }
      if (child.tagName === 'A') {
        child.setAttribute('target', '_blank')
        child.setAttribute('rel', 'noopener noreferrer')
      }
      walk(child)
    }
  }
  walk(doc.body)
  return doc.body.innerHTML
}

const MD_IMAGE = /!\[[^\]]*\]\(([^)\s]+)\)/g

function markdownToHtml(text: string): string {
  const escaped = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
  return escaped.replace(MD_IMAGE, (_m, url) => `<img src="${url}" alt="">`)
}

/** An attachment we could not rescue; say so instead of showing a broken icon. */
function MissingImage({ src }: { src: string }) {
  const id = src.split('/').pop()?.split('?')[0] ?? ''
  return (
    <span className="missing-img" title={`ek id: ${id}`}>
      <Icon name="warning" size={14} />
      Bu görsel TestRail'den alınamadı
    </span>
  )
}

export function RichText({ value, className = '' }: { value?: string | null; className?: string }) {
  const html = useMemo(() => {
    if (!value) return ''
    const looksLikeHtml = /<[a-z][\s\S]*>/i.test(value)
    return sanitize(looksLikeHtml ? value : markdownToHtml(value))
  }, [value])

  const missing = useMemo(
    () => (value ? Array.from(value.matchAll(/\/api\/attachments\/([\w-]+)\?missing=1/g)) : []),
    [value],
  )

  if (!value) return <span className="faint">—</span>

  // images we do not hold would render as a broken icon, so pull them out
  const cleaned = missing.length
    ? html.replace(/<img[^>]*missing=1[^>]*>/g, '')
    : html

  return (
    <div className={`rich ${className}`}>
      <div dangerouslySetInnerHTML={{ __html: cleaned }} />
      {missing.map((m, i) => (
        <MissingImage key={`${m[1]}-${i}`} src={m[0]} />
      ))}
    </div>
  )
}
