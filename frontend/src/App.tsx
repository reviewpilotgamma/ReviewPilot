import { lazy, Suspense } from "react";
import { createBrowserRouter, Navigate, Outlet, RouterProvider } from "react-router-dom";
import { AppShell } from "@/components/layout/AppShell";
import { ProtectedRoute } from "@/components/layout/ProtectedRoute";
import { FullPageSpinner } from "@/components/ui/Spinner";
import { AuthProvider } from "@/context/AuthContext";

const Landing = lazy(() => import("@/pages/Landing"));
const Login = lazy(() => import("@/pages/Login"));
const Dashboard = lazy(() => import("@/pages/Dashboard"));
const Rules = lazy(() => import("@/pages/Rules"));
const History = lazy(() => import("@/pages/History"));
const Insights = lazy(() => import("@/pages/Insights"));
const Activity = lazy(() => import("@/pages/Activity"));
const Settings = lazy(() => import("@/pages/Settings"));
const NotFound = lazy(() => import("@/pages/NotFound"));

function Root() {
  return (
    <AuthProvider>
      <Suspense fallback={<FullPageSpinner />}>
        <Outlet />
      </Suspense>
    </AuthProvider>
  );
}

export const routes = [
  {
    element: <Root />,
    children: [
      { path: "/", element: <Landing /> },
      { path: "/login", element: <Login /> },
      {
        element: <ProtectedRoute />,
        children: [
          {
            element: <AppShell />,
            children: [
              { path: "/dashboard", element: <Dashboard /> },
              { path: "/rules", element: <Rules /> },
              { path: "/history", element: <History /> },
              { path: "/insights", element: <Insights /> },
              { path: "/activity", element: <Activity /> },
              { path: "/settings", element: <Settings /> },
            ],
          },
        ],
      },
      { path: "/home", element: <Navigate to="/" replace /> },
      { path: "*", element: <NotFound /> },
    ],
  },
];

const router = createBrowserRouter(routes);

export default function App() {
  return <RouterProvider router={router} future={{ v7_startTransition: true }} />;
}
