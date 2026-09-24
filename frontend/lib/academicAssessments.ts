import type { AcademicLearningComponentScore } from '../types'


type AssessmentScore = AcademicLearningComponentScore & {
  label?: string | null
  display_name?: string | null
  title?: string | null
}

export type CanonicalAssessmentColumn = {
  key: string
  name: string
  quizNumber?: number | null
  assessmentType: 'quiz' | 'final_test'
  deadlineDate?: string | null
  availableFrom?: string | null
  deadlineMode?: string | null
  scheduleWarning?: string | null
}

const QUIZ_LABEL = /\b(?:quiz|learning\s*check|lc)\s*#?\s*(\d{1,3})\b/i

function positiveInteger(value: unknown) {
  const number = Number(value)
  return Number.isInteger(number) && number >= 1 && number <= 999 ? number : null
}

function normalizedLabel(value: unknown) {
  return String(value || '').normalize('NFKC').trim().toLowerCase().replace(/\s+/g, ' ')
}

function labels(score: AssessmentScore) {
  return [score.name, score.label, score.display_name, score.title]
    .map((value) => String(value || '').trim())
    .filter(Boolean)
}

export function canonicalAssessmentIdentity(score: AssessmentScore) {
  const humanLabels = labels(score)
  const match = QUIZ_LABEL.exec(humanLabels.join(' '))
  const assessmentType = String(score.assessment_type || '').trim().toLowerCase()
  const number = match
    ? positiveInteger(match[1])
    : assessmentType === 'quiz'
      ? positiveInteger(score.quiz_number)
      : null
  if (number) return `quiz:${number}`
  if (
    assessmentType === 'final_test'
    || humanLabels.some((label) => normalizedLabel(label) === 'final test')
  ) return 'final_test'
  return null
}

export function canonicalAssessmentColumns(
  scores: AssessmentScore[],
): CanonicalAssessmentColumn[] {
  const byIdentity = new Map<string, CanonicalAssessmentColumn>()
  scores.forEach((score) => {
    const identity = canonicalAssessmentIdentity(score)
    if (!identity) return
    const existing = byIdentity.get(identity)
    const isFinal = identity === 'final_test'
    const quizNumber = isFinal ? null : positiveInteger(identity.split(':', 2)[1])
    byIdentity.set(identity, {
      key: identity,
      name: isFinal ? 'Final test' : `Quiz ${quizNumber}`,
      quizNumber,
      assessmentType: isFinal ? 'final_test' : 'quiz',
      deadlineDate: score.deadline_date || existing?.deadlineDate || null,
      availableFrom: score.available_from || existing?.availableFrom || null,
      deadlineMode: score.deadline_mode || existing?.deadlineMode || null,
      scheduleWarning: score.schedule_warning || existing?.scheduleWarning || null,
    })
  })
  return Array.from(byIdentity.values()).sort((left, right) => {
    if (left.assessmentType !== right.assessmentType) {
      return left.assessmentType === 'quiz' ? -1 : 1
    }
    return (left.quizNumber || 0) - (right.quizNumber || 0)
  })
}
