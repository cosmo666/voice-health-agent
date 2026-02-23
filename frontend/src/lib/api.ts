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

export interface CallLog {
  id: string
  patient_phone: string
  duration_seconds: number
  transcript: string
  summary: string | null
  tools_used: string[]
  escalated: boolean
  sentiment_score: number | null
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

export interface AnalyticsData {
  calls_per_day: { date: string; count: number }[]
  booking_rate: { date: string; rate: number }[]
  avg_duration: { date: string; avg: number }[]
  escalation_rate: { date: string; rate: number }[]
  top_doctors: { name: string; count: number }[]
  sentiment_distribution: { label: string; count: number }[]
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
  const logs = await fetchCallLogs(1, 1000)

  // Compute analytics from call logs
  const callsByDay = new Map<string, number>()
  const durationsByDay = new Map<string, number[]>()
  const sentiments: number[] = []

  for (const log of logs.items) {
    const day = log.created_at.split('T')[0]
    callsByDay.set(day, (callsByDay.get(day) || 0) + 1)
    if (!durationsByDay.has(day)) durationsByDay.set(day, [])
    durationsByDay.get(day)!.push(log.duration_seconds)
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
  }
}

export default api
