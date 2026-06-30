import { Link, Route, Routes } from 'react-router-dom';
import Board from './pages/Board';
import StockDetail from './pages/StockDetail';
import Performance from './pages/Performance';

export default function App() {
  return (
    <div>
      <nav>
        <Link to="/">추천보드</Link>
        <Link to="/performance">성과추적</Link>
      </nav>
      <Routes>
        <Route path="/" element={<Board />} />
        <Route path="/stock/:code" element={<StockDetail />} />
        <Route path="/performance" element={<Performance />} />
      </Routes>
    </div>
  );
}
