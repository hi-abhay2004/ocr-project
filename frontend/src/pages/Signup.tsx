import { useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { GraduationCap, Loader2, PenLine, ScanLine } from 'lucide-react'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { HOME_FOR_ROLE } from '@/auth/AuthContext'
import { useAuth } from '@/auth/useAuth'
import { errorMessage } from '@/lib/axios'
import { cn } from '@/lib/utils'
import type { Role } from '@/types/api'

const schema = z
  .object({
    role: z.enum(['TEACHER', 'STUDENT']),
    full_name: z.string().min(2, 'Enter your full name'),
    username: z
      .string()
      .min(3, 'At least 3 characters')
      .regex(/^[A-Za-z0-9_.]+$/, 'Letters, numbers, dot and underscore only'),
    email: z.email('Enter a valid email'),
    usn: z.string().optional(),
    password: z.string().min(8, 'At least 8 characters'),
    confirm: z.string(),
  })
  .superRefine((values, ctx) => {
    if (values.password !== values.confirm) {
      ctx.addIssue({ code: 'custom', path: ['confirm'], message: 'Passwords do not match' })
    }
    // USN is what links a login to the answer sheets uploaded for that student,
    // so it is required for students and meaningless for teachers.
    if (values.role === 'STUDENT') {
      if (!values.usn?.trim()) {
        ctx.addIssue({ code: 'custom', path: ['usn'], message: 'Your USN is required' })
      } else if (!/^[0-9A-Za-z]{6,15}$/.test(values.usn.trim())) {
        ctx.addIssue({ code: 'custom', path: ['usn'], message: 'USN looks malformed' })
      }
    }
  })

type Values = z.infer<typeof schema>

const ROLES: { value: Role; label: string; hint: string; icon: typeof PenLine }[] = [
  {
    value: 'TEACHER',
    label: 'Teacher',
    hint: 'Create exams, upload sheets, review and publish results.',
    icon: PenLine,
  },
  {
    value: 'STUDENT',
    label: 'Student',
    hint: 'View your published marks, coverage and feedback.',
    icon: GraduationCap,
  },
]

export function Signup() {
  const { user, isLoading, register: registerUser } = useAuth()
  const navigate = useNavigate()
  const [serverError, setServerError] = useState<string | null>(null)

  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      role: 'TEACHER',
      full_name: '',
      username: '',
      email: '',
      usn: '',
      password: '',
      confirm: '',
    },
  })

  const role = form.watch('role')

  if (!isLoading && user) return <Navigate to={HOME_FOR_ROLE[user.role]} replace />

  async function onSubmit(values: Values) {
    setServerError(null)
    try {
      const created = await registerUser({
        username: values.username,
        full_name: values.full_name,
        email: values.email,
        password: values.password,
        role: values.role,
        // Omit entirely for teachers rather than sending an empty string.
        ...(values.role === 'STUDENT' ? { usn: values.usn?.trim() } : {}),
      })
      navigate(HOME_FOR_ROLE[created.role], { replace: true })
    } catch (err) {
      setServerError(errorMessage(err, 'Could not create the account'))
    }
  }

  const errors = form.formState.errors
  const busy = form.formState.isSubmitting

  return (
    <div className="bg-muted/40 flex min-h-svh flex-col items-center justify-center gap-4 p-4">
      <Link to="/" className="flex items-center gap-2 font-semibold">
        <ScanLine className="size-5" />
        Answer Sheet Evaluation
      </Link>

      <Card className="w-full max-w-lg">
        <CardHeader>
          <CardTitle className="text-xl">Create your account</CardTitle>
          <CardDescription>
            Pick the role you need — it decides what you can do and cannot be changed later.
          </CardDescription>
        </CardHeader>

        <CardContent>
          <form onSubmit={form.handleSubmit(onSubmit)} noValidate className="space-y-4">
            {/* ── Role ───────────────────────────────────────────────── */}
            <fieldset className="space-y-2">
              <legend className="mb-2 text-sm font-medium">I am a…</legend>
              <div className="grid gap-2 sm:grid-cols-2">
                {ROLES.map(({ value, label, hint, icon: Icon }) => {
                  const selected = role === value
                  return (
                    <label
                      key={value}
                      className={cn(
                        'flex cursor-pointer gap-3 rounded-lg border p-3 transition-colors',
                        selected ? 'border-primary bg-primary/5' : 'hover:bg-muted/50',
                      )}
                    >
                      <input
                        type="radio"
                        value={value}
                        className="sr-only"
                        {...form.register('role')}
                      />
                      <Icon className="mt-0.5 size-4 shrink-0" />
                      <span>
                        <span className="block text-sm font-medium">{label}</span>
                        <span className="text-muted-foreground block text-xs">{hint}</span>
                      </span>
                    </label>
                  )
                })}
              </div>
            </fieldset>

            <div className="grid gap-4 sm:grid-cols-2">
              <Field id="full_name" label="Full name" error={errors.full_name?.message}>
                <Input
                  id="full_name"
                  autoComplete="name"
                  aria-invalid={!!errors.full_name}
                  {...form.register('full_name')}
                />
              </Field>

              <Field id="username" label="Username" error={errors.username?.message}>
                <Input
                  id="username"
                  autoComplete="username"
                  aria-invalid={!!errors.username}
                  {...form.register('username')}
                />
              </Field>
            </div>

            <Field id="email" label="Email" error={errors.email?.message}>
              <Input
                id="email"
                type="email"
                autoComplete="email"
                aria-invalid={!!errors.email}
                {...form.register('email')}
              />
            </Field>

            {role === 'STUDENT' && (
              <Field
                id="usn"
                label="USN"
                hint="This is what links your account to your answer sheets."
                error={errors.usn?.message}
              >
                <Input
                  id="usn"
                  placeholder="1BY22CS001"
                  aria-invalid={!!errors.usn}
                  {...form.register('usn')}
                />
              </Field>
            )}

            <div className="grid gap-4 sm:grid-cols-2">
              <Field id="password" label="Password" error={errors.password?.message}>
                <Input
                  id="password"
                  type="password"
                  autoComplete="new-password"
                  aria-invalid={!!errors.password}
                  {...form.register('password')}
                />
              </Field>

              <Field id="confirm" label="Confirm password" error={errors.confirm?.message}>
                <Input
                  id="confirm"
                  type="password"
                  autoComplete="new-password"
                  aria-invalid={!!errors.confirm}
                  {...form.register('confirm')}
                />
              </Field>
            </div>

            {serverError && (
              <Alert variant="destructive">
                <AlertDescription>{serverError}</AlertDescription>
              </Alert>
            )}

            <Button type="submit" className="w-full" disabled={busy}>
              {busy && <Loader2 className="size-4 animate-spin" />}
              Create account
            </Button>

            <p className="text-muted-foreground text-center text-sm">
              Already have an account?{' '}
              <Link to="/login" className="text-foreground underline underline-offset-4">
                Sign in
              </Link>
            </p>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}

function Field({
  id,
  label,
  hint,
  error,
  children,
}: {
  id: string
  label: string
  hint?: string
  error?: string
  children: React.ReactNode
}) {
  return (
    <div className="space-y-2">
      <Label htmlFor={id}>{label}</Label>
      {children}
      {hint && !error && <p className="text-muted-foreground text-xs">{hint}</p>}
      {error && <p className="text-destructive text-sm">{error}</p>}
    </div>
  )
}
