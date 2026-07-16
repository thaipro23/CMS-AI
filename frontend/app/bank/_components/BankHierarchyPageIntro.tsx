import type { AppIconName } from '../../../components/icons/AppIcon'
import { AppIcon } from '../../../components/icons/AppIcon'

export function BankHierarchyPageIntro({
  title,
  description,
  icon = 'bank',
}: {
  title: string
  description: string
  icon?: AppIconName
}) {
  return <section className="bank-hierarchy-page-intro" aria-labelledby="bank-hierarchy-page-title">
    <span className="bank-hierarchy-page-icon" aria-hidden="true"><AppIcon name={icon} size={34} /></span>
    <div className="bank-hierarchy-page-copy">
      <h2 id="bank-hierarchy-page-title">{title}</h2>
      <p>{description}</p>
    </div>
  </section>
}
