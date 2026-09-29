import { Link } from 'react-router-dom'
import { LogOut, ScanLine } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { HOME_FOR_ROLE } from '@/auth/AuthContext'
import { useAuth } from '@/auth/useAuth'

export function Header({ children }: { children?: React.ReactNode }) {
  const { user, logout } = useAuth()

  return (
    <header className="bg-background/95 supports-[backdrop-filter]:bg-background/70 sticky top-0 z-40 border-b backdrop-blur">
      <div className="mx-auto flex h-14 max-w-7xl items-center gap-3 px-4">
        <Link
          to={user ? HOME_FOR_ROLE[user.role] : '/login'}
          className="flex shrink-0 items-center gap-2 font-semibold"
        >
          <ScanLine className="size-5" />
          <span className="hidden sm:inline">Answer Sheet Evaluation</span>
          <span className="sm:hidden">AES</span>
        </Link>

        <div className="min-w-0 flex-1">{children}</div>

        {user && (
          <div className="flex shrink-0 items-center gap-2">
            <Badge variant="secondary" className="hidden sm:inline-flex">
              {user.role === 'TEACHER' ? 'Teacher' : 'Student'}
            </Badge>
            <span className="text-muted-foreground hidden max-w-[12rem] truncate text-sm md:inline">
              {user.full_name || user.username}
            </span>
            <Button variant="ghost" size="sm" onClick={logout} aria-label="Log out">
              <LogOut className="size-4" />
              <span className="hidden sm:inline">Log out</span>
            </Button>
          </div>
        )}
      </div>
    </header>
  )
}
