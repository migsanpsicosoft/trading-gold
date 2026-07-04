import { NavLink, Route, Routes } from 'react-router-dom'
import Home from './pages/Home'
import Data from './pages/Data'

export default function App() {
  return (
    <>
      <nav className="topnav">
        <span className="brand">🥇 Gold Hybrid Bot</span>
        <NavLink to="/" end>
          Home
        </NavLink>
        <NavLink to="/data">Datos</NavLink>
        {/* Próximas fases: Estrategias, Régimen, Meta-modelo, Riesgo */}
      </nav>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/data" element={<Data />} />
      </Routes>
    </>
  )
}
