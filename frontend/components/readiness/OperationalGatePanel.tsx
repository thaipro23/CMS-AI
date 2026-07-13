import type { ReactNode } from 'react'

export type OperationalGateTone = 'success' | 'warning' | 'danger' | 'neutral'

export type OperationalGatePanelProps = {
  title: string
  subtitle?: string
  tone?: OperationalGateTone
  status?: string
  counters?: Array<{ label: string; value: ReactNode; tone?: OperationalGateTone }>
  children?: ReactNode
}

function toneClass(tone: OperationalGateTone = 'neutral') {
  if (tone === 'success') return 'status-pill success'
  if (tone === 'warning') return 'status-pill warning'
  if (tone === 'danger') return 'status-pill danger'
  return 'status-pill neutral'
}

/**
 * Shared enterprise-style panel for security/performance/RC/pilot gates.
 * v25.9.16.7.2.64.12 introduces this component so future readiness UI does not
 * keep expanding analytics/learning/page.tsx.
 */
export function OperationalGatePanel({ title, subtitle, tone = 'neutral', status, counters = [], children }: OperationalGatePanelProps) {
  return (
    <section className={`ops-gate-panel ${tone}`}>
      <div className="analytics-pilot-head">
        <div>
          <b>{title}</b>
          {subtitle && <span>{subtitle}</span>}
        </div>
        <div className="analytics-pilot-counters">
          {status && <span className={toneClass(tone)}>{status}</span>}
          {counters.map((item, index) => <span key={`${item.label}-${index}`} className={toneClass(item.tone)}>{item.value} {item.label}</span>)}
        </div>
      </div>
      {children}
    </section>
  )
}
