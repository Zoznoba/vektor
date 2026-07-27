import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { AuthProvider, useAuth } from './auth/AuthContext';
import { RequireAuth } from './auth/RequireAuth';
import { LoginPage } from './pages/LoginPage';
import { StudentHome } from './pages/student/StudentHome';

/** Уже залогиненного пользователя с /login уводим в кабинет. */
function LoginRoute() {
  const { status } = useAuth();
  if (status === 'loading') return null;
  if (status === 'authenticated') return <Navigate to="/" replace />;
  return <LoginPage />;
}

/**
 * Маршруты по ролям: пока реализован только кабинет ученика, поэтому все
 * роли попадают на StudentHome. Когда появятся кабинеты учителя/родителя/
 * админа — здесь будет ветвление по user.role.
 */
function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginRoute />} />
          <Route element={<RequireAuth />}>
            <Route path="/" element={<StudentHome />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}

export default App;
