import { Routes, Route, Navigate } from 'react-router-dom'
import Landing from './routes/Landing.jsx'
import Login from './routes/Login.jsx'
import Signup from './routes/Signup.jsx'
import AuthCallback from './routes/AuthCallback.jsx'
import Projects from './routes/Projects.jsx'
import Editor from './routes/Editor.jsx'
import ProtectedRoute from './routes/ProtectedRoute.jsx'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/login" element={<Login />} />
      <Route path="/signup" element={<Signup />} />
      <Route path="/auth/callback" element={<AuthCallback />} />

      <Route element={<ProtectedRoute />}>
        <Route path="/projects" element={<Projects />} />
        <Route path="/projects/:projectId" element={<Editor />} />
        <Route path="/projects/:projectId/files/:fileId" element={<Editor />} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
