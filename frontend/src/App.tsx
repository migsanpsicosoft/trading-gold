import { NavLink, Route, Routes } from 'react-router-dom'
import Home from './pages/Home'
import Data from './pages/Data'
import Features from './pages/Features'

export default function App() {
  return (
    <>
      <nav className="topnav">
        <span className="brand">🥇 Gold Hybrid Bot</span>
        <NavLink to="/" end>
          Home
        </NavLink>
        <NavLink to="/data">Datos</NavLink>
        <NavLink to="/features">Features</NavLink>
        {/* Próximas fases: Estrategias, Régimen, Meta-modelo, Riesgo */}
      </nav>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/data" element={<Data />} />
        <Route path="/features" element={<Features />} />
      </Routes>
    </>
  )
}
