/**
 * A stable colour per project.
 *
 * With 16 projects and a rail that looks identical in all of them, the first
 * thing anyone loses is which one they are in. A colour fixes that faster
 * than any label: you learn "TRANSIT is the teal one" in a day and never
 * misread it again.
 *
 * Two rules this palette has to obey, and both of them constrain it hard:
 *
 *   Nothing may collide with a status. Green, red and amber mean passed,
 *   failed and retest everywhere in this application; a project wearing one
 *   of them would make a grid unreadable. So the hues skip those bands.
 *
 *   It must survive the dark theme. Each entry carries its own dark
 *   variant rather than being lightened programmatically, which turns muddy
 *   at the blue end.
 */

export interface ProjectColor {
  /** the identity colour itself */
  ink: string
  /** a wash for chips and active rows */
  soft: string
  /** the dark-theme pair */
  darkInk: string
  darkSoft: string
}

/* Hues deliberately drawn from the cyan → violet → magenta → brown arc,
   leaving 90°–150° (green) and 0°–30° (red) to the statuses. */
const PALETTE: ProjectColor[] = [
  { ink: '#00a9ce', soft: '#e3f7fc', darkInk: '#35c8e6', darkSoft: '#0b2e39' },
  { ink: '#3b6ef0', soft: '#e7edfe', darkInk: '#6d93f7', darkSoft: '#10203f' },
  { ink: '#7a5af0', soft: '#eee9fe', darkInk: '#a189f8', darkSoft: '#211a3e' },
  { ink: '#b44ddb', soft: '#f6e9fc', darkInk: '#cc82ea', darkSoft: '#2d1738' },
  { ink: '#d94b8f', soft: '#fce8f2', darkInk: '#ec83b4', darkSoft: '#361427' },
  { ink: '#0f8f86', soft: '#e0f4f2', darkInk: '#3cbdb2', darkSoft: '#0a2e2b' },
  { ink: '#8a6d3b', soft: '#f5eddd', darkInk: '#c4a068', darkSoft: '#2b2216' },
  { ink: '#5568a8', soft: '#eaeef8', darkInk: '#8b9ddb', darkSoft: '#181f36' },
  { ink: '#0076b6', soft: '#e2f0fa', darkInk: '#4aa8dd', darkSoft: '#08263a' },
  { ink: '#9c4f6c', soft: '#f8e9ee', darkInk: '#c98098', darkSoft: '#31161f' },
  { ink: '#4f7fa8', soft: '#e9f1f7', darkInk: '#7fb0d4', darkSoft: '#13252f' },
  { ink: '#6b3fa0', soft: '#eee7f8', darkInk: '#9c77d0', darkSoft: '#1f1533' },
  { ink: '#1a7f9e', soft: '#e1f2f7', darkInk: '#4fb4ce', darkSoft: '#0a2831' },
  { ink: '#a3547a', soft: '#f9eaf0', darkInk: '#cd88a6', darkSoft: '#321824' },
  { ink: '#3f6b8f', soft: '#e8eff5', darkInk: '#7aa3c4', darkSoft: '#11202b' },
  { ink: '#8455b8', soft: '#f0e9f9', darkInk: '#ab8ad6', darkSoft: '#241a35' },
]

/**
 * The same project gets the same colour on every machine and after every
 * deploy, because it is derived from the id rather than from position in a
 * list that changes whenever somebody adds a project.
 */
export function projectColor(projectId?: number): ProjectColor {
  if (!projectId) return PALETTE[0]
  return PALETTE[projectId % PALETTE.length]
}

/** CSS custom properties to hang on a container. */
export function projectVars(projectId?: number, dark = false) {
  const c = projectColor(projectId)
  return {
    '--project': dark ? c.darkInk : c.ink,
    '--project-soft': dark ? c.darkSoft : c.soft,
  } as React.CSSProperties
}
