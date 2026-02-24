import { useState, useCallback } from 'react'
import {
  Search,
  ChevronLeft,
  ChevronRight,
  Phone,
  AlertTriangle,
  FileText,
  Brain,
  Globe,
  Target,
  CheckCircle2,
  Clock,
  Lightbulb,
  Star,
  TrendingUp,
} from 'lucide-react'
import {
  Card,
  CardContent,
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
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Separator } from '@/components/ui/separator'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useCallLogs } from '@/hooks/use-calls'
import type { CallLog, AIInsights } from '@/lib/api'

const PER_PAGE = 20

/** Format seconds into "Xm Ys" display string. */
function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  if (m === 0) return `${s}s`
  return `${m}m ${s}s`
}

/** Format ISO date string into readable date. */
function formatDate(dateString: string): string {
  const date = new Date(dateString)
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
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

/** Badge for resolution status. */
function ResolutionBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    resolved:
      'bg-emerald-500/15 text-emerald-700 border-emerald-500/25 dark:text-emerald-400',
    partially_resolved:
      'bg-amber-500/15 text-amber-700 border-amber-500/25 dark:text-amber-400',
    unresolved:
      'bg-red-500/15 text-red-700 border-red-500/25 dark:text-red-400',
    escalated:
      'bg-purple-500/15 text-purple-700 border-purple-500/25 dark:text-purple-400',
  }
  const labels: Record<string, string> = {
    resolved: 'Resolved',
    partially_resolved: 'Partially Resolved',
    unresolved: 'Unresolved',
    escalated: 'Escalated',
  }
  return (
    <Badge className={colors[status] ?? colors.unresolved}>
      {labels[status] ?? status}
    </Badge>
  )
}

/** Badge for performance ratings. */
function RatingBadge({ rating }: { rating: string }) {
  const colors: Record<string, string> = {
    excellent:
      'bg-emerald-500/15 text-emerald-700 border-emerald-500/25 dark:text-emerald-400',
    good: 'bg-blue-500/15 text-blue-700 border-blue-500/25 dark:text-blue-400',
    high: 'bg-emerald-500/15 text-emerald-700 border-emerald-500/25 dark:text-emerald-400',
    medium:
      'bg-amber-500/15 text-amber-700 border-amber-500/25 dark:text-amber-400',
    fair: 'bg-amber-500/15 text-amber-700 border-amber-500/25 dark:text-amber-400',
    low: 'bg-red-500/15 text-red-700 border-red-500/25 dark:text-red-400',
    poor: 'bg-red-500/15 text-red-700 border-red-500/25 dark:text-red-400',
  }
  return (
    <Badge className={colors[rating] ?? 'bg-muted text-muted-foreground'}>
      {rating.charAt(0).toUpperCase() + rating.slice(1)}
    </Badge>
  )
}

