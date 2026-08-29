import type { ReactNode } from 'react'
import type { AppIconName } from '../../../components/icons/AppIcon'
import { SectionHeader } from '../../../components/layout/SectionHeader'
import { VisualIcon, type VisualTone } from '../../../components/ui/VisualIcon'

export function BankPageIdentity({
  title,
  description,
  icon = 'bank',
  tone = 'blue',
  actions,
  meta,
  className = '',
}: {
  title: string
  description: ReactNode
  icon?: AppIconName
  tone?: VisualTone
  actions?: ReactNode
  meta?: ReactNode
  className?: string
}) {
  return <header className={`bank-page-identity ${className}`.trim()}>
    <div className="bank-page-identity__main">
      <VisualIcon icon={icon} tone={tone} label={title} size={22} className="bank-page-identity__icon" />
      <div className="bank-page-identity__copy">
        <div className="bank-page-identity__title-row">
          <h1>{title}</h1>
          {meta ? <div className="bank-page-identity__meta">{meta}</div> : null}
        </div>
        <p>{description}</p>
      </div>
    </div>
    {actions ? <div className="bank-page-identity__actions">{actions}</div> : null}
  </header>
}

export function BankWorkflowStepper({
  steps,
  currentStep,
  className = '',
}: {
  steps: Array<{ title: string; description: string; icon: AppIconName; tone?: VisualTone }>
  currentStep: number
  className?: string
}) {
  return <nav className={`bank-workflow-stepper ${className}`.trim()} aria-label="Quy trình nghiệp vụ">
    {steps.map((step, index) => {
      const number = index + 1
      const done = number < currentStep
      const active = number === currentStep
      return <div key={step.title} className={`bank-workflow-step${active ? ' is-active' : ''}${done ? ' is-done' : ''}`} aria-current={active ? 'step' : undefined}>
        <div className="bank-workflow-step__marker">
          {done ? <span aria-hidden="true">✓</span> : <span aria-hidden="true">{number}</span>}
        </div>
        <VisualIcon icon={step.icon} tone={step.tone || 'blue'} label={step.title} size={16} className="bank-workflow-step__icon" />
        <div className="bank-workflow-step__copy">
          <b>{step.title}</b>
          <small>{step.description}</small>
        </div>
      </div>
    })}
  </nav>
}

export function BankSection({
  title,
  description,
  icon,
  tone = 'blue',
  meta,
  actions,
  children,
  className = '',
  bodyClassName = '',
}: {
  title: string
  description?: ReactNode
  icon?: AppIconName
  tone?: VisualTone
  meta?: ReactNode
  actions?: ReactNode
  children: ReactNode
  className?: string
  bodyClassName?: string
}) {
  return <section className={`bank-section ${className}`.trim()}>
    <SectionHeader title={title} description={description} icon={icon} tone={tone} meta={meta} actions={actions} className="bank-section__header" />
    <div className={`bank-section__body ${bodyClassName}`.trim()}>{children}</div>
  </section>
}
