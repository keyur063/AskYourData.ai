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
 *   await apiClient.uploadFile('/workspaces/123/files', file)
 */
import { supabase } from './supabase-client'

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

async function getToken(): Promise<string | null> {
  const {
    data: { session },
  } = await supabase.auth.getSession()
  return session?.access_token ?? null
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown
): Promise<T> {
  const token = await getToken()
  const headers: HeadersInit = { 'Content-Type': 'application/json' }
  if (token) headers['Authorization'] = `Bearer ${token}`

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

async function uploadFile<T>(path: string, file: File): Promise<T> {
  const token = await getToken()
  const headers: HeadersInit = {}
  if (token) headers['Authorization'] = `Bearer ${token}`

  const formData = new FormData()
  formData.append('file', file)

  const res = await fetch(`${API_URL}${path}`, {
    method: 'POST',
    headers,
    body: formData,
  })

  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText)
    throw new Error(`Upload ${path} → ${res.status}: ${detail}`)
  }

  return res.json() as Promise<T>
}

export const apiClient = {
  get: <T>(path: string) => request<T>('GET', path),
  post: <T>(path: string, body: unknown) => request<T>('POST', path, body),
  delete: <T>(path: string) => request<T>('DELETE', path),
  uploadFile: <T>(path: string, file: File) => uploadFile<T>(path, file),
}

