import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '../store/auth.js'

export default function ProtectedRoute() {
  const isAuthed = useAuth((s) => !!s.accessToken)
  const loc = useLocation()
  if (!isAuthed) {
    return (
      <Navigate
        to="/login"
        replace
        state={{ from: loc.pathname, sessionExpired: true }}
      />
    )
  }
  return <Outlet />
}
