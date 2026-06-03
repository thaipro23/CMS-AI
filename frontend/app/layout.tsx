import './globals.css'
import type { Metadata } from 'next'
import { AppProvider } from '../context/AppContext'
import { AppShell } from '../components/layout/AppShell'

export const metadata: Metadata = {
  title: 'Bảng điều khiển AI Open edX',
  description: 'Máy chủ AI Learning cho Open edX CMS'
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return <html lang="vi"><body><AppProvider><AppShell>{children}</AppShell></AppProvider></body></html>
}
