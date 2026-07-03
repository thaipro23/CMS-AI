import './globals.css'
import type { Metadata, Viewport } from 'next'
import { AppProvider } from '../context/AppContext'
import { AppShell } from '../components/layout/AppShell'

export const metadata: Metadata = {
  title: 'Open edX AI Server · FPT Polytechnic',
  description: 'Hệ thống quản lý ngân hàng đề, tạo Quiz trên CMS và theo dõi tiến trình học tập.'
}

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  maximumScale: 1,
  viewportFit: 'cover'
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return <html lang="vi-VN" suppressHydrationWarning><body><AppProvider><AppShell>{children}</AppShell></AppProvider></body></html>
}
