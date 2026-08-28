/**
 * Typed fetch wrapper for the FastAPI backend.
 *
 * All backend calls go through this module so that:
 *  - The base URL comes from NEXT_PUBLIC_API_URL (not hardcoded)
 *  - The Supabase JWT is attached automatically from the active session
 *  - Errors are surfaced uniformly
 *
 * Usage:
 *   import { apiClient } from '@/app/lib/api-client'
 *   const workspaces = await apiClient.get('/workspaces')
 */
import { supabase } from './supabase-client'

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

async function getAuthHeaders(): Promise<HeadersInit> {
  const {
    data: { session },
  } = await supabase.auth.getSession()

  if (!session?.access_token) {
    return { 'Content-Type': 'application/json' }
  }

  return {
    'Content-Type': 'application/json',
    Authorization: `Bearer ${session.access_token}`,
  }
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown
): Promise<T> {
  const headers = await getAuthHeaders()
  const res = await fetch(`${API_URL}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })

  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText)
    throw new Error(`API ${method} ${path} → ${res.status}: ${detail}`)
  }

  // 204 No Content — return null
  if (res.status === 204) return null as T
  return res.json() as Promise<T>
}

export const apiClient = {
  get: <T>(path: string) => request<T>('GET', path),
  post: <T>(path: string, body: unknown) => request<T>('POST', path, body),
  // Add patch/delete as needed in later tickets
}
