import { Inbox } from 'lucide-react'

export function Empty({
  title,
  hint,
  icon: Icon = Inbox,
  action,
}: {
  title: string
  hint?: string
  icon?: React.ComponentType<{ className?: string }>
  action?: React.ReactNode
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed px-6 py-14 text-center">
      <Icon className="text-muted-foreground size-8" />
      <p className="font-medium">{title}</p>
      {hint && <p className="text-muted-foreground max-w-sm text-sm">{hint}</p>}
      {action && <div className="mt-3">{action}</div>}
    </div>
  )
}
