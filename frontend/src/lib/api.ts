import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
})

// Types
export interface Doctor {
  id: string
  name: string
  specialty: string
  bio: string
  available_days: string[]
  consultation_fee: number
  created_at: string
}

export interface Patient {
  id: string
  name: string
  phone: string
  email: string | null
  insurance_provider: string | null
  date_of_birth: string | null
  created_at: string
}

export interface TimeSlot {
  id: string
  doctor_id: string
  doctor_name?: string
  slot_date: string
  start_time: string
  end_time: string
  is_available: boolean
}

export interface Appointment {
  id: string
  patient_id: string
  doctor_id: string
  slot_id: string
  visit_type: string
  status: string
  notes: string | null
  created_at: string
  updated_at: string | null
  patient?: Patient
  doctor?: Doctor
  time_slot?: TimeSlot
}

export interface AgentPerformance {
  response_quality: 'excellent' | 'good' | 'fair' | 'poor'
  empathy_score: 'high' | 'medium' | 'low'
  accuracy: 'high' | 'medium' | 'low'
  areas_for_improvement: string[]
}

export interface KeyMoment {
  timestamp: string
  event: string
}

export interface AIInsights {
  topics: string[]
  patient_intent: string
  resolution_status: 'resolved' | 'partially_resolved' | 'unresolved' | 'escalated'
  language_detected: 'english' | 'hindi' | 'hinglish'
  key_moments: KeyMoment[]
  action_items: string[]
  patient_satisfaction: 'high' | 'medium' | 'low'
  agent_performance: AgentPerformance
  recommendations: string[]
}

export interface CallLog {
  id: string
  patient_phone: string
  duration_seconds: number
  transcript: string
  summary: string | null
  tools_used: string[]
  escalated: boolean
  sentiment_score: number | null
  ai_insights: AIInsights | null
  created_at: string
}

export interface PaginatedCallLogs {
  items: CallLog[]
  total: number
  page: number
  per_page: number
  pages: number
}

export interface HealthStatus {
  status: string
  services: Record<string, string>
}

export interface InsightsAggregate {
  top_topics: { topic: string; count: number }[]
  resolution_breakdown: { status: string; count: number }[]
  language_breakdown: { language: string; count: number }[]
  satisfaction_breakdown: { level: string; count: number }[]
  avg_agent_quality: string
  common_action_items: string[]
  common_recommendations: string[]
  calls_with_insights: number
}

export interface AnalyticsData {
  calls_per_day: { date: string; count: number }[]
  booking_rate: { date: string; rate: number }[]
  avg_duration: { date: string; avg: number }[]
  escalation_rate: { date: string; rate: number }[]
  top_doctors: { name: string; count: number }[]
  sentiment_distribution: { label: string; count: number }[]
  insights_aggregate: InsightsAggregate | null
}

// API functions
export const fetchDoctors = (specialty?: string) =>
  api
    .get<Doctor[]>('/doctors/', { params: specialty ? { specialty } : {} })
    .then((r) => r.data)

export const fetchCallLogs = (page = 1, perPage = 20, phone?: string) =>
  api
    .get<PaginatedCallLogs>('/calls/', {
      params: { page, per_page: perPage, ...(phone ? { phone } : {}) },
    })
    .then((r) => r.data)

export const fetchCallDetail = (id: string) =>
  api.get<CallLog>(`/calls/${id}`).then((r) => r.data)

export const fetchHealth = () =>
  axios.get<HealthStatus>('/health').then((r) => r.data)

export const fetchAppointments = (phone?: string) =>
  api
    .get<Appointment[]>('/appointments/', {
      params: phone ? { patient_phone: phone } : {},
    })
    .then((r) => r.data)

export const fetchSlots = (doctorName?: string, date?: string) =>
  api
    .get<TimeSlot[]>('/appointments/slots', {
      params: {
        ...(doctorName ? { doctor_name: doctorName } : {}),
        ...(date ? { date } : {}),
      },
    })
    .then((r) => r.data)

