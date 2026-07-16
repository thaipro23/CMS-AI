import type { AppIconName } from '../../../components/icons/AppIcon'
import { VisualIcon } from '../../../components/ui/VisualIcon'

export function BankHierarchyPageIntro({
  title,
  description,
  icon = 'bank',
}: {
  title: string
  description: string
  icon?: AppIconName
}) {
  return <header className="bank-hierarchy-page-intro bank-page-identity" aria-labelledby="bank-hierarchy-page-title">
    <div className="bank-page-identity__main">
      <VisualIcon icon={icon} tone="blue" label={title} size={22} className="bank-page-identity__icon bank-hierarchy-page-icon" />
      <div className="bank-page-identity__copy bank-hierarchy-page-copy">
        <h1 id="bank-hierarchy-page-title">{title}</h1>
        <p>{description}</p>
      </div>
    </div>
  </header>
}
