import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { AuthProvider, useAuth } from './auth/AuthContext';
import { RequireAuth } from './auth/RequireAuth';
import { LoginPage } from './pages/LoginPage';
import { StudentHome } from './pages/student/StudentHome';
import { AssessmentFillPage } from './pages/student/AssessmentFillPage';
import { SurveysPage } from './pages/surveys/SurveysPage';
import { TeacherClassesPage } from './pages/teacher/TeacherClassesPage';
import { TeacherStudentPage } from './pages/teacher/TeacherStudentPage';
import { TeacherCasesPage } from './pages/teacher/TeacherCasesPage';
import { AdminDashboard } from './pages/admin/AdminDashboard';
import { AdminUsersPage } from './pages/admin/AdminUsersPage';
import { AdminClassesPage } from './pages/admin/AdminClassesPage';
import { AdminCasesPage } from './pages/admin/AdminCasesPage';
import { AdminCampaignsPage } from './pages/admin/AdminCampaignsPage';
import { AdminQuestionnairePage } from './pages/admin/AdminQuestionnairePage';
import { AdminUserProfilePage } from './pages/admin/AdminUserProfilePage';
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
              path="/teacher/cases"
              element={
                <RequireTeacher>
                  <TeacherCasesPage />
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
              path="/admin/cases"
              element={
                <RequireAdmin>
                  <AdminCasesPage />
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
              path="/admin/questionnaire"
              element={
                <RequireAdmin>
                  <AdminQuestionnairePage />
                </RequireAdmin>
              }
            />
            {/* Карточка пользователя — одна страница. `/results` оставлен
                синонимом: по нему ведут действия «Диагностика» из «Классов»,
                «Кейсов» и покрытия кампании. Блок диагностики раскрыт в
                обоих случаях, поэтому поведение адресов не различается. */}
            <Route
              path="/admin/users/:id"
              element={
                <RequireAdmin>
                  <AdminUserProfilePage />
                </RequireAdmin>
              }
            />
            <Route
              path="/admin/users/:id/results"
              element={
                <RequireAdmin>
                  <AdminUserProfilePage />
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
