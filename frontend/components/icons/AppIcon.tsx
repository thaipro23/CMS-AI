import type { ReactNode, SVGProps } from 'react'

export type AppIconName =
  | 'dashboard' | 'bank' | 'search' | 'release' | 'quiz' | 'students' | 'teachers'
  | 'analytics' | 'jobs' | 'audit' | 'sync' | 'readiness' | 'campus' | 'semester'
  | 'users' | 'settings' | 'menu' | 'panel-left-close' | 'panel-left-open'
  | 'sun' | 'moon' | 'chevron-down' | 'chevron-right' | 'user' | 'logout' | 'close' | 'check'
  | 'book' | 'layers' | 'link' | 'alert' | 'clock' | 'calendar' | 'filter' | 'info'
  | 'database' | 'server' | 'shield' | 'upload' | 'download' | 'file' | 'money' | 'sparkles' | 'eye' | 'edit'

const paths: Record<AppIconName, ReactNode> = {
  dashboard: <><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></>,
  bank: <><path d="M4 5.5 12 2l8 3.5v13L12 22l-8-3.5z"/><path d="M4 5.5 12 9l8-3.5M12 9v13"/></>,
  search: <><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/></>,
  release: <><path d="M12 3v12"/><path d="m7 10 5 5 5-5"/><path d="M5 21h14"/></>,
  quiz: <><path d="M9 5h10v14H5V9z"/><path d="M9 5v4H5"/><path d="M9 13h6M9 16h4"/></>,
  students: <><path d="m3 10 9-5 9 5-9 5z"/><path d="M7 13v4c3 2 7 2 10 0v-4"/></>,
  teachers: <><circle cx="9" cy="8" r="3"/><path d="M3 20v-2a6 6 0 0 1 12 0v2"/><path d="M16 7h5M18.5 4.5v5"/></>,
  analytics: <><path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/></>,
  jobs: <><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M8 5V3h8v2M8 12h8M8 16h5"/></>,
  audit: <><path d="M6 3h9l3 3v15H6z"/><path d="M14 3v4h4M9 11h6M9 15h6"/></>,
  sync: <><path d="M20 7h-7a5 5 0 0 0-5 5"/><path d="m17 4 3 3-3 3"/><path d="M4 17h7a5 5 0 0 0 5-5"/><path d="m7 20-3-3 3-3"/></>,
  readiness: <><path d="M12 3 3 7v5c0 5 3.8 8.4 9 9 5.2-.6 9-4 9-9V7z"/><path d="m8.5 12 2.2 2.2 4.8-5"/></>,
  campus: <><path d="M3 21h18M5 21V9h14v12M8 12h2M14 12h2M8 16h2M14 16h2M9 9V5h6v4"/></>,
  semester: <><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4M8 3v4M3 10h18M8 14h2M14 14h2M8 18h2"/></>,
  users: <><circle cx="9" cy="8" r="3"/><path d="M3 20v-2a6 6 0 0 1 12 0v2"/><circle cx="17" cy="10" r="2"/><path d="M16 20v-1a4 4 0 0 1 5-3.9"/></>,
  settings: <><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6v.2h-4V21a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9A1.7 1.7 0 0 0 3 14H2.8v-4H3a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9L4.2 7 7 4.2l.1.1A1.7 1.7 0 0 0 9 4.6 1.7 1.7 0 0 0 10 3V2.8h4V3a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1L19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.2v4H21a1.7 1.7 0 0 0-1.6 1Z"/></>,
  menu: <><path d="M4 7h16M4 12h16M4 17h16"/></>,
  'panel-left-close': <><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M9 3v18M15 9l-3 3 3 3"/></>,
  'panel-left-open': <><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M9 3v18M12 9l3 3-3 3"/></>,
  sun: <><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></>,
  moon: <path d="M21 12.8A8.5 8.5 0 1 1 11.2 3 6.7 6.7 0 0 0 21 12.8Z"/>,
  'chevron-down': <path d="m6 9 6 6 6-6"/>,
  'chevron-right': <path d="m9 6 6 6-6 6"/>,
  user: <><circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/></>,
  logout: <><path d="M10 17l5-5-5-5M15 12H3"/><path d="M14 3h7v18h-7"/></>,
  close: <><path d="m6 6 12 12M18 6 6 18"/></>,
  check: <path d="m5 12 4 4L19 6"/>,
  book: <><path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H11v16H6.5A2.5 2.5 0 0 0 4 21.5z"/><path d="M20 5.5A2.5 2.5 0 0 0 17.5 3H13v16h4.5a2.5 2.5 0 0 1 2.5 2.5z"/></>,
  layers: <><path d="m12 2 9 5-9 5-9-5z"/><path d="m3 12 9 5 9-5"/><path d="m3 17 9 5 9-5"/></>,
  link: <><path d="M10 13a5 5 0 0 0 7.5.5l2-2a5 5 0 0 0-7-7l-1.1 1.1"/><path d="M14 11a5 5 0 0 0-7.5-.5l-2 2a5 5 0 0 0 7 7l1.1-1.1"/></>,
  alert: <><path d="M12 3 2.8 20h18.4z"/><path d="M12 9v4M12 17h.01"/></>,
  clock: <><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></>,
  calendar: <><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4M8 3v4M3 10h18"/></>,
  filter: <><path d="M4 5h16M7 12h10M10 19h4"/></>,
  info: <><circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/></>,
  database: <><ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6"/></>,
  server: <><rect x="3" y="4" width="18" height="6" rx="2"/><rect x="3" y="14" width="18" height="6" rx="2"/><path d="M7 7h.01M7 17h.01M11 7h6M11 17h6"/></>,
  shield: <><path d="M12 3 4 6v6c0 5 3.3 8 8 9 4.7-1 8-4 8-9V6z"/><path d="m8.5 12 2.2 2.2 4.8-5"/></>,
  upload: <><path d="M12 16V4M7 9l5-5 5 5"/><path d="M5 20h14"/></>,
  download: <><path d="M12 4v12M7 11l5 5 5-5"/><path d="M5 20h14"/></>,
  file: <><path d="M6 3h9l3 3v15H6z"/><path d="M14 3v4h4"/></>,
  money: <><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M7 9h.01M17 15h.01"/><circle cx="12" cy="12" r="2.5"/></>,
  sparkles: <><path d="m12 3 1.2 3.8L17 8l-3.8 1.2L12 13l-1.2-3.8L7 8l3.8-1.2z"/><path d="m19 14 .8 2.2L22 17l-2.2.8L19 20l-.8-2.2L16 17l2.2-.8z"/><path d="m5 14 .8 1.7L8 16.5l-2.2.8L5 19l-.8-1.7L2 16.5l2.2-.8z"/></>,
  eye: <><path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12Z"/><circle cx="12" cy="12" r="2.5"/></>,
  edit: <><path d="M4 20h4l11-11-4-4L4 16z"/><path d="m13.5 6.5 4 4"/></>,
}

export function AppIcon({ name, size = 18, ...props }: SVGProps<SVGSVGElement> & { name: AppIconName; size?: number }) {
  return <svg viewBox="0 0 24 24" width={size} height={size} fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false" {...props}>{paths[name]}</svg>
}
