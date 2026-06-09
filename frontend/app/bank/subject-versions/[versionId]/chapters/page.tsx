import { SubjectVersionChaptersPage } from '../../../_components/BankPages'
export default function Page({ params }: { params: { versionId: string } }) { return <SubjectVersionChaptersPage versionId={params.versionId} /> }
