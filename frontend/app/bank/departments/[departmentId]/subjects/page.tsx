import { DepartmentSubjectsPage } from '../../../_components/BankPages'
export default function Page({ params }: { params: { departmentId: string } }) { return <DepartmentSubjectsPage departmentId={params.departmentId} /> }
