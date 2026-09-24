import { Icon } from './Icon'

export interface StepDraft {
  content: string
  expected: string
}

/** Step list editor, shared by the create dialog and the case page. */
export function StepsEditor({ steps, onChange }: {
  steps: StepDraft[]
  onChange: (steps: StepDraft[]) => void
}) {
  const update = (i: number, patch: Partial<StepDraft>) =>
    onChange(steps.map((s, j) => (j === i ? { ...s, ...patch } : s)))

  const move = (i: number, delta: number) => {
    const target = i + delta
    if (target < 0 || target >= steps.length) return
    const next = [...steps]
    ;[next[i], next[target]] = [next[target], next[i]]
    onChange(next)
  }

  return (
    <div>
      {steps.map((step, i) => (
        <div className="steprow" key={i} style={{ marginBottom: 8 }}>
          <div className="num" style={{ display: 'flex', flexDirection: 'column',
                                        alignItems: 'center', gap: 2 }}>
            <span>{i + 1}</span>
            <button type="button" className="ghost icon-only" title="Yukarı taşı"
                    style={{ padding: 2 }} disabled={i === 0}
                    onClick={() => move(i, -1)}>
              <Icon name="chevron-up" size={12} />
            </button>
            <button type="button" className="ghost icon-only" title="Aşağı taşı"
                    style={{ padding: 2 }} disabled={i === steps.length - 1}
                    onClick={() => move(i, 1)}>
              <Icon name="chevron-down" size={12} />
            </button>
          </div>
          <textarea rows={3} placeholder="Adım" value={step.content}
                    onChange={(e) => update(i, { content: e.target.value })} />
          <div>
            <textarea rows={3} placeholder="Beklenen sonuç" value={step.expected}
                      onChange={(e) => update(i, { expected: e.target.value })} />
            <button type="button" className="ghost danger small"
                    style={{ marginTop: 4 }}
                    onClick={() => onChange(steps.filter((_, j) => j !== i))}>
              <Icon name="trash" size={12} /> Adımı sil
            </button>
          </div>
        </div>
      ))}
      <button type="button"
              onClick={() => onChange([...steps, { content: '', expected: '' }])}>
        <Icon name="plus" size={13} /> Adım ekle
      </button>
    </div>
  )
}
