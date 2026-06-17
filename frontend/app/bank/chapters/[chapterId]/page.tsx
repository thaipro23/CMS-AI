import { ChapterWorkspacePage } from '../../_components/BankPages'
export default function Page({ params }: { params: { chapterId: string } }) { return <ChapterWorkspacePage chapterId={params.chapterId} /> }
