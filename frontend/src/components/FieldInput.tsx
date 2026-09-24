import type { Catalog, CustomField, User } from '../api/types'
import { RichText } from './RichText'

/**
 * One editor per custom field type, chosen from the catalog at runtime.
 *
 * This instance has 23 custom case fields and an admin can add another
 * without a deploy. A hand-written form would be out of date the first time
 * somebody adds a dropdown, so the form is generated from the same field
 * definitions the read-only view uses.
 */

export function isEmptyValue(v: unknown) {
  return v === null || v === undefined || v === '' ||
    (Array.isArray(v) && v.length === 0) ||
    // TestRail writes 0 into a dropdown that was never set
    v === 0 || v === '0'
}

export function optionsFor(catalog: Catalog, field: CustomField) {
  return catalog.field_options[field.system_name] ?? []
}

export function labelFor(catalog: Catalog, field: CustomField, value: unknown) {
  const options = optionsFor(catalog, field)
  const hit = options.find((o) => String(o.value) === String(value))
  if (hit) return hit.label
  // an option deleted in TestRail leaves the value behind; say so rather
  // than printing a bare number
  return options.length ? `#${value} (tanımsız seçenek)` : String(value)
}

export function FieldInput({ field, value, onChange, catalog, users }: {
  field: CustomField
  value: unknown
  onChange: (value: unknown) => void
  catalog: Catalog
  users: User[]
}) {
  const options = optionsFor(catalog, field)

  switch (field.field_type) {
    case 'text':
      return (
        <textarea rows={4} value={(value as string) ?? ''}
                  onChange={(e) => onChange(e.target.value || null)} />
      )

    case 'dropdown':
      return (
        <select value={(value as string | number) ?? ''}
                onChange={(e) => onChange(e.target.value === ''
                  ? null : Number(e.target.value))}>
          <option value="">— seçilmedi —</option>
          {options.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
      )

    case 'multiselect': {
      const picked = (Array.isArray(value) ? value : []).map(String)
      return (
        <div className="chiprow">
          {options.map((o) => {
            const on = picked.includes(String(o.value))
            return (
              <button key={o.value} type="button"
                      className={`chip-toggle ${on ? 'on' : ''}`}
                      onClick={() => onChange(
                        on ? picked.filter((v) => v !== String(o.value)).map(Number)
                           : [...picked.map(Number), o.value])}>
                {o.label}
              </button>
            )
          })}
          {options.length === 0 && <span className="faint small">seçenek yok</span>}
        </div>
      )
    }

    case 'checkbox':
      return (
        <label className="row small" style={{ gap: 8 }}>
          <input type="checkbox" checked={Boolean(value)}
                 onChange={(e) => onChange(e.target.checked)} />
          {field.label}
        </label>
      )

    case 'user':
      return (
        <select value={(value as number) ?? ''}
                onChange={(e) => onChange(e.target.value === ''
                  ? null : Number(e.target.value))}>
          <option value="">— seçilmedi —</option>
          {users.filter((u) => u.is_active).map((u) => (
            <option key={u.id} value={u.id}>{u.name}</option>
          ))}
        </select>
      )

    case 'date':
      return (
        <input type="date"
               value={value ? String(value).slice(0, 10) : ''}
               onChange={(e) => onChange(e.target.value || null)} />
      )

    case 'integer':
      return (
        <input type="number" value={(value as number) ?? ''}
               onChange={(e) => onChange(e.target.value === ''
                 ? null : Number(e.target.value))} />
      )

    case 'url':
      return (
        <input type="url" placeholder="https://…" value={(value as string) ?? ''}
               onChange={(e) => onChange(e.target.value || null)} />
      )

    default:
      return (
        <input value={(value as string) ?? ''}
               onChange={(e) => onChange(e.target.value || null)} />
      )
  }
}

/** Read-only rendering of the same value. */
export function FieldValue({ field, value, catalog, users }: {
  field: CustomField
  value: unknown
  catalog: Catalog
  users: User[]
}) {
  if (isEmptyValue(value)) return <span className="faint">None</span>
  switch (field.field_type) {
    case 'text':
      return <RichText value={String(value)} />
    case 'dropdown':
      return <span>{labelFor(catalog, field, value)}</span>
    case 'multiselect':
      return <>{(Array.isArray(value) ? value : [value]).map((v, i) => (
        <span key={i} className="badge soft" style={{ marginRight: 4 }}>
          {labelFor(catalog, field, v)}
        </span>
      ))}</>
    case 'checkbox':
      return <span>{value ? 'Evet' : 'Hayır'}</span>
    case 'user':
      return <span>{users.find((u) => u.id === Number(value))?.name ?? `#${value}`}</span>
    case 'date':
      return <span>{new Date(String(value)).toLocaleDateString('tr-TR')}</span>
    case 'url':
      return <a href={String(value)} target="_blank" rel="noreferrer">{String(value)}</a>
    default:
      return <span>{String(value)}</span>
  }
}

/** Which fields belong to this project, in display order. */
export function scopedFields(catalog: Catalog, projectId?: number,
                             entity: 'case' | 'result' = 'case') {
  const all = entity === 'case' ? catalog.case_fields : catalog.result_fields
  return all
    .filter((f) => {
      if (['steps', 'step_results', 'bdd', 'bdd_results'].includes(f.field_type)) {
        return false
      }
      if (!projectId) return f.is_global
      return (f.configs ?? []).some((c) => {
        const ctx = c.context ?? {}
        return ctx.is_global || (ctx.project_ids ?? []).includes(projectId)
      })
    })
    .sort((a, b) => a.display_order - b.display_order)
}
