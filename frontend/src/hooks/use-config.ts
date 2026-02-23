import { useQuery } from '@tanstack/react-query'
import { fetchHealth } from '@/lib/api'

/**
 * Hook to poll the backend health endpoint every 10 seconds.
 * Returns service-level status (API, Ollama, Voice Agent).
 */
export function useHealthStatus() {
  return useQuery({
    queryKey: ['health'],
    queryFn: fetchHealth,
    refetchInterval: 10000,
  })
}
