import { redirect } from 'next/navigation'

export default function LegacyRedirectPage() {
  redirect('/ap-sync')
}
