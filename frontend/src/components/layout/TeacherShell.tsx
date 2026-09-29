import { Outlet } from 'react-router-dom'
import { BookOpen } from 'lucide-react'
import { Header } from './Header'
import { Nav, type NavItem } from './Nav'

const items: NavItem[] = [{ to: '/exams', label: 'Exams', icon: BookOpen }]

export function TeacherShell() {
  return (
    <div className="bg-background min-h-svh">
      <Header>
        <Nav items={items} />
      </Header>
      <main className="mx-auto max-w-7xl px-4 py-6">
        <Outlet />
      </main>
    </div>
  )
}
