import { CheckCircle2, CircleAlert, Lightbulb } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { Feedback } from '@/types/api'

const SECTIONS = [
  {
    key: 'strengths',
    title: 'What you did well',
    icon: CheckCircle2,
    tone: 'text-green-700 dark:text-green-400',
    ring: 'border-green-600/30 bg-green-50/60 dark:bg-green-950/20',
  },
  {
    key: 'gaps',
    title: 'What was missing',
    icon: CircleAlert,
    tone: 'text-amber-700 dark:text-amber-400',
    ring: 'border-amber-600/30 bg-amber-50/60 dark:bg-amber-950/20',
  },
  {
    key: 'suggestions',
    title: 'How to improve',
    icon: Lightbulb,
    tone: 'text-blue-700 dark:text-blue-400',
    ring: 'border-blue-600/30 bg-blue-50/60 dark:bg-blue-950/20',
  },
] as const

export function FeedbackPanel({ feedback, className }: { feedback: Feedback; className?: string }) {
  return (
    <div className={cn('space-y-3', className)}>
      {SECTIONS.map(({ key, title, icon: Icon, tone, ring }) => (
        <div key={key} className={cn('rounded-lg border p-3', ring)}>
          <p className={cn('flex items-center gap-1.5 text-sm font-medium', tone)}>
            <Icon className="size-4" />
            {title}
          </p>
          <p className="mt-1.5 text-sm leading-relaxed">{feedback[key] || '—'}</p>
        </div>
      ))}
    </div>
  )
}
