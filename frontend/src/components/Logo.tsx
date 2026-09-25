import { useId } from 'react'

/**
 * DGTest — the DGPays mark with the product's own name beside it.
 *
 * The mark is the company's: a disc cut into four bands, the two middle
 * bands broken by a rounded gap, shaded from teal at the bottom left to blue
 * at the top right. It is drawn on a 48-unit square where the bands and the
 * gaps between them are all 48/7 tall, so it stays crisp at 16px in a tab.
 * favicon.svg carries the same geometry.
 */

const BAND = 48 / 7
const R = BAND / 2
// the top of each band: band, gap, band, gap, band, gap, band
const Y = [0, 2, 4, 6].map((i) => i * BAND)

export function LogoMark({ size = 24, className = '' }: {
  size?: number
  className?: string
}) {
  const id = useId().replace(/:/g, '')
  const fill = `url(#g${id})`
  // pieces run well past the disc so only their inner ends show as rounded;
  // the clip trims the outer ends to the circle
  const piece = (x1: number, x2: number, y: number) => (
    <rect x={x1} y={y} width={x2 - x1} height={BAND} rx={R} fill={fill} />
  )
  return (
    <svg className={className} width={size} height={size} viewBox="0 0 48 48"
         aria-hidden="true">
      <defs>
        <linearGradient id={`g${id}`} x1="0" y1="1" x2="1" y2="0">
          <stop offset="0" stopColor="#0ee6cf" />
          <stop offset="0.55" stopColor="#00a0ec" />
          <stop offset="1" stopColor="#0466ff" />
        </linearGradient>
        <clipPath id={`c${id}`}><circle cx="24" cy="24" r="24" /></clipPath>
      </defs>
      <g clipPath={`url(#c${id})`}>
        {piece(-20, 68, Y[0])}
        {piece(-20, 11.6, Y[1])}
        {piece(18.8, 68, Y[1])}
        {piece(-20, 29.5, Y[2])}
        {piece(36.4, 68, Y[2])}
        {piece(-20, 68, Y[3])}
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
      <span className="lockup">
        <span className="word" style={{ fontSize: size * 0.8 }}>
          DG<span className="grad">Test</span>
        </span>
        {subtitle && <small>Yazılım Test Yönetimi</small>}
      </span>
    </span>
  )
}
