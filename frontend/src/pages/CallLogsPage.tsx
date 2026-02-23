import { useState, useCallback } from 'react'
import { Search, ChevronLeft, ChevronRight, Phone, AlertTriangle, FileText } from 'lucide-react'
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
import { useCallLogs } from '@/hooks/use-calls'
import type { CallLog } from '@/lib/api'

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
          Browse and search all recorded voice interactions.
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
          <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
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

              {/* Summary */}
              {selectedCall.summary && (
                <div>
                  <h4 className="text-sm font-medium mb-2">Summary</h4>
                  <Card>
                    <CardContent className="p-4">
                      <p className="text-sm leading-relaxed">
                        {selectedCall.summary}
                      </p>
                    </CardContent>
                  </Card>
                </div>
              )}

              {/* Transcript */}
              <div>
                <h4 className="text-sm font-medium mb-2">Transcript</h4>
                <Card>
                  <CardContent className="p-4">
                    <pre className="text-sm whitespace-pre-wrap leading-relaxed font-mono text-muted-foreground">
                      {selectedCall.transcript || 'No transcript available.'}
                    </pre>
                  </CardContent>
                </Card>
              </div>
            </div>
          </DialogContent>
        )}
      </Dialog>
    </div>
  )
}