/** AI Insights panel displayed inside the call detail dialog. */
function AIInsightsPanel({ insights }: { insights: AIInsights }) {
  return (
    <div className="space-y-4">
      {/* Intent & Resolution Row */}
      <div className="grid grid-cols-2 gap-4">
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center gap-2 mb-2">
              <Target className="h-4 w-4 text-blue-500" />
              <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                Patient Intent
              </span>
            </div>
            <p className="text-sm">{insights.patient_intent}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center gap-2 mb-2">
              <CheckCircle2 className="h-4 w-4 text-emerald-500" />
              <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                Resolution
              </span>
            </div>
            <div className="flex items-center gap-2">
              <ResolutionBadge status={insights.resolution_status} />
              <span className="text-xs text-muted-foreground">
                Satisfaction:{' '}
                <RatingBadge rating={insights.patient_satisfaction} />
              </span>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Topics & Language */}
      <div className="grid grid-cols-2 gap-4">
        <div>
          <div className="flex items-center gap-2 mb-2">
            <Brain className="h-4 w-4 text-purple-500" />
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
              Topics Discussed
            </span>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {insights.topics.map((topic) => (
              <Badge key={topic} variant="outline" className="text-xs">
                {topic}
              </Badge>
            ))}
          </div>
        </div>
        <div>
          <div className="flex items-center gap-2 mb-2">
            <Globe className="h-4 w-4 text-teal-500" />
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
              Language
            </span>
          </div>
          <Badge variant="secondary">
            {insights.language_detected.charAt(0).toUpperCase() +
              insights.language_detected.slice(1)}
          </Badge>
        </div>
      </div>

      {/* Key Moments */}
      {insights.key_moments && insights.key_moments.length > 0 && (
        <div>
          <div className="flex items-center gap-2 mb-2">
            <Clock className="h-4 w-4 text-orange-500" />
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
              Key Moments
            </span>
          </div>
          <div className="space-y-1.5">
            {insights.key_moments.map((moment, i) => (
              <div
                key={i}
                className="flex items-start gap-2 text-sm"
              >
                <span className="text-xs font-mono text-muted-foreground min-w-[60px]">
                  {moment.timestamp}
                </span>
                <span>{moment.event}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Action Items */}
      {insights.action_items && insights.action_items.length > 0 && (
        <div>
          <div className="flex items-center gap-2 mb-2">
            <TrendingUp className="h-4 w-4 text-blue-500" />
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
              Action Items
            </span>
          </div>
          <ul className="space-y-1">
            {insights.action_items.map((item, i) => (
              <li key={i} className="flex items-start gap-2 text-sm">
                <span className="text-muted-foreground mt-0.5">-</span>
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <Separator />

      {/* Agent Performance */}
      {insights.agent_performance && (
        <div>
          <div className="flex items-center gap-2 mb-3">
            <Star className="h-4 w-4 text-yellow-500" />
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
              Agent Performance
            </span>
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div className="text-center">
              <p className="text-xs text-muted-foreground mb-1">
                Response Quality
              </p>
              <RatingBadge
                rating={insights.agent_performance.response_quality}
              />
            </div>
            <div className="text-center">
              <p className="text-xs text-muted-foreground mb-1">Empathy</p>
              <RatingBadge
                rating={insights.agent_performance.empathy_score}
              />
            </div>
            <div className="text-center">
              <p className="text-xs text-muted-foreground mb-1">Accuracy</p>
              <RatingBadge rating={insights.agent_performance.accuracy} />
            </div>
          </div>
          {insights.agent_performance.areas_for_improvement &&
            insights.agent_performance.areas_for_improvement.length > 0 && (
              <div className="mt-3">
                <p className="text-xs text-muted-foreground mb-1">
                  Areas for Improvement:
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {insights.agent_performance.areas_for_improvement.map(
                    (area, i) => (
                      <Badge
                        key={i}
                        variant="outline"
                        className="text-xs border-amber-500/25 text-amber-700 dark:text-amber-400"
                      >
                        {area}
                      </Badge>
                    )
                  )}
                </div>
              </div>
            )}
        </div>
      )}

      {/* Recommendations */}
      {insights.recommendations && insights.recommendations.length > 0 && (
        <div>
          <div className="flex items-center gap-2 mb-2">
            <Lightbulb className="h-4 w-4 text-yellow-500" />
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
              Recommendations
            </span>
          </div>
          <ul className="space-y-1">
            {insights.recommendations.map((rec, i) => (
              <li key={i} className="flex items-start gap-2 text-sm">
                <span className="text-muted-foreground mt-0.5">-</span>
                <span>{rec}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

/** Loading skeleton rows for the call log table. */
function TableSkeleton() {
  return (
    <>
      {Array.from({ length: 8 }).map((_, i) => (
        <TableRow key={i}>
          <TableCell><Skeleton className="h-4 w-28" /></TableCell>
          <TableCell><Skeleton className="h-4 w-14" /></TableCell>
          <TableCell><Skeleton className="h-5 w-16 rounded-full" /></TableCell>
          <TableCell><Skeleton className="h-5 w-16 rounded-full" /></TableCell>
          <TableCell><Skeleton className="h-4 w-20" /></TableCell>
          <TableCell><Skeleton className="h-4 w-32" /></TableCell>
        </TableRow>
      ))}
    </>
  )
}

export default function CallLogsPage() {
  const [page, setPage] = useState(1)
  const [phoneFilter, setPhoneFilter] = useState('')
  const [searchInput, setSearchInput] = useState('')
  const [selectedCall, setSelectedCall] = useState<CallLog | null>(null)

  const { data, isLoading, error } = useCallLogs(
    page,
    PER_PAGE,
    phoneFilter || undefined
  )

  const handleSearch = useCallback(() => {
    setPhoneFilter(searchInput.trim())
    setPage(1)
  }, [searchInput])

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter') handleSearch()
    },
    [handleSearch]
  )

  const handleClearSearch = useCallback(() => {
    setSearchInput('')
    setPhoneFilter('')
    setPage(1)
  }, [])

  const totalPages = data?.pages ?? 1

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Call Logs</h1>
        <p className="text-muted-foreground mt-1">
          Browse and search all recorded voice interactions with AI-powered
          insights.
        </p>
      </div>

      {/* Search Bar */}
      <div className="flex gap-2">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Filter by phone number..."
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            onKeyDown={handleKeyDown}
            className="pl-9"
          />
        </div>
        <Button onClick={handleSearch} variant="secondary">
          Search
        </Button>
        {phoneFilter && (
          <Button onClick={handleClearSearch} variant="ghost">
            Clear
          </Button>
        )}
      </div>

      {/* Call Logs Table */}
      <Card>
        <CardContent className="p-0">
          {error ? (
            <div className="text-center py-12 text-muted-foreground">
              <AlertTriangle className="h-8 w-8 mx-auto mb-2 text-destructive" />
              <p>Failed to load call logs. Is the API server running?</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Phone</TableHead>
                  <TableHead>Duration</TableHead>
                  <TableHead>Sentiment</TableHead>
                  <TableHead>Escalated</TableHead>
                  <TableHead>Tools Used</TableHead>
                  <TableHead>Date</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {isLoading ? (
                  <TableSkeleton />
                ) : data && data.items.length > 0 ? (
                  data.items.map((call) => (
                    <TableRow
                      key={call.id}
                      className="cursor-pointer"
                      onClick={() => setSelectedCall(call)}
                    >
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
                      <TableCell>
                        <div className="flex flex-wrap gap-1">
                          {call.tools_used.length > 0 ? (
                            call.tools_used.map((tool) => (
                              <Badge
                                key={tool}
                                variant="outline"
                                className="text-xs"
                              >
                                {tool}
                              </Badge>
                            ))
                          ) : (
                            <span className="text-muted-foreground text-xs">
                              None
                            </span>
                          )}
                        </div>
                      </TableCell>
                      <TableCell className="text-muted-foreground text-sm">
                        {formatDate(call.created_at)}
                      </TableCell>
                    </TableRow>
                  ))
                ) : (
                  <TableRow>
                    <TableCell colSpan={6}>
                      <div className="text-center py-12 text-muted-foreground">
                        <Phone className="h-10 w-10 mx-auto mb-3 opacity-40" />
                        <p className="text-sm font-medium">No calls found</p>
                        <p className="text-xs mt-1">
                          {phoneFilter
                            ? `No results for "${phoneFilter}". Try a different phone number.`
                            : 'Voice interactions will appear here once patients start calling.'}
                        </p>
                      </div>
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Pagination */}
      {data && data.pages > 1 && (
        <div className="flex items-center justify-between">
          <p className="text-sm text-muted-foreground">
            Showing {(page - 1) * PER_PAGE + 1} to{' '}
            {Math.min(page * PER_PAGE, data.total)} of {data.total} calls
          </p>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page <= 1}
            >
              <ChevronLeft className="h-4 w-4 mr-1" />
              Previous
            </Button>
            <span className="text-sm text-muted-foreground px-2">
              Page {page} of {totalPages}
            </span>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page >= totalPages}
            >
              Next
              <ChevronRight className="h-4 w-4 ml-1" />
            </Button>
          </div>
        </div>
      )}

      {/* Call Detail Dialog */}
      <Dialog
        open={selectedCall !== null}
        onOpenChange={(open) => {
          if (!open) setSelectedCall(null)
        }}
      >
        {selectedCall && (
          <DialogContent className="max-w-3xl max-h-[85vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <FileText className="h-5 w-5" />
                Call Detail
              </DialogTitle>
              <DialogDescription>
                {selectedCall.patient_phone} &mdash;{' '}
                {formatDate(selectedCall.created_at)}
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-4">
              {/* Metadata Row */}
              <div className="flex flex-wrap gap-3">
                <div className="flex items-center gap-1.5">
                  <span className="text-xs text-muted-foreground">Duration:</span>
                  <span className="text-sm font-medium">
                    {formatDuration(selectedCall.duration_seconds)}
                  </span>
                </div>
                <div className="flex items-center gap-1.5">
                  <span className="text-xs text-muted-foreground">Sentiment:</span>
                  <SentimentBadge score={selectedCall.sentiment_score} />
                </div>
                <div className="flex items-center gap-1.5">
                  <span className="text-xs text-muted-foreground">Status:</span>
                  {selectedCall.escalated ? (
                    <Badge className="bg-red-500/15 text-red-700 border-red-500/25 dark:text-red-400">
                      Escalated
                    </Badge>
                  ) : (
                    <Badge className="bg-emerald-500/15 text-emerald-700 border-emerald-500/25 dark:text-emerald-400">
                      Resolved
                    </Badge>
                  )}
                </div>
                {selectedCall.ai_insights && (
                  <div className="flex items-center gap-1.5">
                    <span className="text-xs text-muted-foreground">
                      Language:
                    </span>
                    <Badge variant="secondary" className="text-xs">
                      {selectedCall.ai_insights.language_detected}
                    </Badge>
                  </div>
                )}
              </div>

              {/* Tools Used */}
              {selectedCall.tools_used.length > 0 && (
                <div>
                  <h4 className="text-sm font-medium mb-2">Tools Used</h4>
                  <div className="flex flex-wrap gap-1.5">
                    {selectedCall.tools_used.map((tool) => (
                      <Badge key={tool} variant="outline">
                        {tool}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}

              <Separator />

              {/* Tabbed Content: AI Insights | Summary | Transcript */}
              <Tabs
                defaultValue={selectedCall.ai_insights ? 'insights' : 'transcript'}
                className="w-full"
              >
                <TabsList className="grid w-full grid-cols-3">
                  <TabsTrigger
                    value="insights"
                    className="flex items-center gap-1.5"
                    disabled={!selectedCall.ai_insights}
                  >
                    <Brain className="h-3.5 w-3.5" />
                    AI Insights
                  </TabsTrigger>
                  <TabsTrigger
                    value="summary"
                    className="flex items-center gap-1.5"
                  >
                    <FileText className="h-3.5 w-3.5" />
                    Summary
                  </TabsTrigger>
                  <TabsTrigger
                    value="transcript"
                    className="flex items-center gap-1.5"
                  >
                    <Phone className="h-3.5 w-3.5" />
                    Transcript
                  </TabsTrigger>
                </TabsList>

                {/* AI Insights Tab */}
                <TabsContent value="insights" className="mt-4">
                  {selectedCall.ai_insights ? (
                    <AIInsightsPanel insights={selectedCall.ai_insights} />
                  ) : (
                    <Card>
                      <CardContent className="p-8 text-center text-muted-foreground">
                        <Brain className="h-8 w-8 mx-auto mb-2 opacity-40" />
                        <p className="text-sm">
                          AI insights are being generated. Check back in a
                          moment.
                        </p>
                      </CardContent>
                    </Card>
                  )}
                </TabsContent>

                {/* Summary Tab */}
                <TabsContent value="summary" className="mt-4">
                  {selectedCall.summary ? (
                    <Card>
                      <CardContent className="p-4">
                        <p className="text-sm leading-relaxed">
                          {selectedCall.summary}
                        </p>
                      </CardContent>
                    </Card>
                  ) : (
                    <Card>
                      <CardContent className="p-8 text-center text-muted-foreground">
                        <p className="text-sm">
                          Summary is being generated...
                        </p>
                      </CardContent>
                    </Card>
                  )}
                </TabsContent>

                {/* Transcript Tab */}
                <TabsContent value="transcript" className="mt-4">
                  <Card>
                    <CardContent className="p-4">
                      <pre className="text-sm whitespace-pre-wrap leading-relaxed font-mono text-muted-foreground">
                        {selectedCall.transcript || 'No transcript available.'}
                      </pre>
                    </CardContent>
                  </Card>
                </TabsContent>
              </Tabs>
            </div>
          </DialogContent>
        )}
      </Dialog>
    </div>
  )
}
