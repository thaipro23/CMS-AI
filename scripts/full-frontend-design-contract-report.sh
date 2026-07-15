#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="${EXPECTED_VERSION:-25.9.16.7.2.64.16.5.7.2.2}"
pass=0
fail=0
check() {
  local label="$1"; shift
  if "$@"; then printf 'PASS  %s\n' "$label"; pass=$((pass+1)); else printf 'FAIL  %s\n' "$label"; fail=$((fail+1)); fi
}
contains() { grep -Fq -- "$2" "$1"; }
not_contains() { ! grep -Fq -- "$2" "$1"; }
contains_regex() { grep -Eq -- "$2" "$1"; }

APP="$ROOT/frontend/components/layout/AppShell.tsx"
TABLE="$ROOT/frontend/components/table/EnterpriseDataTable.tsx"
CSS="$ROOT/frontend/styles/full-frontend-design-contract.css"
SEM="$ROOT/frontend/app/semesters/page.tsx"
BANK="$ROOT/frontend/app/bank/_components/pages/BankDashboardPage.tsx"
CHAPTER="$ROOT/frontend/app/bank/_components/pages/ChapterWorkspacePage.tsx"
STUDENT="$ROOT/frontend/app/student-management/page.tsx"
CLASS="$ROOT/frontend/app/student-management/classes/[classId]/page.tsx"
USERS="$ROOT/frontend/app/users/page.tsx"
RBAC_ROUTE="$ROOT/backend/app/api/routes/rbac.py"
RBAC_SERVICE="$ROOT/backend/app/services/business_rbac.py"
DOCKERFILE="$ROOT/frontend/Dockerfile"

check 'Version metadata is current' contains "$ROOT/frontend/package.json" "\"version\": \"$VERSION\""
check 'Question search removed from sidebar' not_contains "$APP" "href: '/bank/search'"
check 'Breadcrumb component renders no navigation' contains "$ROOT/frontend/components/navigation/Breadcrumbs.tsx" 'return null'
check 'Topbar owns the page title' contains "$APP" 'enterprise-topbar-page-heading'
check 'Sidebar/workspace use fixed viewport shell' bash -c "grep -Fq '.enterprise-app-shell {' '$CSS' && grep -Fq 'height: 100dvh;' '$CSS'"
check 'Only main content scrolls vertically' bash -c "grep -Fq '.enterprise-content {' '$CSS' && grep -Fq 'overflow-y: auto;' '$CSS'"
check 'No in-content breadcrumb is visible' contains "$CSS" '.enterprise-breadcrumbs { display: none !important; }'
check 'Spacing contract uses the 4px scale' contains "$CSS" '--acms-space-6: 24px'
check 'Semester actions live in the list section' contains "$SEM" 'title="Danh sách học kỳ"'
check 'Semester KPI strip removed' not_contains "$SEM" 'OperationsKpiStrip'
check 'Semester has separate Block 1 and Block 2 columns' bash -c "grep -Fq \"header: 'Lịch Block 1'\" '$SEM' && grep -Fq \"header: 'Lịch Block 2'\" '$SEM'"
check 'Semester table duplicated summary disabled' contains "$SEM" 'showSummary={false}'
check 'Semester editor is single-flow and non-overlapping' contains "$CSS" '.semester-dialog-body .term-block-editor { grid-template-columns: minmax(0, 1fr); }'
check 'Bank filters and scope metadata share one toolbar' contains "$BANK" 'dashboard-control-bar'
check 'Bank legacy scope strip removed' not_contains "$BANK" 'dashboard-scope-strip'
chapter_stat_count=$(grep -c 'chapter-inline-stats' "$CHAPTER" || true)
check 'Chapter redundant primary KPI strip removed' test "$chapter_stat_count" -le 1
check 'Chapter action labels carry useful counts' bash -c "grep -Fq 'Tạo câu hỏi (còn' '$CHAPTER' && grep -Fq 'Duyệt câu hỏi (' '$CHAPTER'"
check 'Concept remains opt-in via column visibility' contains "$ROOT/frontend/app/bank/_components/BankQuestionEnterpriseTable.tsx" "key: 'concept', header: 'Concept'"
check 'Source remains opt-in via column visibility' contains "$ROOT/frontend/app/bank/_components/BankQuestionEnterpriseTable.tsx" "key: 'source', header: 'Nguồn'"
check 'Student auto-map belongs to subject section' bash -c "grep -Fq 'title=\"Danh sách môn\"' '$STUDENT' && grep -Fq 'Tự động ghép Course CMS' '$STUDENT'"
check 'Student class list uses EnterpriseDataTable' bash -c "grep -Fq '<EnterpriseDataTable' '$CLASS' && ! grep -Fq 'student-grade-table' '$CLASS'"
back_link_count=$(grep -l 'ContextBackLink' "$ROOT"/frontend/app/bank/_components/pages/*.tsx | wc -l)
check 'Nested Bank pages use contextual back links' test "$back_link_count" -ge 4
check 'Granting rights is a centered dialog' bash -c "grep -Fq 'title=\"Gán quyền\"' '$USERS' && grep -Fq '<AccessibleDialog' '$USERS' && ! grep -Fq 'rbac-grant-panel' '$USERS'"
check 'Legacy CAMPUS_MANAGER cannot be granted anew' contains "$USERS" "filter((role) => role.code !== 'CAMPUS_MANAGER')"
check 'RBAC UI supports selecting multiple scopes' contains "$USERS" 'selectedScopeIds'
check 'RBAC backend has atomic batch endpoint' bash -c "grep -Fq \"'/assignments/batch'\" '$RBAC_ROUTE' && grep -Fq 'def create_assignments_batch' '$RBAC_SERVICE' && grep -Fq 'self.db.rollback()' '$RBAC_SERVICE'"
check 'Data tables keep full content by default' contains "$TABLE" 'showSummary = false'
check 'Production image skips duplicate lint/typecheck by default' contains "$DOCKERFILE" 'FRONTEND_VALIDATE_IN_IMAGE=false'
check 'Next build worker is in-process on constrained UAT hosts' contains "$ROOT/frontend/next.config.js" 'webpackBuildWorker: false'
check 'Final design stylesheet is imported last' bash -c "tail -n +1 '$ROOT/frontend/app/layout.tsx' | grep -n 'full-frontend-design-contract.css' >/dev/null"

printf '\nFull frontend design contract: %s pass, %s fail\n' "$pass" "$fail"
if (( fail > 0 )); then exit 1; fi
printf 'READY — %s/%s\n' "$pass" "$((pass+fail))"
