/**
 * Kanıt — the brand mark.
 *
 * A check that breaks out of its box. The record is the square; the proof is
 * the stroke that does not stay inside it. The gap in the top-right corner
 * is the whole mark: without it this is the verified badge every second
 * application ships.
 *
 * Built from strokes rather than filled shapes so it survives 16px in a
 * browser tab, where the gap closes up and it simply reads as a tick in a
 * rounded square -- which is the right thing to degrade into.
 */

export function LogoMark({ size = 24, tile = false, className = '' }: {
  size?: number
  /** Draw the rounded square behind the mark. */
  tile?: boolean
  className?: string
}) {
  // the stroke thins as the mark grows, so a 96px logo does not look clubbed
  const stroke = size <= 20 ? 2.4 : size <= 40 ? 2.1 : 1.8
  return (
    <svg className={className} width={size} height={size} viewBox="0 0 24 24"
         fill="none" aria-hidden="true">
      {tile && (
        <rect x="0" y="0" width="24" height="24" rx="6.5"
              fill="currentColor" opacity="0.1" />
      )}
      <g stroke="currentColor" strokeWidth={stroke} strokeLinecap="round"
         strokeLinejoin="round">
        {/* the box, drawn with the top-right corner left open */}
        <path d="M16 3.6H8A4.4 4.4 0 0 0 3.6 8v8A4.4 4.4 0 0 0 8 20.4h8
                 A4.4 4.4 0 0 0 20.4 16v-3" />
        {/* the proof, leaving through the gap */}
        <path d="M7.8 12.4 11 15.6 21 4.8" />
      </g>
    </svg>
  )
}

/** Mark plus wordmark, for the masthead and the sign-in page. */
export function Logo({ size = 22, subtitle = true, className = '' }: {
  size?: number
  subtitle?: boolean
  className?: string
}) {
  return (
    <span className={`logotype ${className}`}>
      <LogoMark size={size} />
      <span className="word" style={{ fontSize: size * 0.82 }}>Kanıt</span>
      {subtitle && <small>DGPays</small>}
    </span>
  )
}
