import { Outlet } from 'react-router-dom'
import { GraduationCap } from 'lucide-react'
import { Header } from './Header'
import { Nav, type NavItem } from './Nav'

const items: NavItem[] = [{ to: '/results', label: 'My results', icon: GraduationCap }]

export function StudentShell() {
  return (
    <div className="bg-background min-h-svh">
      <Header>
        <Nav items={items} />
      </Header>
      <main className="mx-auto max-w-4xl px-4 py-6">
        <Outlet />
      </main>
    </div>
  )
}
