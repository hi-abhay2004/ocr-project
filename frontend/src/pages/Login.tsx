import { useState } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Loader2, ScanLine } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { HOME_FOR_ROLE } from '@/auth/AuthContext'
import { useAuth } from '@/auth/useAuth'
import { errorMessage } from '@/lib/axios'

const schema = z.object({
  username: z.string().min(1, 'Username is required'),
  password: z.string().min(1, 'Password is required'),
})

type FormValues = z.infer<typeof schema>

export function Login() {
  const { user, isLoading: authLoading, login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [serverError, setServerError] = useState<string | null>(null)

  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { username: '', password: '' },
  })

  // Already signed in — never show the form again, just go home.
  if (!authLoading && user) return <Navigate to={HOME_FOR_ROLE[user.role]} replace />

  async function onSubmit(values: FormValues) {
    setServerError(null)
    try {
      const u = await login(values.username, values.password)
      // The role decides the landing page, but a deep link they were bounced
      // from wins — as long as it belongs to their role's tree.
      const from = (location.state as { from?: string } | null)?.from
      const home = HOME_FOR_ROLE[u.role]
      const isTeacherPath = from?.startsWith('/exams') || from?.startsWith('/sheets')
      const allowed =
        from && from !== '/login' && (u.role === 'TEACHER' ? isTeacherPath : from.startsWith('/results'))
      navigate(allowed ? from : home, { replace: true })
    } catch (err) {
      setServerError(errorMessage(err, 'Invalid username or password'))
    }
  }

  const busy = form.formState.isSubmitting

  return (
    <div className="bg-muted/40 flex min-h-svh flex-col items-center justify-center gap-4 p-4">
      <Link to="/" className="flex items-center gap-2 font-semibold">
        <ScanLine className="size-5" />
        Answer Sheet Evaluation
      </Link>

      <Card className="w-full max-w-sm">
        <CardHeader className="space-y-1">
          <CardTitle className="text-xl">Sign in</CardTitle>
          <CardDescription>Enter your credentials to continue</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={form.handleSubmit(onSubmit)} noValidate className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="username">Username</Label>
              <Input
                id="username"
                autoComplete="username"
                autoFocus
                aria-invalid={!!form.formState.errors.username}
                {...form.register('username')}
              />
              {form.formState.errors.username && (
                <p className="text-destructive text-sm">
                  {form.formState.errors.username.message}
                </p>
              )}
            </div>

            <div className="space-y-2">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                type="password"
                autoComplete="current-password"
                aria-invalid={!!form.formState.errors.password}
                {...form.register('password')}
              />
              {form.formState.errors.password && (
                <p className="text-destructive text-sm">
                  {form.formState.errors.password.message}
                </p>
              )}
            </div>

            {serverError && (
              <Alert variant="destructive">
                <AlertDescription>{serverError}</AlertDescription>
              </Alert>
            )}

            <Button type="submit" className="w-full" disabled={busy}>
              {busy && <Loader2 className="size-4 animate-spin" />}
              Sign in
            </Button>

            <p className="text-muted-foreground text-center text-sm">
              No account yet?{' '}
              <Link to="/signup" className="text-foreground underline underline-offset-4">
                Create one
              </Link>
            </p>
          </form>

          {import.meta.env.VITE_USE_MSW === 'true' && (
            <p className="text-muted-foreground mt-4 text-center text-xs">
              Mock mode — <code className="font-mono">teacher</code> /{' '}
              <code className="font-mono">student</code>, any password
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
