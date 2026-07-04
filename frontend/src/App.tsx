import { NavLink, Route, Routes } from 'react-router-dom'
import Home from './pages/Home'
import Data from './pages/Data'
import Features from './pages/Features'
import Strategies from './pages/Strategies'
import Regime from './pages/Regime'
import Meta from './pages/Meta'
import Risk from './pages/Risk'
import Live from './pages/Live'
import Multi from './pages/Multi'

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
        <NavLink to="/strategies">Estrategias</NavLink>
        <NavLink to="/regime">Régimen</NavLink>
        <NavLink to="/meta">Meta-modelo</NavLink>
        <NavLink to="/risk">Riesgo</NavLink>
        <NavLink to="/multi">Multi-activo</NavLink>
        <NavLink to="/live">Live</NavLink>
      </nav>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/data" element={<Data />} />
        <Route path="/features" element={<Features />} />
        <Route path="/strategies" element={<Strategies />} />
        <Route path="/regime" element={<Regime />} />
        <Route path="/meta" element={<Meta />} />
        <Route path="/risk" element={<Risk />} />
        <Route path="/multi" element={<Multi />} />
        <Route path="/live" element={<Live />} />
      </Routes>
    </>
  )
}
