import { Link, useParams } from 'react-router-dom'
import {
  Bar,
  BarChart,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip as RechartsTooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { Sparkles } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Empty } from '@/components/states/Empty'
import { ErrorState } from '@/components/states/ErrorState'
import { Loading } from '@/components/states/Loading'
import { useExamSummary } from '@/hooks/useExams'

/**
 * Class analytics (§8 screen 9). Lazy-loaded from router.tsx — recharts is the
 * heaviest dependency in the app and is used on this screen only.
 *
 * The concept miss-rate chart is the one a real teacher would act on: it says
 * "34 of 58 students missed the superkey condition", which is a lecture to
 * re-teach, not a number to file.
 */

const BAND_COLOR = { green: '#16a34a', orange: '#d97706', red: '#dc2626' }

export function ExamSummary() {
  const examId = Number(useParams().examId)
  const { data, isPending, error, refetch } = useExamSummary(examId)

  if (isPending) return <Loading label="Loading analytics…" />
  if (error) return <ErrorState error={error} onRetry={() => void refetch()} />
  if (!data) return null

  if (data.sheet_count === 0) {
    return (
      <div className="space-y-4">
        <Link to={`/exams/${examId}`} className="text-muted-foreground text-sm hover:underline">
          ← Back to exam
        </Link>
        <Empty title="Nothing to analyse yet" hint="Upload and evaluate some sheets first." />
      </div>
    )
  }

  const bandData = [
    { name: 'High confidence', value: data.bands.green, fill: BAND_COLOR.green },
    { name: 'Needs a look', value: data.bands.orange, fill: BAND_COLOR.orange },
    { name: 'Review required', value: data.bands.red, fill: BAND_COLOR.red },
  ].filter((d) => d.value > 0)

  // Worst first — the chart should lead with what to re-teach.
  const missData = data.concept_miss_rate
    .slice(0, 8)
    .map((c) => ({ ...c, short: c.concept.length > 42 ? `${c.concept.slice(0, 40)}…` : c.concept }))

  return (
    <div className="space-y-6">
      <div>
        <Link to={`/exams/${examId}`} className="text-muted-foreground text-sm hover:underline">
          ← Back to exam
        </Link>
        <h1 className="mt-1 text-2xl font-semibold">Class analytics</h1>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Sheets evaluated" value={String(data.sheet_count)} />
        <Stat label="Approved" value={`${data.approved_count} / ${data.sheet_count}`} />
        <Stat label="Average confidence" value={`${(data.avg_confidence * 100).toFixed(0)}%`} />
        <Stat
          label="VLM escalation rate"
          value={`${(data.vlm_escalation_rate * 100).toFixed(0)}%`}
          hint="blocks the CV layer could not resolve alone"
          icon
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="text-base">Mark distribution</CardTitle>
            <CardDescription>How the class scored overall</CardDescription>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={data.mark_distribution}>
                <XAxis dataKey="bucket" tickLine={false} axisLine={false} fontSize={12} />
                <YAxis allowDecimals={false} tickLine={false} axisLine={false} fontSize={12} />
                <RechartsTooltip
                  cursor={{ fill: 'rgba(0,0,0,0.04)' }}
                  contentStyle={{ fontSize: 12, borderRadius: 8 }}
                />
                <Bar dataKey="count" fill="#2563eb" radius={[4, 4, 0, 0]} name="Students" />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Confidence bands</CardTitle>
            <CardDescription>How much human review was needed</CardDescription>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={240}>
              <PieChart>
                <Pie
                  data={bandData}
                  dataKey="value"
                  nameKey="name"
                  innerRadius={50}
                  outerRadius={80}
                  paddingAngle={2}
                >
                  {bandData.map((entry) => (
                    <Cell key={entry.name} fill={entry.fill} />
                  ))}
                </Pie>
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <RechartsTooltip contentStyle={{ fontSize: 12, borderRadius: 8 }} />
              </PieChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Most-missed concepts</CardTitle>
          <CardDescription>
            Sorted worst first. A tall red bar is a concept to re-teach, not a student to fail.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={Math.max(240, missData.length * 46)}>
            <BarChart data={missData} layout="vertical" margin={{ left: 8, right: 16 }}>
              <XAxis type="number" allowDecimals={false} tickLine={false} axisLine={false} fontSize={12} />
              <YAxis
                type="category"
                dataKey="short"
                width={220}
                tickLine={false}
                axisLine={false}
                fontSize={11}
              />
              <RechartsTooltip
                cursor={{ fill: 'rgba(0,0,0,0.04)' }}
                contentStyle={{ fontSize: 12, borderRadius: 8 }}
              />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Bar dataKey="missing" stackId="a" fill={BAND_COLOR.red} name="Missing" />
              <Bar dataKey="partial" stackId="a" fill={BAND_COLOR.orange} name="Partial" />
              <Bar
                dataKey="covered"
                stackId="a"
                fill={BAND_COLOR.green}
                name="Covered"
                radius={[0, 4, 4, 0]}
              />
            </BarChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>
    </div>
  )
}

function Stat({
  label,
  value,
  hint,
  icon,
}: {
  label: string
  value: string
  hint?: string
  icon?: boolean
}) {
  return (
    <Card>
      <CardContent className="py-1">
        <p className="text-muted-foreground flex items-center gap-1.5 text-xs">
          {icon && <Sparkles className="size-3 text-violet-500" />}
          {label}
        </p>
        <p className="mt-1 font-mono text-2xl font-semibold">{value}</p>
        {hint && <p className="text-muted-foreground mt-0.5 text-xs">{hint}</p>}
      </CardContent>
    </Card>
  )
}
