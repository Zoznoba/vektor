import { StudentHome } from './pages/student/StudentHome';

/**
 * Пока в проекте одна готовая страница — «Главная» ученика.
 * Когда появятся «Анкеты», «Результаты», «Профиль» и кабинеты других ролей,
 * здесь подключается роутер (react-router-dom) и App превращается в
 * раздачу маршрутов по ролям, без изменений в самих страницах.
 */
function App() {
  return <StudentHome />;
}

export default App;
