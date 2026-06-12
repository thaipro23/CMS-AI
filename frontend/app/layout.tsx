import './globals.css'
import type { Metadata } from 'next'
import { AppProvider } from '../context/AppContext'
import { AppShell } from '../components/layout/AppShell'

export const metadata: Metadata = {
  title: 'Open edX AI Server · FPT Polytechnic',
  description: 'Máy chủ AI quản lý ngân hàng đề, tạo Quiz Open edX và theo dõi vận hành giảng viên.'
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return <html lang="vi" suppressHydrationWarning><body><AppProvider><AppShell>{children}</AppShell></AppProvider></body></html>
}
