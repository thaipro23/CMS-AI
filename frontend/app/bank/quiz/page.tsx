'use client'

import Link from 'next/link'
import { useEffect, useMemo, useState } from 'react'
import { useAppContext } from '../../../context/AppContext'
import {
  BankRelease,
  CourseQuizInstance,
  Department,
  EdxCourseMapping,
  MappingValidation,
  Subject,
  SubjectChapter,
  SubjectOffering,
} from '../../../types'
import {
  createCourseChapterMapping,
  createCourseMapping,
  getBankReleases,
  getCourseMappings,
  getDepartments,
  getSubjectChapters,
  getSubjectOfferings,
  getSubjects,
  validateCourseChapterMapping,
  validateCourseMapping,
  previewQuizFromBankRelease,
  createQuizFromBankRelease,
  getCourseQuizInstances,
  rollbackCourseQuizInstance,
} from '../../../lib/api'

function classNames(...items: Array<string | false | null | undefined>) {
  return items.filter(Boolean).join(' ')
}

export default function BankQuizPage() {
  const { authHeaders, can } = useAppContext()
  const headers = useMemo(() => authHeaders(true), [authHeaders])
  const [departments, setDepartments] = useState<Department[]>([])
  const [subjects, setSubjects] = useState<Subject[]>([])
  const [offerings, setOfferings] = useState<SubjectOffering[]>([])
  const [chapters, setChapters] = useState<SubjectChapter[]>([])
  const [releases, setReleases] = useState<BankRelease[]>([])
  const [mappings, setMappings] = useState<EdxCourseMapping[]>([])
  const [quizHistory, setQuizHistory] = useState<CourseQuizInstance[]>([])
  const [selectedDepartmentId, setSelectedDepartmentId] = useState('')
  const [selectedSubjectId, setSelectedSubjectId] = useState('')
  const [selectedOfferingId, setSelectedOfferingId] = useState('')
  const [selectedChapterId, setSelectedChapterId] = useState('')
  const [selectedReleaseId, setSelectedReleaseId] = useState('')
  const [selectedMappingId, setSelectedMappingId] = useState('')
  const [courseId, setCourseId] = useState('')
  const [courseTitle, setCourseTitle] = useState('')
  const [term, setTerm] = useState('')
  const [nodeId, setNodeId] = useState('')
  const [nodeTitle, setNodeTitle] = useState('')
  const [mappingValidation, setMappingValidation] = useState<MappingValidation | null>(null)
  const [chapterValidation, setChapterValidation] = useState<MappingValidation | null>(null)
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [savedChapterMappingId, setSavedChapterMappingId] = useState('')
  const [quizPlan, setQuizPlan] = useState<any | null>(null)
  const [quizResult, setQuizResult] = useState<any | null>(null)
  const [totalQuestions, setTotalQuestions] = useState(15)
  const [difficultyEasy, setDifficultyEasy] = useState(50)
  const [difficultyMedium, setDifficultyMedium] = useState(30)
  const [difficultyHard, setDifficultyHard] = useState(20)
  const [quizTitle, setQuizTitle] = useState('')

  const load = async () => {
    const [nextDepartments, nextSubjects, nextOfferings, nextChapters, nextReleases, nextMappings, nextQuizHistory] = await Promise.all([
      getDepartments(headers),
      getSubjects(headers),
      getSubjectOfferings(headers),
      getSubjectChapters(headers),
      getBankReleases(headers),
      getCourseMappings(headers),
      getCourseQuizInstances(headers, { limit: 50 }).catch(() => []),
    ])
    setDepartments(nextDepartments)
    setSubjects(nextSubjects)
    setOfferings(nextOfferings)
    setChapters(nextChapters)
    setReleases(nextReleases)
    setMappings(nextMappings)
    setQuizHistory(nextQuizHistory)
    const deptId = selectedDepartmentId || nextDepartments[0]?.id || ''
    const subjectId = selectedSubjectId || nextSubjects.find((item) => item.department_id === deptId)?.id || nextSubjects[0]?.id || ''
    const offeringId = selectedOfferingId || nextOfferings.find((item) => item.subject_id === subjectId)?.id || ''
    const chapterId = selectedChapterId || nextChapters.find((item) => item.subject_offering_id === offeringId)?.id || ''
    const releaseId = selectedReleaseId || nextReleases.find((item) => item.chapter_id === chapterId && item.status === 'published')?.id || ''
    const mappingId = selectedMappingId || nextMappings.find((item) => item.subject_id === subjectId)?.id || ''
    setSelectedDepartmentId(deptId)
    setSelectedSubjectId(subjectId)
    setSelectedOfferingId(offeringId)
    setSelectedChapterId(chapterId)
    setSelectedReleaseId(releaseId)
    setSelectedMappingId(mappingId)
  }

  useEffect(() => {
    load().catch((error) => setMessage(error instanceof Error ? error.message : 'Không tải được dữ liệu mapping'))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const run = async (work: () => Promise<unknown>, ok: string) => {
    setBusy(true)
    setMessage('')
    try {
      await work()
      await load()
      setMessage(ok)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Thao tác thất bại')
    } finally {
      setBusy(false)
    }
  }

  const subjectsOfDepartment = subjects.filter((item) => item.department_id === selectedDepartmentId)
  const offeringsOfSubject = offerings.filter((item) => item.subject_id === selectedSubjectId)
  const chaptersOfOffering = chapters.filter((item) => item.subject_offering_id === selectedOfferingId)
  const publishedReleasesOfChapter = releases.filter((item) => item.chapter_id === selectedChapterId && item.status === 'published')
  const selectedSubject = subjects.find((item) => item.id === selectedSubjectId)
  const selectedOffering = offerings.find((item) => item.id === selectedOfferingId)
  const selectedChapter = chapters.find((item) => item.id === selectedChapterId)
  const selectedRelease = releases.find((item) => item.id === selectedReleaseId)
  const selectedMapping = mappings.find((item) => item.id === selectedMappingId)
  const readyToCreateQuiz = Boolean(selectedMapping && selectedRelease && selectedRelease.status === 'published' && (savedChapterMappingId || chapterValidation?.can_create_mapping))

  if (!can('publish_questions')) return <div className="card empty-state">Bạn không có quyền map khóa học hoặc tạo quiz.</div>

  return <div className="page-stack bank-quiz-page">
    <section className="card page-intro">
      <div>
        <div className="eyebrow">Open edX Quiz</div>
        <h1>Map khóa học, tạo Quiz và lịch sử</h1>
        <p>Chỉ tạo Quiz khi bộ đề đã chốt/publish. Phía dưới có lịch sử Quiz đã tạo và nút rollback khi cần.</p>
      </div>
      <Link className="btn secondary" href="/bank">Quay lại Ngân hàng đề</Link>
    </section>

    {message ? <div className={classNames('alert', message.toLowerCase().includes('lỗi') || message.toLowerCase().includes('thất bại') ? 'danger' : 'success')}>{message}</div> : null}

    <section className="card">
      <h2>1. Chọn bộ đề đã publish</h2>
      <div className="inline-form compact-form">
        <label>Bộ môn<select className="input" value={selectedDepartmentId} onChange={(event) => setSelectedDepartmentId(event.target.value)}>{departments.map((item) => <option key={item.id} value={item.id}>{item.code} · {item.name}</option>)}</select></label>
        <label>Môn<select className="input" value={selectedSubjectId} onChange={(event) => setSelectedSubjectId(event.target.value)}>{subjectsOfDepartment.map((item) => <option key={item.id} value={item.id}>{item.code} · {item.name}</option>)}</select></label>
        <label>Version môn<select className="input" value={selectedOfferingId} onChange={(event) => setSelectedOfferingId(event.target.value)}>{offeringsOfSubject.map((item) => <option key={item.id} value={item.id}>{item.code}</option>)}</select></label>
        <label>Bài<select className="input" value={selectedChapterId} onChange={(event) => setSelectedChapterId(event.target.value)}>{chaptersOfOffering.map((item) => <option key={item.id} value={item.id}>Bài {item.chapter_no} · {item.title}</option>)}</select></label>
        <label>Release đã publish<select className="input" value={selectedReleaseId} onChange={(event) => setSelectedReleaseId(event.target.value)}><option value="">Chưa có release public</option>{publishedReleasesOfChapter.map((item) => <option key={item.id} value={item.id}>{item.release_code} · {item.approved_question_count} câu</option>)}</select></label>
      </div>
      {!publishedReleasesOfChapter.length ? <div className="alert warning">Bài này chưa có Release đã publish. Quay lại trang Ngân hàng đề để tạo Release và bấm Publish Library trước.</div> : <div className="alert success">Release sẵn sàng: <b>{selectedRelease?.release_code}</b> · Library <code>{selectedRelease?.openedx_library_key}</code></div>}
    </section>

    <section className="card">
      <h2>2. Map course Open edX vào môn</h2>
      <p className="muted">Hệ thống sẽ chặn nếu dán nhầm course khác mã môn.</p>
      <div className="inline-form compact-form">
        <label>Course ID<input className="input" value={courseId} onChange={(event) => setCourseId(event.target.value)} placeholder="course-v1:FPT+WEB107+SU26" /></label>
        <label>Tên course<input className="input" value={courseTitle} onChange={(event) => setCourseTitle(event.target.value)} placeholder="Tên trong Studio" /></label>
        <label>Kỳ<input className="input" value={term} onChange={(event) => setTerm(event.target.value)} placeholder={selectedOffering?.term || 'SU26'} /></label>
      </div>
      <div className="button-row">
        <button className="btn secondary" disabled={busy || !selectedSubjectId || !courseId} onClick={async () => {
          setBusy(true)
          try {
            const result = await validateCourseMapping(headers, { openedx_course_id: courseId, subject_id: selectedSubjectId, department_id: selectedDepartmentId || null, term: term || selectedOffering?.term || '', openedx_course_title: courseTitle })
            setMappingValidation(result)
            setMessage(result.message)
            await load()
          } catch (error) {
            setMessage(error instanceof Error ? error.message : 'Kiểm tra course mapping thất bại')
          } finally {
            setBusy(false)
          }
        }}>Kiểm tra course</button>
        <button className="btn" disabled={busy || mappingValidation?.can_create_mapping !== true || mappingValidation?.risk_level === 'high'} onClick={() => run(() => createCourseMapping(headers, { openedx_course_id: courseId, subject_id: selectedSubjectId, department_id: selectedDepartmentId || null, term: term || selectedOffering?.term || '', openedx_course_title: courseTitle, allow_warnings: mappingValidation?.risk_level === 'medium' }), 'Đã lưu mapping course an toàn')}>Lưu mapping</button>
      </div>
      {mappingValidation ? <div className={classNames('alert', mappingValidation.risk_level === 'high' ? 'danger' : mappingValidation.risk_level === 'medium' ? 'warning' : 'success')}><b>{mappingValidation.message}</b><ul>{mappingValidation.checks.map((check) => <li key={check.code}>{check.status.toUpperCase()} · {check.message}</li>)}</ul></div> : null}
      <div className="inline-form compact-form">
        <label>Mapping đã lưu<select className="input" value={selectedMappingId} onChange={(event) => setSelectedMappingId(event.target.value)}>{mappings.filter((item) => item.subject_id === selectedSubjectId).map((item) => <option key={item.id} value={item.id}>{item.openedx_course_id}</option>)}</select></label>
      </div>
    </section>

    <section className="card">
      <h2>3. Map bài vào vị trí Open edX</h2>
      <p className="muted">Chỉ lưu được nếu Release đã publish và node Open edX thuộc đúng course.</p>
      <div className="inline-form compact-form">
        <label>Node Open edX<input className="input" value={nodeId} onChange={(event) => setNodeId(event.target.value)} placeholder="block-v1:...+type@chapter+block@..." /></label>
        <label>Tên node<input className="input" value={nodeTitle} onChange={(event) => setNodeTitle(event.target.value)} placeholder={selectedChapter?.title || 'Bài 4'} /></label>
      </div>
      <div className="button-row">
        <button className="btn secondary" disabled={busy || !selectedMappingId || !selectedChapterId || !selectedReleaseId || !nodeId} onClick={async () => {
          setBusy(true)
          try {
            const result = await validateCourseChapterMapping(headers, { course_mapping_id: selectedMappingId, subject_chapter_id: selectedChapterId, bank_release_id: selectedReleaseId, openedx_parent_node_id: nodeId, openedx_node_title: nodeTitle })
            setChapterValidation(result)
            setMessage(result.message)
            await load()
          } catch (error) {
            setMessage(error instanceof Error ? error.message : 'Kiểm tra chapter mapping thất bại')
          } finally {
            setBusy(false)
          }
        }}>Kiểm tra chapter</button>
        <button className="btn" disabled={busy || chapterValidation?.can_create_mapping !== true || chapterValidation?.risk_level === 'high'} onClick={async () => {
          setBusy(true)
          setMessage('')
          try {
            const saved = await createCourseChapterMapping(headers, { course_mapping_id: selectedMappingId, subject_chapter_id: selectedChapterId, bank_release_id: selectedReleaseId, openedx_parent_node_id: nodeId, openedx_node_title: nodeTitle, allow_warnings: chapterValidation?.risk_level === 'medium' })
            setSavedChapterMappingId(saved.id)
            await load()
            setMessage('Đã lưu mapping chapter vào Release')
          } catch (error) {
            setMessage(error instanceof Error ? error.message : 'Lưu mapping chapter thất bại')
          } finally {
            setBusy(false)
          }
        }}>Lưu chapter mapping</button>
      </div>
      {chapterValidation ? <div className={classNames('alert', chapterValidation.risk_level === 'high' ? 'danger' : chapterValidation.risk_level === 'medium' ? 'warning' : 'success')}><b>{chapterValidation.message}</b><ul>{chapterValidation.checks.map((check) => <li key={check.code}>{check.status.toUpperCase()} · {check.message}</li>)}</ul></div> : null}
    </section>

    <section className="card">
      <h2>4. Tạo Quiz từ Bank Release</h2>
      {readyToCreateQuiz ? <div className="alert success">Đủ điều kiện tạo Quiz từ Release <b>{selectedRelease?.release_code}</b>. Hệ thống sẽ tạo Quiz node và native Problem Bank Beta trên Open edX.</div> : <div className="alert warning">Chưa đủ điều kiện tạo Quiz. Cần Release đã publish, course mapping an toàn và chapter mapping an toàn.</div>}
      <div className="inline-form compact-form">
        <label>Số câu<input className="input" type="number" min={1} max={200} value={totalQuestions} onChange={(event) => setTotalQuestions(Number(event.target.value || 15))} /></label>
        <label>Easy %<input className="input" type="number" value={difficultyEasy} onChange={(event) => setDifficultyEasy(Number(event.target.value || 0))} /></label>
        <label>Medium %<input className="input" type="number" value={difficultyMedium} onChange={(event) => setDifficultyMedium(Number(event.target.value || 0))} /></label>
        <label>Hard %<input className="input" type="number" value={difficultyHard} onChange={(event) => setDifficultyHard(Number(event.target.value || 0))} /></label>
        <label>Tên Quiz<input className="input" value={quizTitle} onChange={(event) => setQuizTitle(event.target.value)} placeholder={`AI Learning Check - ${selectedChapter?.title || 'Bài'}`} /></label>
      </div>
      <div className="button-row">
        <button className="btn secondary" disabled={busy || !selectedReleaseId} onClick={async () => {
          setBusy(true)
          setMessage('')
          try {
            const result = await previewQuizFromBankRelease(headers, selectedReleaseId, { total_questions: totalQuestions, difficulty_easy: difficultyEasy, difficulty_medium: difficultyMedium, difficulty_hard: difficultyHard, max_families_per_bank: 2 })
            setQuizPlan(result)
            setMessage(result.message)
            await load()
          } catch (error) {
            setMessage(error instanceof Error ? error.message : 'Không tính được kế hoạch Quiz')
          } finally {
            setBusy(false)
          }
        }}>Xem kế hoạch</button>
        <button className="btn" disabled={busy || !readyToCreateQuiz || !selectedReleaseId || !(savedChapterMappingId || chapterValidation?.can_create_mapping)} onClick={async () => {
          setBusy(true)
          setMessage('')
          try {
            let mappingId = savedChapterMappingId
            if (!mappingId) {
              const saved = await createCourseChapterMapping(headers, { course_mapping_id: selectedMappingId, subject_chapter_id: selectedChapterId, bank_release_id: selectedReleaseId, openedx_parent_node_id: nodeId, openedx_node_title: nodeTitle, allow_warnings: chapterValidation?.risk_level === 'medium' })
              mappingId = saved.id
              setSavedChapterMappingId(saved.id)
            }
            const result = await createQuizFromBankRelease(headers, selectedReleaseId, { course_chapter_mapping_id: mappingId, quiz_title: quizTitle, unit_title: 'Quiz tự luyện', total_questions: totalQuestions, difficulty_easy: difficultyEasy, difficulty_medium: difficultyMedium, difficulty_hard: difficultyHard, max_families_per_bank: 2 })
            setQuizResult(result)
            setQuizPlan(result.plan)
            setMessage(result.message)
            await load()
          } catch (error) {
            setMessage(error instanceof Error ? error.message : 'Tạo Quiz thất bại')
          } finally {
            setBusy(false)
          }
        }}>Tạo Quiz thật trên Open edX</button>
      </div>
      {quizPlan ? <div className="alert success"><b>{quizPlan.total_questions}</b> Problem Bank slot · <b>{quizPlan.assigned_component_count}</b> component · {quizPlan.message}{quizPlan.warnings?.length ? <ul>{quizPlan.warnings.map((item: string, index: number) => <li key={index}>{item}</li>)}</ul> : null}</div> : null}
      {quizResult ? <div className="alert success">Đã tạo Quiz: <code>{quizResult.openedx_unit_node_id}</code></div> : null}
      <p className="muted">Hệ thống không báo thành công nếu Open edX chưa tạo được Quiz node và native Problem Bank thật.</p>
    </section>

    <section className="card">
      <h2>5. Lịch sử Quiz đã tạo</h2>
      <p className="muted">Dùng để biết Quiz nào đã đẩy lên Open edX. Nếu tạo nhầm, bấm rollback. Nếu Open edX chưa xác nhận xóa được, hệ thống sẽ báo cần kiểm tra thủ công trong Studio.</p>
      <div className="table-wrap"><table className="data-table compact-table"><thead><tr><th>Course</th><th>Trạng thái</th><th>Unit Open edX</th><th>Thời gian</th><th></th></tr></thead><tbody>{quizHistory.map((item) => <tr key={item.id}><td><b>{item.openedx_course_id}</b><small>{item.metadata_json?.quiz_title || item.bank_release_id}</small></td><td><span className={classNames('status', item.status === 'created' ? 'success' : item.status?.includes('rollback') || item.status === 'failed' ? 'danger' : 'pending')}>{item.status}</span></td><td><code>{item.openedx_unit_node_id || '—'}</code></td><td>{new Date(item.created_at).toLocaleString()}</td><td><button className="btn small secondary" disabled={busy || !can('publish_questions') || item.status === 'rolled_back'} onClick={() => run(() => rollbackCourseQuizInstance(headers, item.id, { mode: 'safe', note: 'Rollback từ giao diện lịch sử Quiz' }), 'Đã gửi yêu cầu rollback Quiz')}>Rollback</button></td></tr>)}</tbody></table></div>
      {!quizHistory.length ? <div className="empty-state">Chưa có Quiz nào được tạo từ ngân hàng đề.</div> : null}
    </section>
  </div>
}
