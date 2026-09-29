import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { ProtectedRoute } from '@/auth/ProtectedRoute'
import { HOME_FOR_ROLE } from '@/auth/AuthContext'
import { useAuth } from '@/auth/useAuth'
import { TeacherShell } from '@/components/layout/TeacherShell'
import { StudentShell } from '@/components/layout/StudentShell'
import { Loading } from '@/components/states/Loading'
import { Landing } from '@/pages/Landing'
import { Login } from '@/pages/Login'
import { Signup } from '@/pages/Signup'
import { ExamList } from '@/pages/teacher/ExamList'
import { ExamDetail } from '@/pages/teacher/ExamDetail'
import { QuestionEditor } from '@/pages/teacher/QuestionEditor'
import { StudentManage } from '@/pages/teacher/StudentManage'
import { SheetUpload } from '@/pages/teacher/SheetUpload'
import { ReviewQueue } from '@/pages/teacher/ReviewQueue'
import { ReviewDetail } from '@/pages/teacher/ReviewDetail'
import { ResultList } from '@/pages/student/ResultList'
import { ResultDetail } from '@/pages/student/ResultDetail'

// Recharts is ~100 kB gzipped and used on exactly one screen (§12) — keep it
// out of the main bundle so the review screen loads fast.
const ExamSummary = lazy(() =>
  import('@/pages/teacher/ExamSummary').then((m) => ({ default: m.ExamSummary })),
)

/**
 * Fallback for unknown paths: signed-in users go to their own home, everyone
 * else to the public landing page.
 *
 * `/` itself deliberately does NOT redirect — the landing page is public and
 * stays reachable while signed in (it just swaps its CTAs for a dashboard link).
 * Bouncing a logged-in user off the homepage would make the project description
 * unreachable to exactly the people demoing it.
 */
function RoleRedirect() {
  const { user, isLoading } = useAuth()
  if (isLoading) return <Loading />
  return <Navigate to={user ? HOME_FOR_ROLE[user.role] : '/'} replace />
}

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/login" element={<Login />} />
      <Route path="/signup" element={<Signup />} />

      {/* ── Teacher ─────────────────────────────────────────────────── */}
      <Route
        element={
          <ProtectedRoute requiredRole="TEACHER">
            <TeacherShell />
          </ProtectedRoute>
        }
      >
        <Route path="/exams" element={<ExamList />} />
        <Route path="/exams/:examId" element={<ExamDetail />} />
        <Route path="/exams/:examId/questions" element={<QuestionEditor />} />
        <Route path="/exams/:examId/students" element={<StudentManage />} />
        <Route path="/exams/:examId/upload" element={<SheetUpload />} />
        <Route path="/exams/:examId/review" element={<ReviewQueue />} />
        <Route
          path="/exams/:examId/summary"
          element={
            <Suspense fallback={<Loading label="Loading charts…" />}>
              <ExamSummary />
            </Suspense>
          }
        />
        <Route path="/sheets/:sheetId" element={<ReviewDetail />} />
      </Route>

      {/* ── Student ─────────────────────────────────────────────────── */}
      <Route
        element={
          <ProtectedRoute requiredRole="STUDENT">
            <StudentShell />
          </ProtectedRoute>
        }
      >
        <Route path="/results" element={<ResultList />} />
        <Route path="/results/:sheetId" element={<ResultDetail />} />
      </Route>

      <Route path="*" element={<RoleRedirect />} />
    </Routes>
  )
}
