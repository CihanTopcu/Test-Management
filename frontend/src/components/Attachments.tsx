import { useRef, useState } from 'react'
import { useAttachments, useDeleteAttachment, useUploadAttachment } from '../api/hooks'
import { Icon } from './Icon'

/**
 * Attachment strip: list, drop-to-upload, remove.
 *
 * The 491 files that came over from TestRail are read-only history -- the
 * backend refuses to delete anything whose id it did not mint -- so the
 * delete button only shows up on files uploaded here.
 */

function human(size: number) {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(0)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

const IMAGE = /^image\//

export function Attachments({ entityType, entityId, projectId, canEdit = true }: {
  entityType: 'case' | 'result' | 'test' | 'run' | 'plan'
  entityId?: number | null
  projectId?: number
  canEdit?: boolean
}) {
  const { data: files = [] } = useAttachments(entityType, entityId)
  const upload = useUploadAttachment(entityType, entityId, projectId)
  const remove = useDeleteAttachment(entityType, entityId)
  const input = useRef<HTMLInputElement>(null)
  const [over, setOver] = useState(false)
  const [preview, setPreview] = useState<string | null>(null)

  const send = (list: FileList | null) => {
    if (!list) return
    for (const file of Array.from(list)) upload.mutate(file)
  }

  return (
    <div>
      <div className="attachrow">
        {files.map((f) => (
          <div className="attachcard" key={f.id}>
            {IMAGE.test(f.content_type ?? '') ? (
              <img src={f.url} alt={f.filename} loading="lazy"
                   onClick={() => setPreview(f.url)} />
            ) : (
              <div className="filetile"><Icon name="file" size={22} /></div>
            )}
            <div className="meta">
              <a href={f.url} target="_blank" rel="noreferrer" title={f.filename}>
                {f.filename}
              </a>
              <span className="faint small">{human(f.size)}</span>
            </div>
            {canEdit && f.id.startsWith('u') && (
              <button className="ghost danger icon-only" title="Eki sil"
                      onClick={() => remove.mutate(f.id)}>
                <Icon name="trash" size={13} />
              </button>
            )}
          </div>
        ))}
        {files.length === 0 && !canEdit && (
          <span className="faint small">Ek yok.</span>
        )}
      </div>

      {canEdit && (
        <div className={`dropzone ${over ? 'over' : ''}`}
             onDragOver={(e) => { e.preventDefault(); setOver(true) }}
             onDragLeave={() => setOver(false)}
             onDrop={(e) => {
               e.preventDefault(); setOver(false); send(e.dataTransfer.files)
             }}
             onClick={() => input.current?.click()}>
          <Icon name="upload" size={15} />
          {upload.isPending ? 'Yükleniyor…' : 'Dosya sürükleyin ya da seçmek için tıklayın'}
          <input ref={input} type="file" multiple hidden
                 onChange={(e) => { send(e.target.files); e.target.value = '' }} />
        </div>
      )}
      {upload.isError && (
        <div className="error small" style={{ marginTop: 6 }}>
          {(upload.error as Error).message}
        </div>
      )}

      {preview && (
        <div className="lightbox" onClick={() => setPreview(null)}>
          <img src={preview} alt="" />
        </div>
      )}
    </div>
  )
}
