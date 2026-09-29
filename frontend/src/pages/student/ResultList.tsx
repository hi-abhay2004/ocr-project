import { Link } from 'react-router-dom'
import { GraduationCap } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Empty } from '@/components/states/Empty'
import { ErrorState } from '@/components/states/ErrorState'
import { Loading } from '@/components/states/Loading'
import { useStudentResults } from '@/hooks/useStudentResults'

export function ResultList() {
  const { data: results, isPending, error, refetch } = useStudentResults()

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">My results</h1>
        <p className="text-muted-foreground text-sm">
          Results appear here once your teacher has reviewed and published them.
        </p>
      </div>

      {isPending && <Loading />}
      {error && <ErrorState error={error} onRetry={() => void refetch()} />}

      {results && results.length === 0 && (
        <Empty
          icon={GraduationCap}
          title="No results published yet"
          hint="Your teacher reviews every evaluated sheet before publishing it. Check back later."
        />
      )}

      <div className="space-y-3">
        {results?.map((result) => {
          const percent = (result.total_marks / result.max_marks) * 100
          return (
            <Link key={result.sheet_id} to={`/results/${result.sheet_id}`} className="block">
              <Card className="hover:border-primary/50 transition-colors">
                <CardContent className="flex flex-wrap items-center justify-between gap-4">
                  <div>
                    <p className="font-medium">{result.exam_name}</p>
                    <p className="text-muted-foreground text-sm">
                      {result.subject} · {result.exam_date}
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="font-mono text-2xl font-semibold">
                      {result.total_marks}
                      <span className="text-muted-foreground text-base"> / {result.max_marks}</span>
                    </p>
                    <p className="text-muted-foreground text-xs">{percent.toFixed(0)}%</p>
                  </div>
                </CardContent>
              </Card>
            </Link>
          )
        })}
      </div>
    </div>
  )
}
