import { createBrowserRouter, RouterProvider } from "react-router-dom";
import { AppShell } from "@/components/AppShell";
import { ChatPage } from "@/pages/ChatPage";
import { PagesPage } from "@/pages/PagesPage";

const router = createBrowserRouter([
  {
    path: "/",
    element: <AppShell />,
    children: [
      { index: true, element: <ChatPage /> },
      { path: "pages", element: <PagesPage /> },
    ],
  },
]);

export function App() {
  return <RouterProvider router={router} />;
}
