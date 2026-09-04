import './globals.css'
import '../styles/production-ui.css'
import '../styles/enterprise-visual-foundation.css'
import '../styles/bank-workflow-ux.css'
import '../styles/training-analytics-ux.css'
import '../styles/operations-catalog-rbac-ux.css'
import '../styles/production-ux-acceptance.css'
import '../styles/production-ux-browser-hotfix.css'
import '../styles/global-visual-polish.css'
import '../styles/layout-integrity.css'
import '../styles/frontend-runtime-contracts.css'
import '../styles/full-frontend-design-contract.css'
import '../styles/frontend-visual-ergonomics-hotfix.css'
import '../styles/bank-redesign-batch-one.css'
import '../styles/global-project-responsive-contract.css'
import '../styles/bank-design-contract.css'
import '../styles/enterprise-screen-contract.css'
import '../styles/global-workspace-scroll-notice-hotfix.css'
import '../styles/student-operations-visual-hotfix.css'
import '../styles/bank-cost-dashboard.css'
import '../styles/subject-management-udemy.css'
import '../styles/project-spacing-contract.css'
import type { Metadata, Viewport } from 'next'
import { AppProvider } from '../context/AppContext'
import { AppShell } from '../components/layout/AppShell'
import { FeedbackProvider } from '../components/ui/FeedbackProvider'

export const metadata: Metadata = {
  title: 'Open edX AI Server · FPT Polytechnic',
  description: 'Hệ thống quản lý ngân hàng đề, tạo Quiz trên CMS và theo dõi tiến trình học tập.'
}

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  viewportFit: 'cover'
}

const shellBootstrap = `(function(){try{var d=document.documentElement;d.dataset.theme='light';d.dataset.aiTheme='light';var s=localStorage.getItem('ai-shell-sidebar');d.dataset.sidebar=s==='collapsed'?'collapsed':'expanded';d.dataset.mobileNav='closed'}catch(e){}})();`

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return <html lang="vi-VN" suppressHydrationWarning>
    <head><script dangerouslySetInnerHTML={{ __html: shellBootstrap }} /></head>
    <body><AppProvider><FeedbackProvider><AppShell>{children}</AppShell></FeedbackProvider></AppProvider></body>
  </html>
}

