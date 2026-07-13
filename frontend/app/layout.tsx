import './globals.css'
import '../styles/production-ui.css'
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
  viewportFit: 'cover'
}

const shellBootstrap = `(function(){try{var d=document.documentElement;var t=localStorage.getItem('ai-shell-theme');if(t!=='dark'&&t!=='light'){t=window.matchMedia&&window.matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light'}d.dataset.theme=t;d.dataset.aiTheme=t;var s=localStorage.getItem('ai-shell-sidebar');d.dataset.sidebar=s==='expanded'?'expanded':'collapsed';d.dataset.mobileNav='closed'}catch(e){}})();`

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return <html lang="vi-VN" suppressHydrationWarning>
    <head><script dangerouslySetInnerHTML={{ __html: shellBootstrap }} /></head>
    <body><AppProvider><AppShell>{children}</AppShell></AppProvider></body>
  </html>
}

