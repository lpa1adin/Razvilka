import { lazy, Suspense } from 'react'
import { Outlet, RouterProvider, createBrowserRouter } from 'react-router'

import { Skeleton } from '@/components/ui/States'

import { AuthProvider } from '@/features/auth/AuthProvider'
import { MentorProvider } from '@/features/mentor/MentorProvider'
import { CoursePage } from '@/pages/courses/CoursePage'
import { CoursesPage } from '@/pages/courses/CoursesPage'
import { LessonPage } from '@/pages/courses/LessonPage'
import { HomePage } from '@/pages/HomePage'
import { FragmentPage } from '@/pages/library/FragmentPage'
import { LibraryPage } from '@/pages/library/LibraryPage'
import { PracticePage } from '@/pages/practice/PracticePage'
import { ArchPage } from '@/pages/practice/ArchPage'
import { AssignmentPage } from '@/pages/practice/AssignmentPage'
import { QuizPage } from '@/pages/practice/QuizPage'
import { SubmissionPage } from '@/pages/reviews/SubmissionPage'
import { ForksPage } from '@/pages/ForksPage'
import { PathPage, ProjectsPage } from '@/pages/projects/ProjectsPage'
import { ReviewDetailPage, ReviewsPage } from '@/pages/reviews/ReviewsPage'
import { TaskPage } from '@/pages/practice/TaskPage'
import { LoginPage } from '@/pages/LoginPage'
import { NotFoundPage } from '@/pages/NotFoundPage'
import { SectionPage } from '@/pages/SectionPage'
import { ContentPage } from '@/pages/workshop/ContentPage'
import { CourseEditorPage } from '@/pages/workshop/CourseEditorPage'
import { GeneratePage } from '@/pages/workshop/GeneratePage'
import { GradingPage } from '@/pages/workshop/GradingPage'
import { GenerateRequestPage } from '@/pages/workshop/GenerateRequestPage'
import { QuizTopicPage } from '@/pages/workshop/QuizTopicPage'
import { SourcesPage } from '@/pages/workshop/SourcesPage'
import { SystemPage } from '@/pages/workshop/SystemPage'
import { UsersPage } from '@/pages/workshop/UsersPage'

// Редактор заданий тянет Monaco — грузим его только когда он нужен
const TaskEditorPage = lazy(() => import('@/pages/workshop/TaskEditorPage').then((m) => ({ default: m.TaskEditorPage })))
import { WorkshopOverviewPage } from '@/pages/workshop/WorkshopOverviewPage'

import { AppShell } from './AppShell'
import { RequireAdmin, RequireAuth } from './guards'
import { STUDY_NAV, WORKSHOP_NAV } from './nav'

const sectionRoutes = (items: typeof STUDY_NAV) =>
  items.filter((n) => n.stage).map((n) => ({ path: n.to, element: <SectionPage /> }))

const router = createBrowserRouter([
  {
    element: (
      <AuthProvider>
        <Outlet />
      </AuthProvider>
    ),
    children: [
      { path: '/login', element: <LoginPage /> },
      {
        element: (
          <RequireAuth>
            <MentorProvider>
              <AppShell />
            </MentorProvider>
          </RequireAuth>
        ),
        children: [
          { path: '/', element: <HomePage /> },
          { path: '/courses', element: <CoursesPage /> },
          { path: '/courses/:slug', element: <CoursePage /> },
          { path: '/courses/:slug/lessons/:lessonId', element: <LessonPage /> },
          { path: '/library', element: <LibraryPage /> },
          { path: '/library/:id', element: <FragmentPage /> },
          { path: '/practice', element: <PracticePage /> },
          { path: '/practice/tests/:slug', element: <QuizPage /> },
          // handle.fullBleed: страница задания занимает всё окно, без отступов оболочки
          { path: '/practice/:slug', element: <TaskPage />, handle: { fullBleed: true } },
          { path: '/reviews', element: <ReviewsPage /> },
          { path: '/reviews/:id', element: <ReviewDetailPage /> },
          { path: '/reviews/submissions/:id', element: <SubmissionPage /> },
          { path: '/practice/assignments/:slug', element: <AssignmentPage /> },
          { path: '/practice/arch/:slug', element: <ArchPage /> },
          { path: '/forks', element: <ForksPage /> },
          { path: '/projects', element: <ProjectsPage /> },
          { path: '/projects/:slug', element: <PathPage /> },
          ...sectionRoutes(STUDY_NAV),
          {
            path: '/workshop',
            element: (
              <RequireAdmin>
                <Outlet />
              </RequireAdmin>
            ),
            children: [
              { index: true, element: <WorkshopOverviewPage /> },
              { path: 'system', element: <SystemPage /> },
              { path: 'content', element: <ContentPage /> },
              { path: 'content/:id', element: <CourseEditorPage /> },
              { path: 'content/quiz/:id', element: <QuizTopicPage /> },
              {
                path: 'content/tasks/:id',
                element: (
                  <Suspense fallback={<Skeleton lines={5} />}>
                    <TaskEditorPage />
                  </Suspense>
                ),
              },
              { path: 'generate', element: <GeneratePage /> },
              { path: 'generate/:id', element: <GenerateRequestPage /> },
              { path: 'grading', element: <GradingPage /> },
              { path: 'sources', element: <SourcesPage /> },
              { path: 'users', element: <UsersPage /> },
              ...sectionRoutes(WORKSHOP_NAV),
            ],
          },
        ],
      },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
])

export function App() {
  return <RouterProvider router={router} />
}
