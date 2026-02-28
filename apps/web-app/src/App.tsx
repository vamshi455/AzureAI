import { BrowserRouter, Routes, Route, NavLink, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MsalProvider, AuthenticatedTemplate, UnauthenticatedTemplate, useMsal } from "@azure/msal-react";
import { PublicClientApplication, EventType } from "@azure/msal-browser";
import { BarChart3, MessageSquare, LifeBuoy, Home, LogIn, LogOut, User } from "lucide-react";

import Dashboard from "./pages/Dashboard";
import AIChat from "./pages/AIChat";
import Support from "./pages/Support";

// --- MSAL Configuration ---
const msalConfig = {
  auth: {
    clientId: import.meta.env.VITE_AZURE_CLIENT_ID || "00000000-0000-0000-0000-000000000000",
    authority: `https://login.microsoftonline.com/${import.meta.env.VITE_AZURE_TENANT_ID || "common"}`,
    redirectUri: import.meta.env.VITE_REDIRECT_URI || window.location.origin,
    postLogoutRedirectUri: window.location.origin,
  },
  cache: {
    cacheLocation: "sessionStorage" as const,
    storeAuthStateInCookie: false,
  },
};

const msalInstance = new PublicClientApplication(msalConfig);

// Set active account on login success
msalInstance.addEventCallback((event) => {
  if (event.eventType === EventType.LOGIN_SUCCESS && event.payload) {
    const payload = event.payload as { account: ReturnType<typeof msalInstance.getAllAccounts>[0] };
    if (payload.account) {
      msalInstance.setActiveAccount(payload.account);
    }
  }
});

// Set active account if one exists
const accounts = msalInstance.getAllAccounts();
if (accounts.length > 0) {
  msalInstance.setActiveAccount(accounts[0]);
}

// --- React Query Client ---
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000,
      retry: 2,
      refetchOnWindowFocus: false,
    },
  },
});

// --- Navigation Component ---
function Navigation() {
  const { instance, accounts } = useMsal();
  const activeAccount = accounts[0];

  const handleLogin = () => {
    instance.loginPopup({
      scopes: ["User.Read", "openid", "profile", "email"],
    }).catch((error) => {
      console.error("Login failed:", error);
    });
  };

  const handleLogout = () => {
    instance.logoutPopup().catch((error) => {
      console.error("Logout failed:", error);
    });
  };

  const navLinkClasses = ({ isActive }: { isActive: boolean }) =>
    `flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
      isActive
        ? "bg-blue-600 text-white shadow-sm"
        : "text-gray-600 hover:bg-gray-100 hover:text-gray-900"
    }`;

  return (
    <header className="bg-white border-b border-gray-200 sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Logo */}
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center">
              <BarChart3 className="w-5 h-5 text-white" />
            </div>
            <span className="text-lg font-bold text-gray-900">Azure Data Platform</span>
          </div>

          {/* Navigation Links */}
          <nav className="flex items-center gap-1">
            <NavLink to="/" end className={navLinkClasses}>
              <Home className="w-4 h-4" />
              Home
            </NavLink>
            <NavLink to="/dashboard" className={navLinkClasses}>
              <BarChart3 className="w-4 h-4" />
              Analytics
            </NavLink>
            <NavLink to="/chat" className={navLinkClasses}>
              <MessageSquare className="w-4 h-4" />
              AI Chat
            </NavLink>
            <NavLink to="/support" className={navLinkClasses}>
              <LifeBuoy className="w-4 h-4" />
              Support
            </NavLink>
          </nav>

          {/* Auth Section */}
          <div className="flex items-center gap-3">
            <AuthenticatedTemplate>
              <div className="flex items-center gap-2 text-sm text-gray-600">
                <User className="w-4 h-4" />
                <span>{activeAccount?.name || activeAccount?.username}</span>
              </div>
              <button
                onClick={handleLogout}
                className="flex items-center gap-1 px-3 py-1.5 text-sm text-gray-600 hover:text-red-600 rounded-lg hover:bg-red-50 transition-colors"
              >
                <LogOut className="w-4 h-4" />
                Sign Out
              </button>
            </AuthenticatedTemplate>
            <UnauthenticatedTemplate>
              <button
                onClick={handleLogin}
                className="flex items-center gap-1 px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 transition-colors"
              >
                <LogIn className="w-4 h-4" />
                Sign In
              </button>
            </UnauthenticatedTemplate>
          </div>
        </div>
      </div>
    </header>
  );
}

// --- Home Page ---
function HomePage() {
  return (
    <div className="max-w-4xl mx-auto py-16 px-4 text-center">
      <h1 className="text-4xl font-bold text-gray-900 mb-4">
        Azure Data Platform
      </h1>
      <p className="text-xl text-gray-600 mb-8">
        Manufacturing & Sales Intelligence Portal
      </p>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mt-12">
        <NavLink
          to="/dashboard"
          className="p-6 bg-white rounded-xl shadow-sm border border-gray-200 hover:shadow-md hover:border-blue-300 transition-all"
        >
          <BarChart3 className="w-10 h-10 text-blue-600 mx-auto mb-4" />
          <h3 className="text-lg font-semibold text-gray-900">Analytics Dashboard</h3>
          <p className="text-sm text-gray-500 mt-2">
            View sales KPIs, demand forecasts, and manufacturing metrics
          </p>
        </NavLink>
        <NavLink
          to="/chat"
          className="p-6 bg-white rounded-xl shadow-sm border border-gray-200 hover:shadow-md hover:border-blue-300 transition-all"
        >
          <MessageSquare className="w-10 h-10 text-blue-600 mx-auto mb-4" />
          <h3 className="text-lg font-semibold text-gray-900">AI Assistant</h3>
          <p className="text-sm text-gray-500 mt-2">
            Query AI agents for insights, forecasts, and analysis
          </p>
        </NavLink>
        <NavLink
          to="/support"
          className="p-6 bg-white rounded-xl shadow-sm border border-gray-200 hover:shadow-md hover:border-blue-300 transition-all"
        >
          <LifeBuoy className="w-10 h-10 text-blue-600 mx-auto mb-4" />
          <h3 className="text-lg font-semibold text-gray-900">Support</h3>
          <p className="text-sm text-gray-500 mt-2">
            Create and track support tickets via Plane
          </p>
        </NavLink>
      </div>
    </div>
  );
}

// --- Main App ---
export default function App() {
  return (
    <MsalProvider instance={msalInstance}>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <div className="min-h-screen bg-gray-50">
            <Navigation />
            <main>
              <Routes>
                <Route path="/" element={<HomePage />} />
                <Route path="/dashboard" element={<Dashboard />} />
                <Route path="/chat" element={<AIChat />} />
                <Route path="/support" element={<Support />} />
                <Route path="*" element={<Navigate to="/" replace />} />
              </Routes>
            </main>
            <footer className="border-t border-gray-200 bg-white mt-auto">
              <div className="max-w-7xl mx-auto px-4 py-4 text-center text-sm text-gray-500">
                Azure Data Platform v1.0.0 | Manufacturing & Sales
              </div>
            </footer>
          </div>
        </BrowserRouter>
      </QueryClientProvider>
    </MsalProvider>
  );
}
