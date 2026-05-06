import { useEffect } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useAuth } from '../store/auth.js'
import { api } from '../lib/api.js'

// Backend's Google OAuth handler issues tokens then redirects to:
//   /auth/callback?access_token=...&refresh_token=...
// We pull them into the auth store and bounce to /projects.
export default function AuthCallback() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const setSession = useAuth((s) => s.setSession)

  useEffect(() => {
    const access = params.get('access_token')
    const refresh = params.get('refresh_token')
    const error = params.get('error')
    if (error) {
      navigate('/login?error=' + encodeURIComponent(error), { replace: true })
      return
    }
    if (!access || !refresh) {
      navigate('/login?error=missing_tokens', { replace: true })
      return
    }
    setSession({ accessToken: access, refreshToken: refresh, user: null })
    api.me().then((user) => {
      useAuth.getState().setUser(user)
      navigate('/projects', { replace: true })
    }).catch(() => navigate('/login?error=me_failed', { replace: true }))
  }, [params, navigate, setSession])

  return (
    <div className="min-h-screen flex items-center justify-center text-ink-300">
      Signing you in…
    </div>
  )
}