// Analytics endpoint (computed from call logs on the frontend)
export const fetchAnalytics = async (): Promise<AnalyticsData> => {
  const logs = await fetchCallLogs(1, 100)

  // Compute analytics from call logs
  const callsByDay = new Map<string, number>()
  const durationsByDay = new Map<string, number[]>()
  const sentiments: number[] = []

  for (const log of logs.items) {
    const day = log.created_at.split('T')[0] ?? log.created_at
    callsByDay.set(day, (callsByDay.get(day) ?? 0) + 1)
    if (!durationsByDay.has(day)) durationsByDay.set(day, [])
    durationsByDay.get(day)?.push(log.duration_seconds)
    if (log.sentiment_score !== null) sentiments.push(log.sentiment_score)
  }

  const calls_per_day = Array.from(callsByDay.entries())
    .map(([date, count]) => ({ date, count }))
    .sort((a, b) => a.date.localeCompare(b.date))

  const avg_duration = Array.from(durationsByDay.entries())
    .map(([date, durations]) => ({
      date,
      avg: Math.round(
        durations.reduce((a, b) => a + b, 0) / durations.length
      ),
    }))
    .sort((a, b) => a.date.localeCompare(b.date))

  const totalCalls = logs.items.length
  const escalated = logs.items.filter((l) => l.escalated).length
  const booking_rate = calls_per_day.map((d) => ({ date: d.date, rate: 0 }))

  const positive = sentiments.filter((s) => s >= 0.6).length
  const neutral = sentiments.filter((s) => s >= 0.3 && s < 0.6).length
  const negative = sentiments.filter((s) => s < 0.3).length

  // Aggregate AI insights from all calls that have them
  const insightsAggregate = aggregateInsights(logs.items)

  return {
    calls_per_day,
    booking_rate,
    avg_duration,
    escalation_rate: [
      {
        date: 'overall',
        rate: totalCalls > 0 ? (escalated / totalCalls) * 100 : 0,
      },
    ],
    top_doctors: [],
    sentiment_distribution: [
      { label: 'Positive', count: positive },
      { label: 'Neutral', count: neutral },
      { label: 'Negative', count: negative },
    ],
    insights_aggregate: insightsAggregate,
  }
}

/** Aggregate AI insights across all calls into summary statistics. */
function aggregateInsights(calls: CallLog[]): InsightsAggregate | null {
  const withInsights = calls.filter((c) => c.ai_insights !== null)
  if (withInsights.length === 0) return null

  // Count topics
  const topicCounts = new Map<string, number>()
  const resolutionCounts = new Map<string, number>()
  const languageCounts = new Map<string, number>()
  const satisfactionCounts = new Map<string, number>()
  const qualityScores: string[] = []
  const allActionItems: string[] = []
  const allRecommendations: string[] = []

  for (const call of withInsights) {
    const ins = call.ai_insights!

    // Topics
    for (const topic of ins.topics ?? []) {
      const t = topic.toLowerCase()
      topicCounts.set(t, (topicCounts.get(t) ?? 0) + 1)
    }

    // Resolution
    if (ins.resolution_status) {
      resolutionCounts.set(
        ins.resolution_status,
        (resolutionCounts.get(ins.resolution_status) ?? 0) + 1
      )
    }

    // Language
    if (ins.language_detected) {
      languageCounts.set(
        ins.language_detected,
        (languageCounts.get(ins.language_detected) ?? 0) + 1
      )
    }

    // Satisfaction
    if (ins.patient_satisfaction) {
      satisfactionCounts.set(
        ins.patient_satisfaction,
        (satisfactionCounts.get(ins.patient_satisfaction) ?? 0) + 1
      )
    }

    // Agent quality
    if (ins.agent_performance?.response_quality) {
      qualityScores.push(ins.agent_performance.response_quality)
    }

    // Action items (collect unique)
    for (const item of ins.action_items ?? []) {
      if (!allActionItems.includes(item)) allActionItems.push(item)
    }

    // Recommendations (collect unique)
    for (const rec of ins.recommendations ?? []) {
      if (!allRecommendations.includes(rec)) allRecommendations.push(rec)
    }
  }

  // Determine most common quality rating
  const qualityCount = new Map<string, number>()
  for (const q of qualityScores) {
    qualityCount.set(q, (qualityCount.get(q) ?? 0) + 1)
  }
  let avgQuality = 'N/A'
  let maxQCount = 0
  for (const [q, c] of qualityCount) {
    if (c > maxQCount) {
      avgQuality = q
      maxQCount = c
    }
  }

  return {
    top_topics: Array.from(topicCounts.entries())
      .map(([topic, count]) => ({ topic, count }))
      .sort((a, b) => b.count - a.count)
      .slice(0, 10),
    resolution_breakdown: Array.from(resolutionCounts.entries())
      .map(([status, count]) => ({ status, count }))
      .sort((a, b) => b.count - a.count),
    language_breakdown: Array.from(languageCounts.entries())
      .map(([language, count]) => ({ language, count }))
      .sort((a, b) => b.count - a.count),
    satisfaction_breakdown: Array.from(satisfactionCounts.entries())
      .map(([level, count]) => ({ level, count }))
      .sort((a, b) => b.count - a.count),
    avg_agent_quality: avgQuality,
    common_action_items: allActionItems.slice(0, 10),
    common_recommendations: allRecommendations.slice(0, 10),
    calls_with_insights: withInsights.length,
  }
}

export default api
