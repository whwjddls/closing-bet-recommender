import { NavLink, Route, Routes } from 'react-router-dom';
import Board from './pages/Board';
import StockDetail from './pages/StockDetail';
import Performance from './pages/Performance';
import GlobalHeader from './components/GlobalHeader';

export default function App() {
  return (
    <div className="app-shell">
      <GlobalHeader />
      <nav className="app-nav">
        <NavLink to="/" end>
          오늘의 추천
        </NavLink>
        <NavLink to="/performance">성과 리포트</NavLink>
      </nav>
      <Routes>
        <Route path="/" element={<Board />} />
        <Route path="/stock/:code" element={<StockDetail />} />
        <Route path="/performance" element={<Performance />} />
      </Routes>
    </div>
  );
}
