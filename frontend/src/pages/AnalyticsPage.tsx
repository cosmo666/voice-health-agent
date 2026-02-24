import {
  AlertTriangle,
  Brain,
  Globe,
  CheckCircle2,
  Star,
  Lightbulb,
  TrendingUp,
  MessageSquare,
} from 'lucide-react'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import { Skeleton } from '@/components/ui/skeleton'
import { useAnalytics } from '@/hooks/use-analytics'
import type { InsightsAggregate } from '@/lib/api'
import {
  BarChart,
  Bar,
  LineChart,
  Line,
  PieChart,
  Pie,
  Cell,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts'

/** Color palette for charts. */
const COLORS = {
  blue: 'hsl(221, 83%, 53%)',
  green: 'hsl(142, 71%, 45%)',
  amber: 'hsl(38, 92%, 50%)',
  red: 'hsl(0, 72%, 51%)',
  purple: 'hsl(262, 83%, 58%)',
  teal: 'hsl(172, 66%, 50%)',
}

/** Sentiment pie chart colors. */
const SENTIMENT_COLORS = [COLORS.green, COLORS.amber, COLORS.red]

/** Resolution status colors for pie chart. */
const RESOLUTION_COLORS = [COLORS.green, COLORS.amber, COLORS.red, COLORS.purple]

/** Language pie chart colors. */
const LANGUAGE_COLORS = [COLORS.blue, COLORS.teal, COLORS.purple]

/** Chart skeleton loader. */
function ChartSkeleton() {
  return (
    <div className="space-y-3 p-4">
      <Skeleton className="h-4 w-32" />
      <Skeleton className="h-[200px] w-full rounded-md" />
    </div>
  )
}

/** Display aggregate AI insights from all analyzed calls. */
function InsightsSection({ insights }: { insights: InsightsAggregate }) {
  return (
    <div className="space-y-6">
      {/* Section Header */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2">
          <Brain className="h-5 w-5 text-purple-500" />
          <h2 className="text-xl font-semibold">AI Speech Insights</h2>
        </div>
        <Badge variant="secondary" className="text-xs">
          {insights.calls_with_insights} call{insights.calls_with_insights !== 1 ? 's' : ''} analyzed
        </Badge>
        <Badge className="bg-purple-500/15 text-purple-700 border-purple-500/25 dark:text-purple-400 text-xs">
          Powered by qwen3-next:80b
        </Badge>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        {/* Top Topics — Horizontal Bar Chart */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base flex items-center gap-2">
              <MessageSquare className="h-4 w-4 text-blue-500" />
              Top Discussion Topics
            </CardTitle>
            <CardDescription>
              Most frequently discussed subjects across all calls
            </CardDescription>
          </CardHeader>
          <CardContent>
            {insights.top_topics.length > 0 ? (
              <ResponsiveContainer width="100%" height={260}>
                <BarChart
                  data={insights.top_topics}
                  layout="vertical"
                  margin={{ top: 5, right: 10, left: 20, bottom: 5 }}
                >
                  <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                  <XAxis type="number" tick={{ fontSize: 12 }} allowDecimals={false} />
                  <YAxis
                    type="category"
                    dataKey="topic"
                    tick={{ fontSize: 11 }}
                    width={130}
                  />
                  <RechartsTooltip
                    contentStyle={{
                      backgroundColor: 'hsl(var(--card))',
                      border: '1px solid hsl(var(--border))',
                      borderRadius: '8px',
                      fontSize: '12px',
                    }}
                  />
                  <Bar
                    dataKey="count"
                    fill={COLORS.blue}
                    radius={[0, 4, 4, 0]}
                    name="Mentions"
                  />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex items-center justify-center h-[260px] text-muted-foreground text-sm">
                No topic data yet.
              </div>
            )}
          </CardContent>
        </Card>

        {/* Resolution Status — Pie Chart */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base flex items-center gap-2">
              <CheckCircle2 className="h-4 w-4 text-emerald-500" />
              Resolution Status
            </CardTitle>
            <CardDescription>
              How effectively were patient issues resolved?
            </CardDescription>
          </CardHeader>
          <CardContent>
            {insights.resolution_breakdown.length > 0 ? (
              <ResponsiveContainer width="100%" height={260}>
                <PieChart>
                  <Pie
                    data={insights.resolution_breakdown}
                    cx="50%"
                    cy="50%"
                    innerRadius={55}
                    outerRadius={90}
                    paddingAngle={3}
                    dataKey="count"
                    nameKey="status"
                    label={({
                      status,
                      percent,
                    }: {
                      status: string
                      percent: number
                    }) => `${status} ${(percent * 100).toFixed(0)}%`}
                    labelLine={false}
                  >
                    {insights.resolution_breakdown.map((_entry, index) => (
                      <Cell
                        key={`cell-${index}`}
                        fill={RESOLUTION_COLORS[index % RESOLUTION_COLORS.length]}
                      />
                    ))}
                  </Pie>
                  <RechartsTooltip
                    contentStyle={{
                      backgroundColor: 'hsl(var(--card))',
                      border: '1px solid hsl(var(--border))',
                      borderRadius: '8px',
                      fontSize: '12px',
                    }}
                  />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex items-center justify-center h-[260px] text-muted-foreground text-sm">
                No resolution data yet.
              </div>
            )}
          </CardContent>
        </Card>

        {/* Language Distribution — Pie Chart */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base flex items-center gap-2">
              <Globe className="h-4 w-4 text-teal-500" />
              Language Distribution
            </CardTitle>
            <CardDescription>
              Languages used by patients across calls
            </CardDescription>
          </CardHeader>
          <CardContent>
            {insights.language_breakdown.length > 0 ? (
              <ResponsiveContainer width="100%" height={260}>
                <PieChart>
                  <Pie
                    data={insights.language_breakdown}
                    cx="50%"
                    cy="50%"
                    innerRadius={55}
                    outerRadius={90}
                    paddingAngle={3}
                    dataKey="count"
                    nameKey="language"
                    label={({
                      language,
                      percent,
                    }: {
                      language: string
                      percent: number
                    }) => `${language} ${(percent * 100).toFixed(0)}%`}
                    labelLine={false}
                  >
                    {insights.language_breakdown.map((_entry, index) => (
                      <Cell
                        key={`cell-${index}`}
                        fill={LANGUAGE_COLORS[index % LANGUAGE_COLORS.length]}
                      />
                    ))}
                  </Pie>
                  <RechartsTooltip
                    contentStyle={{
                      backgroundColor: 'hsl(var(--card))',
                      border: '1px solid hsl(var(--border))',
                      borderRadius: '8px',
                      fontSize: '12px',
                    }}
                  />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex items-center justify-center h-[260px] text-muted-foreground text-sm">
                No language data yet.
              </div>
            )}
          </CardContent>
        </Card>

        {/* Agent Performance Summary */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base flex items-center gap-2">
              <Star className="h-4 w-4 text-yellow-500" />
              Agent Performance
            </CardTitle>
            <CardDescription>
              Overall AI agent quality metrics
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex flex-col items-center justify-center h-[260px]">
              {(() => {
                const quality = insights.avg_agent_quality
                const color =
                  quality === 'excellent'
                    ? 'text-emerald-500'
                    : quality === 'good'
                      ? 'text-blue-500'
                      : quality === 'fair'
                        ? 'text-amber-500'
                        : quality === 'poor'
                          ? 'text-red-500'
                          : 'text-muted-foreground'
                return (
                  <>
                    <div className={`text-4xl font-bold tracking-tight ${color}`}>
                      {quality.charAt(0).toUpperCase() + quality.slice(1)}
                    </div>
                    <p className="text-sm text-muted-foreground mt-2">
                      Average Response Quality
                    </p>

                    {/* Patient Satisfaction Breakdown */}
                    {insights.satisfaction_breakdown.length > 0 && (
                      <div className="mt-6 w-full max-w-xs">
                        <p className="text-xs text-muted-foreground mb-2 text-center">
                          Patient Satisfaction
                        </p>
                        <div className="flex gap-2 justify-center">
                          {insights.satisfaction_breakdown.map((s) => (
                            <Badge
                              key={s.level}
                              variant="outline"
                              className={
                                s.level === 'high'
                                  ? 'border-emerald-500/25 text-emerald-700 dark:text-emerald-400'
                                  : s.level === 'medium'
                                    ? 'border-amber-500/25 text-amber-700 dark:text-amber-400'
                                    : 'border-red-500/25 text-red-700 dark:text-red-400'
                              }
                            >
                              {s.level}: {s.count}
                            </Badge>
                          ))}
                        </div>
                      </div>
                    )}
                  </>
                )
              })()}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Action Items & Recommendations — Full Width */}
      <div className="grid gap-6 md:grid-cols-2">
        {/* Action Items */}
        {insights.common_action_items.length > 0 && (
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base flex items-center gap-2">
                <TrendingUp className="h-4 w-4 text-blue-500" />
                Common Action Items
              </CardTitle>
              <CardDescription>
                Follow-up tasks identified across recent calls
              </CardDescription>
            </CardHeader>
            <CardContent>
              <ul className="space-y-2">
                {insights.common_action_items.map((item, i) => (
                  <li
                    key={i}
                    className="flex items-start gap-2 text-sm"
                  >
                    <span className="text-blue-500 mt-0.5 text-xs">-</span>
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        )}

        {/* Recommendations */}
        {insights.common_recommendations.length > 0 && (
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base flex items-center gap-2">
                <Lightbulb className="h-4 w-4 text-yellow-500" />
                AI Recommendations
              </CardTitle>
              <CardDescription>
                Suggestions for improving clinic operations
              </CardDescription>
            </CardHeader>
            <CardContent>
              <ul className="space-y-2">
                {insights.common_recommendations.map((rec, i) => (
                  <li
                    key={i}
                    className="flex items-start gap-2 text-sm"
                  >
                    <span className="text-yellow-500 mt-0.5 text-xs">-</span>
                    <span>{rec}</span>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  )
}

export default function AnalyticsPage() {
  const { data: analytics, isLoading, error } = useAnalytics()

  if (error) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Analytics</h1>
          <p className="text-muted-foreground mt-1">
            Visualize voice agent performance metrics and AI-powered speech
            insights.
          </p>
        </div>
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-16">
            <AlertTriangle className="h-10 w-10 text-destructive mb-3" />
            <p className="text-muted-foreground">
              Failed to load analytics data. Is the API server running?
            </p>
          </CardContent>
        </Card>
      </div>
    )
  }

  const hasData = analytics && analytics.calls_per_day.length > 0

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Analytics</h1>
        <p className="text-muted-foreground mt-1">
          Visualize voice agent performance metrics and AI-powered speech
          insights.
        </p>
      </div>

      {!hasData && !isLoading && (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-16">
            <p className="text-muted-foreground text-sm">
              No data available yet. Analytics will populate once calls are recorded.
            </p>
          </CardContent>
        </Card>
      )}

      {/* AI Speech Insights Section */}
      {analytics?.insights_aggregate && (
        <>
          <InsightsSection insights={analytics.insights_aggregate} />
          <Separator />
        </>
      )}

      <div className="grid gap-6 md:grid-cols-2">
        {/* 1. Calls Per Day — BarChart */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Calls Per Day</CardTitle>
            <CardDescription>Daily call volume over time</CardDescription>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <ChartSkeleton />
            ) : (
              <ResponsiveContainer width="100%" height={260}>
                <BarChart
                  data={analytics?.calls_per_day ?? []}
                  margin={{ top: 5, right: 10, left: -10, bottom: 5 }}
                >
                  <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                  <XAxis
                    dataKey="date"
                    tick={{ fontSize: 12 }}
                    tickFormatter={(v: string) => {
                      const parts = v.split('-')
                      return `${parts[1]}/${parts[2]}`
                    }}
                    className="text-muted-foreground"
                  />
                  <YAxis tick={{ fontSize: 12 }} allowDecimals={false} />
                  <RechartsTooltip
                    contentStyle={{
                      backgroundColor: 'hsl(var(--card))',
                      border: '1px solid hsl(var(--border))',
                      borderRadius: '8px',
                      fontSize: '12px',
                    }}
                  />
                  <Bar
                    dataKey="count"
                    fill={COLORS.blue}
                    radius={[4, 4, 0, 0]}
                    name="Calls"
                  />
                </BarChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        {/* 2. Average Call Duration — LineChart */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Average Call Duration</CardTitle>
            <CardDescription>Mean duration in seconds per day</CardDescription>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <ChartSkeleton />
            ) : (
              <ResponsiveContainer width="100%" height={260}>
                <LineChart
                  data={analytics?.avg_duration ?? []}
                  margin={{ top: 5, right: 10, left: -10, bottom: 5 }}
                >
                  <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                  <XAxis
                    dataKey="date"
                    tick={{ fontSize: 12 }}
                    tickFormatter={(v: string) => {
                      const parts = v.split('-')
                      return `${parts[1]}/${parts[2]}`
                    }}
                  />
                  <YAxis tick={{ fontSize: 12 }} unit="s" />
                  <RechartsTooltip
                    contentStyle={{
                      backgroundColor: 'hsl(var(--card))',
                      border: '1px solid hsl(var(--border))',
                      borderRadius: '8px',
                      fontSize: '12px',
                    }}
                    formatter={(value: number) => [`${value}s`, 'Avg Duration']}
                  />
                  <Line
                    type="monotone"
                    dataKey="avg"
                    stroke={COLORS.teal}
                    strokeWidth={2}
                    dot={{ r: 3 }}
                    activeDot={{ r: 5 }}
                    name="Avg Duration"
                  />
                </LineChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        {/* 3. Sentiment Distribution — PieChart */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Sentiment Distribution</CardTitle>
            <CardDescription>
              Breakdown of patient call sentiment scores
            </CardDescription>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <ChartSkeleton />
            ) : (
              <ResponsiveContainer width="100%" height={260}>
                <PieChart>
                  <Pie
                    data={analytics?.sentiment_distribution ?? []}
                    cx="50%"
                    cy="50%"
                    innerRadius={55}
                    outerRadius={90}
                    paddingAngle={3}
                    dataKey="count"
                    nameKey="label"
                    label={({ label, percent }: { label: string; percent: number }) =>
                      `${label} ${(percent * 100).toFixed(0)}%`
                    }
                    labelLine={false}
                  >
                    {(analytics?.sentiment_distribution ?? []).map((_entry, index) => (
                      <Cell
                        key={`cell-${index}`}
                        fill={SENTIMENT_COLORS[index % SENTIMENT_COLORS.length]}
                      />
                    ))}
                  </Pie>
                  <RechartsTooltip
                    contentStyle={{
                      backgroundColor: 'hsl(var(--card))',
                      border: '1px solid hsl(var(--border))',
                      borderRadius: '8px',
                      fontSize: '12px',
                    }}
                  />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        {/* 4. Escalation Rate — Stat Card */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Escalation Rate</CardTitle>
            <CardDescription>
              Percentage of calls transferred to human staff
            </CardDescription>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="flex flex-col items-center justify-center h-[260px]">
                <Skeleton className="h-20 w-20 rounded-full" />
                <Skeleton className="h-4 w-24 mt-4" />
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center h-[260px]">
                {(() => {
                  const rate =
                    analytics && analytics.escalation_rate.length > 0
                      ? analytics.escalation_rate[0]?.rate ?? 0
                      : 0
                  const color =
                    rate > 20
                      ? 'text-red-500'
                      : rate > 10
                        ? 'text-amber-500'
                        : 'text-emerald-500'
                  return (
                    <>
                      <div
                        className={`text-6xl font-bold tracking-tighter ${color}`}
                      >
                        {rate.toFixed(1)}%
                      </div>
                      <p className="text-sm text-muted-foreground mt-3">
                        {rate > 20
                          ? 'Above target - review escalation triggers'
                          : rate > 10
                            ? 'Moderate - monitor closely'
                            : 'Healthy - agent handling well'}
                      </p>
                      <div className="w-full max-w-xs mt-6 bg-muted rounded-full h-3 overflow-hidden">
                        <div
                          className={`h-full rounded-full transition-all duration-500 ${
                            rate > 20
                              ? 'bg-red-500'
                              : rate > 10
                                ? 'bg-amber-500'
                                : 'bg-emerald-500'
                          }`}
                          style={{ width: `${Math.min(rate, 100)}%` }}
                        />
                      </div>
                    </>
                  )
                })()}
              </div>
            )}
          </CardContent>
        </Card>

        {/* 5. Top Doctors — Horizontal BarChart */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Top Doctors</CardTitle>
            <CardDescription>
              Most frequently booked physicians
            </CardDescription>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <ChartSkeleton />
            ) : analytics &&
              analytics.top_doctors &&
              analytics.top_doctors.length > 0 ? (
              <ResponsiveContainer width="100%" height={260}>
                <BarChart
                  data={analytics.top_doctors}
                  layout="vertical"
                  margin={{ top: 5, right: 10, left: 20, bottom: 5 }}
                >
                  <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                  <XAxis type="number" tick={{ fontSize: 12 }} allowDecimals={false} />
                  <YAxis
                    type="category"
                    dataKey="name"
                    tick={{ fontSize: 11 }}
                    width={100}
                  />
                  <RechartsTooltip
                    contentStyle={{
                      backgroundColor: 'hsl(var(--card))',
                      border: '1px solid hsl(var(--border))',
                      borderRadius: '8px',
                      fontSize: '12px',
                    }}
                  />
                  <Bar
                    dataKey="count"
                    fill={COLORS.purple}
                    radius={[0, 4, 4, 0]}
                    name="Bookings"
                  />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex items-center justify-center h-[260px] text-muted-foreground text-sm">
                No booking data available yet.
              </div>
            )}
          </CardContent>
        </Card>

        {/* 6. Booking Rate — AreaChart */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Booking Rate</CardTitle>
            <CardDescription>
              Successful appointment bookings over time
            </CardDescription>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <ChartSkeleton />
            ) : analytics &&
              analytics.booking_rate &&
              analytics.booking_rate.length > 0 ? (
              <ResponsiveContainer width="100%" height={260}>
                <AreaChart
                  data={analytics.booking_rate}
                  margin={{ top: 5, right: 10, left: -10, bottom: 5 }}
                >
                  <defs>
                    <linearGradient id="bookingGradient" x1="0" y1="0" x2="0" y2="1">
                      <stop
                        offset="5%"
                        stopColor={COLORS.green}
                        stopOpacity={0.3}
                      />
                      <stop
                        offset="95%"
                        stopColor={COLORS.green}
                        stopOpacity={0}
                      />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                  <XAxis
                    dataKey="date"
                    tick={{ fontSize: 12 }}
                    tickFormatter={(v: string) => {
                      const parts = v.split('-')
                      return `${parts[1]}/${parts[2]}`
                    }}
                  />
                  <YAxis tick={{ fontSize: 12 }} unit="%" />
                  <RechartsTooltip
                    contentStyle={{
                      backgroundColor: 'hsl(var(--card))',
                      border: '1px solid hsl(var(--border))',
                      borderRadius: '8px',
                      fontSize: '12px',
                    }}
                    formatter={(value: number) => [`${value.toFixed(1)}%`, 'Rate']}
                  />
                  <Area
                    type="monotone"
                    dataKey="rate"
                    stroke={COLORS.green}
                    strokeWidth={2}
                    fill="url(#bookingGradient)"
                    name="Booking Rate"
                  />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex items-center justify-center h-[260px] text-muted-foreground text-sm">
                No booking rate data available yet.
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
