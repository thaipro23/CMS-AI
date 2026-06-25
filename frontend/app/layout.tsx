import './globals.css'
import type { Metadata } from 'next'
import { AppProvider } from '../context/AppContext'
import { AppShell } from '../components/layout/AppShell'

export const metadata: Metadata = {
  title: 'Open edX AI Server · FPT Polytechnic',
  description: 'Hệ thống quản lý ngân hàng đề, tạo Quiz trên CMS và theo dõi tiến trình học tập.'
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return <html lang="vi" data-ai-theme="dark" suppressHydrationWarning><body className="ai-theme-dark"><AppProvider><AppShell>{children}</AppShell></AppProvider></body></html>
}
