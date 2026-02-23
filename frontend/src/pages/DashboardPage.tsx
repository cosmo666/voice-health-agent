import { Phone, Clock, AlertTriangle, Users } from 'lucide-react'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { useCallLogs } from '@/hooks/use-calls'
import { useAnalytics } from '@/hooks/use-analytics'
import { useDoctors } from '@/hooks/use-analytics'
import type { CallLog } from '@/lib/api'

/** Format seconds into "Xm Ys" display string. */
function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  if (m === 0) return `${s}s`
  return `${m}m ${s}s`
}

/** Produce a human-readable relative time string from an ISO timestamp. */
function timeAgo(dateString: string): string {
  const date = new Date(dateString)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffSeconds = Math.floor(diffMs / 1000)
  const diffMinutes = Math.floor(diffSeconds / 60)
  const diffHours = Math.floor(diffMinutes / 60)
  const diffDays = Math.floor(diffHours / 24)

  if (diffDays > 0) return `${diffDays} day${diffDays > 1 ? 's' : ''} ago`
  if (diffHours > 0) return `${diffHours} hour${diffHours > 1 ? 's' : ''} ago`
  if (diffMinutes > 0)
    return `${diffMinutes} minute${diffMinutes > 1 ? 's' : ''} ago`
  return 'Just now'
}

/** Return a colored badge based on sentiment score. */
function SentimentBadge({ score }: { score: number | null }) {
  if (score === null) {
    return (
      <Badge variant="secondary" className="text-xs">
        N/A
      </Badge>
    )
  }
  if (score >= 0.6) {
    return (
      <Badge className="bg-emerald-500/15 text-emerald-700 border-emerald-500/25 hover:bg-emerald-500/25 dark:text-emerald-400">
        Positive
      </Badge>
    )
  }
  if (score >= 0.3) {
    return (
      <Badge className="bg-amber-500/15 text-amber-700 border-amber-500/25 hover:bg-amber-500/25 dark:text-amber-400">
        Neutral
      </Badge>
    )
  }
  return (
    <Badge className="bg-red-500/15 text-red-700 border-red-500/25 hover:bg-red-500/25 dark:text-red-400">
      Negative
    </Badge>
  )
}

/** Loading skeleton for the metric cards row. */
function MetricCardsSkeleton() {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {Array.from({ length: 4 }).map((_, i) => (
        <Card key={i}>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <Skeleton className="h-4 w-24" />
            <Skeleton className="h-4 w-4 rounded" />
          </CardHeader>
          <CardContent>
            <Skeleton className="h-8 w-16 mb-1" />
            <Skeleton className="h-3 w-32" />
          </CardContent>
        </Card>
      ))}
    </div>
  )
}

/** Loading skeleton for the recent calls table. */
function RecentCallsSkeleton() {
  return (
    <div className="space-y-3">
      {Array.from({ length: 5 }).map((_, i) => (
        <div key={i} className="flex items-center gap-4">
          <Skeleton className="h-4 w-28" />
          <Skeleton className="h-4 w-16" />
          <Skeleton className="h-5 w-16 rounded-full" />
          <Skeleton className="h-5 w-16 rounded-full" />
          <Skeleton className="h-4 w-24 ml-auto" />
        </div>
      ))}
    </div>
  )
}

export default function DashboardPage() {
  const { data: callData, isLoading: callsLoading, error: callsError } = useCallLogs(1, 5)
  const { data: analytics, isLoading: analyticsLoading } = useAnalytics()
  const { data: doctors, isLoading: doctorsLoading } = useDoctors()

  const totalCalls = callData?.total ?? 0
  const recentCalls: CallLog[] = callData?.items ?? []

  const avgDuration =
    analytics && analytics.avg_duration.length > 0
      ? Math.round(
          analytics.avg_duration.reduce((sum, d) => sum + d.avg, 0) /
            analytics.avg_duration.length
        )
      : 0

  const escalationRate =
    analytics && analytics.escalation_rate.length > 0
      ? analytics.escalation_rate[0]?.rate ?? 0
      : 0

  const activeDoctors = doctors?.length ?? 0

  const isLoading = callsLoading || analyticsLoading || doctorsLoading

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Dashboard</h1>
        <p className="text-muted-foreground mt-1">
          Overview of Sunrise Health Clinic voice agent activity.
        </p>
      </div>

      {/* Metric Cards */}
      {isLoading ? (
        <MetricCardsSkeleton />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Total Calls</CardTitle>
              <Phone className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{totalCalls}</div>
              <CardDescription>All recorded voice interactions</CardDescription>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">
                Avg Duration
              </CardTitle>
              <Clock className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">
                {formatDuration(avgDuration)}
              </div>
              <CardDescription>Average call length</CardDescription>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">
                Escalation Rate
              </CardTitle>
              <AlertTriangle className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">
                {escalationRate.toFixed(1)}%
              </div>
              <CardDescription>Calls transferred to humans</CardDescription>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">
                Active Doctors
              </CardTitle>
              <Users className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{activeDoctors}</div>
              <CardDescription>Physicians on schedule</CardDescription>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Recent Calls */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Recent Calls</CardTitle>
          <CardDescription>
            The latest voice interactions with patients.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {callsError ? (
            <div className="text-center py-8 text-muted-foreground">
              <AlertTriangle className="h-8 w-8 mx-auto mb-2 text-destructive" />
              <p>Failed to load recent calls. Is the API server running?</p>
            </div>
          ) : callsLoading ? (
            <RecentCallsSkeleton />
          ) : recentCalls.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <Phone className="h-10 w-10 mx-auto mb-3 opacity-40" />
              <p className="text-sm font-medium">No calls recorded yet</p>
              <p className="text-xs mt-1">
                Voice interactions will appear here once patients start calling.
              </p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Phone</TableHead>
                  <TableHead>Duration</TableHead>
                  <TableHead>Sentiment</TableHead>
                  <TableHead>Escalated</TableHead>
                  <TableHead className="text-right">Time</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {recentCalls.map((call) => (
                  <TableRow key={call.id}>
                    <TableCell className="font-medium font-mono">
                      {call.patient_phone}
                    </TableCell>
                    <TableCell>{formatDuration(call.duration_seconds)}</TableCell>
                    <TableCell>
                      <SentimentBadge score={call.sentiment_score} />
                    </TableCell>
                    <TableCell>
                      {call.escalated ? (
                        <Badge className="bg-red-500/15 text-red-700 border-red-500/25 hover:bg-red-500/25 dark:text-red-400">
                          Escalated
                        </Badge>
                      ) : (
                        <Badge className="bg-emerald-500/15 text-emerald-700 border-emerald-500/25 hover:bg-emerald-500/25 dark:text-emerald-400">
                          Resolved
                        </Badge>
                      )}
                    </TableCell>
                    <TableCell className="text-right text-muted-foreground text-sm">
                      {timeAgo(call.created_at)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
