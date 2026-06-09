import { SubjectVersionsPage } from '../../../_components/BankPages'
export default function Page({ params }: { params: { subjectId: string } }) { return <SubjectVersionsPage subjectId={params.subjectId} /> }
