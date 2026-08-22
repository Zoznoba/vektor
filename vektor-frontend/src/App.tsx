import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { AuthProvider, useAuth } from './auth/AuthContext';
import { RequireAuth } from './auth/RequireAuth';
import { LoginPage } from './pages/LoginPage';
import { StudentHome } from './pages/student/StudentHome';
import { AssessmentFillPage } from './pages/student/AssessmentFillPage';
import { SurveysPage } from './pages/surveys/SurveysPage';
import { TeacherClassesPage } from './pages/teacher/TeacherClassesPage';
import { TeacherStudentPage } from './pages/teacher/TeacherStudentPage';
import { AdminDashboard } from './pages/admin/AdminDashboard';
import { AdminUsersPage } from './pages/admin/AdminUsersPage';
import { AdminClassesPage } from './pages/admin/AdminClassesPage';
import { AdminCampaignsPage } from './pages/admin/AdminCampaignsPage';
import { AdminResultsPage } from './pages/admin/AdminResultsPage';
import { ParentResultsPage } from './pages/parent/ParentResultsPage';

/** Уже залогиненного пользователя с /login уводим в его кабинет. */
function LoginRoute() {
  const { status } = useAuth();
  if (status === 'loading') return null;
  if (status === 'authenticated') return <Navigate to="/" replace />;
  return <LoginPage />;
}

/**
 * Корень: разводим по кабинетам согласно роли.
 *
 * У учителя «Главной» нет — стартовый экран «Мои классы» (так в прототипе, и
 * дашборд с личными результатами ему бессмысленен: учитель не субъект оценки).
 * У родителя тоже нет личного дашборда — стартовый экран сразу «Результаты»
 * (данные первого ребёнка).
 */
function HomeRedirect() {
  const { user } = useAuth();
  if (user?.role === 'admin') return <Navigate to="/admin" replace />;
  if (user?.role === 'teacher') return <Navigate to="/teacher/classes" replace />;
  if (user?.role === 'parent') return <Navigate to="/parent/results" replace />;
  return <StudentHome />;
}

/** Страницы админки доступны только роли admin; остальных — на их кабинет. */
function RequireAdmin({ children }: { children: React.ReactElement }) {
  const { user } = useAuth();
  if (user?.role !== 'admin') return <Navigate to="/" replace />;
  return children;
}

/** Экраны учителя: учителю и админу. Бэкенд всё равно проверяет права сам. */
function RequireTeacher({ children }: { children: React.ReactElement }) {
  const { user } = useAuth();
  if (user?.role !== 'teacher' && user?.role !== 'admin') return <Navigate to="/" replace />;
  return children;
}

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginRoute />} />
          <Route element={<RequireAuth />}>
            <Route path="/" element={<HomeRedirect />} />
            <Route path="/surveys" element={<SurveysPage />} />
            <Route path="/assessments/:id" element={<AssessmentFillPage />} />
            <Route path="/parent/results" element={<ParentResultsPage />} />
            <Route
              path="/teacher/classes"
              element={
                <RequireTeacher>
                  <TeacherClassesPage />
                </RequireTeacher>
              }
            />
            <Route
              path="/teacher/students"
              element={
                <RequireTeacher>
                  <TeacherStudentPage />
                </RequireTeacher>
              }
            />
            <Route
              path="/teacher/students/:id"
              element={
                <RequireTeacher>
                  <TeacherStudentPage />
                </RequireTeacher>
              }
            />
            <Route
              path="/admin"
              element={
                <RequireAdmin>
                  <AdminDashboard />
                </RequireAdmin>
              }
            />
            <Route
              path="/admin/users"
              element={
                <RequireAdmin>
                  <AdminUsersPage />
                </RequireAdmin>
              }
            />
            <Route
              path="/admin/classes"
              element={
                <RequireAdmin>
                  <AdminClassesPage />
                </RequireAdmin>
              }
            />
            <Route
              path="/admin/campaigns"
              element={
                <RequireAdmin>
                  <AdminCampaignsPage />
                </RequireAdmin>
              }
            />
            <Route
              path="/admin/results"
              element={
                <RequireAdmin>
                  <AdminResultsPage />
                </RequireAdmin>
              }
            />
            <Route
              path="/admin/results/:id"
              element={
                <RequireAdmin>
                  <AdminResultsPage />
                </RequireAdmin>
              }
            />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}

export default App;
