import { useQuery } from '@tanstack/react-query'
import { fetchAnalytics, fetchDoctors } from '@/lib/api'

/**
 * Hook to fetch analytics data computed from call logs.
 * Auto-refreshes every 30 seconds to keep dashboard current.
 */
export function useAnalytics() {
  return useQuery({
    queryKey: ['analytics'],
    queryFn: fetchAnalytics,
    refetchInterval: 30000,
  })
}

/**
 * Hook to fetch doctors list with optional specialty filter.
 */
export function useDoctors(specialty?: string) {
  return useQuery({
    queryKey: ['doctors', specialty],
    queryFn: () => fetchDoctors(specialty),
  })
}
