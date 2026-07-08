import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Welcome from './pages/Welcome'
import Practice from './pages/Practice'
import Exercise from './pages/Exercise'
import Conjugation from './pages/Conjugation'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Welcome />} />
        <Route path="/practice/:language" element={<Practice />} />
        <Route path="/practice/:language/conjugation" element={<Conjugation />} />
        <Route path="/exercise" element={<Exercise />} />
        <Route path="*" element={<Navigate to="/" />} />
      </Routes>
    </BrowserRouter>
  )
}
