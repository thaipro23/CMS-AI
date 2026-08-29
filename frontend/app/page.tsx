'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useAppContext } from '../context/AppContext'

export default function Home() {
  const router = useRouter()
  const { authReady, isAuthenticated } = useAppContext()

  useEffect(() => {
    if (authReady && isAuthenticated) router.replace('/bank')
  }, [authReady, isAuthenticated, router])

  return <section className="card empty-state" role="status" aria-live="polite">
    <h1>Đang kết nối phiên CMS</h1>
    <p>{authReady ? 'Đang chuyển sang CMS để nhận phiên đăng nhập…' : 'Đang kiểm tra phiên đăng nhập hiện tại…'}</p>
  </section>
}
