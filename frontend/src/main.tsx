import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import App from './App';
// 콘솔 타이포: 본문 Pretendard(가변) + 숫자/코드 JetBrains Mono — 전부 로컬 번들(CDN 금지)
import 'pretendard/dist/web/variable/pretendardvariable.css';
import '@fontsource/jetbrains-mono/400.css';
import '@fontsource/jetbrains-mono/700.css';
import './styles/theme.css';
import { initTheme } from './lib/theme';

// 렌더 전에 저장된 테마를 적용해 초기 플래시(다크→라이트 깜빡임)를 막는다.
initTheme();

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
);
