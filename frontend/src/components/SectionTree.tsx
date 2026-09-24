import { useState } from 'react'
import { Icon } from './Icon'
import type { SectionNode } from '../api/types'

interface Props {
  nodes: SectionNode[]
  selected: number | null
  onSelect: (id: number | null) => void
  totalCases: number
}

function Node({ node, depth, selected, onSelect }: {
  node: SectionNode
  depth: number
  selected: number | null
  onSelect: (id: number) => void
}) {
  // deep trees here run to hundreds of folders, so start collapsed below the
  // first level and let people open what they need
  const [open, setOpen] = useState(depth < 1)
  const hasChildren = node.children.length > 0

  return (
    <div>
      <div
        className={`tree-item ${selected === node.id ? 'active' : ''}`}
        style={{ paddingLeft: 6 + depth * 12 }}
        onClick={() => onSelect(node.id)}
      >
        <span
          className="twisty"
          onClick={(e) => { e.stopPropagation(); if (hasChildren) setOpen(!open) }}
        >
          {hasChildren && <Icon name={open ? 'chevron-down' : 'chevron-right'} size={13} />}
        </span>
        <span className="label" title={node.name}>{node.name}</span>
        {node.case_count > 0 && <span className="count">{node.case_count}</span>}
      </div>
      {open && node.children.map((child) => (
        <Node key={child.id} node={child} depth={depth + 1}
              selected={selected} onSelect={onSelect} />
      ))}
    </div>
  )
}

export function SectionTree({ nodes, selected, onSelect, totalCases }: Props) {
  return (
    <div>
      <div
        className={`tree-item ${selected === null ? 'active' : ''}`}
        onClick={() => onSelect(null)}
      >
        <span className="twisty" />
        <span className="label"><b>Tüm case'ler</b></span>
        <span className="count">{totalCases}</span>
      </div>
      {nodes.map((node) => (
        <Node key={node.id} node={node} depth={0}
              selected={selected} onSelect={onSelect} />
      ))}
    </div>
  )
}
