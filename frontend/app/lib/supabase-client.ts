/**
 * Browser-side Supabase client (uses the anon/public key).
 *
 * Import this in Client Components and browser-only code.
 * For Server Components / Route Handlers, use the SSR client below.
 *
 * Reads from NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY —
 * both are populated by you in .env.local (see .env.local.example).
 * Never hardcode the values here.
 */
import { createBrowserClient } from '@supabase/ssr'

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!

if (!supabaseUrl || !supabaseAnonKey) {
  throw new Error(
    'NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY must be set in .env.local'
  )
}

/**
 * Browser Supabase client — singleton, safe to call at module level.
 * Uses RLS via the user's session cookie/token automatically.
 */
export const supabase = createBrowserClient(supabaseUrl, supabaseAnonKey)
