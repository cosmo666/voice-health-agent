import { useQuery } from '@tanstack/react-query'
import { fetchCallLogs, fetchCallDetail } from '@/lib/api'

/**
 * Hook to fetch paginated call logs with optional phone filter.
 * Re-fetches automatically when page, perPage, or phone changes.
 */
export function useCallLogs(page = 1, perPage = 20, phone?: string) {
  return useQuery({
    queryKey: ['calls', page, perPage, phone],
    queryFn: () => fetchCallLogs(page, perPage, phone),
  })
}

/**
 * Hook to fetch a single call log by ID.
 * Only executes if a valid ID is provided.
 */
export function useCallDetail(id: string) {
  return useQuery({
    queryKey: ['call', id],
    queryFn: () => fetchCallDetail(id),
    enabled: !!id,
  })
}
