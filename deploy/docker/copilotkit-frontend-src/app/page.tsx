"use client";

import { CopilotKit } from "@copilotkit/react-core";
import { CopilotSidebar } from "@copilotkit/react-ui";
import "@copilotkit/react-ui/styles.css";
import { signIn, signOut, useSession } from "next-auth/react";
import { SessionProvider } from "next-auth/react";

function ChatContent() {
  const { data: session, status } = useSession();
  const authEnabled = process.env.NEXT_PUBLIC_AUTH_ENABLED === 'true';
  const copilotKitUrl = process.env.NEXT_PUBLIC_COPILOTKIT_URL || "http://langgraph-server:8000/copilotkit";

  if (authEnabled && status === "loading") {
    return <div className="flex h-screen items-center justify-center">Loading...</div>;
  }

  if (authEnabled && !session) {
    return (
      <div className="flex h-screen flex-col items-center justify-center gap-4">
        <h1 className="text-2xl font-bold">NETTRADES AI Platform</h1>
        <p className="text-gray-600">Please authenticate to access the AI assistant.</p>
        <button
          onClick={() => signIn("odoo")}
          className="rounded bg-blue-600 px-4 py-2 text-white hover:bg-blue-700"
        >
          Login with Odoo
        </button>
      </div>
    );
  }

  return (
    <CopilotKit runtimeUrl={copilotKitUrl}>
      <CopilotSidebar
        labels={{
          title: "NETTRADES AI Assistant",
          initial: "Hello! I'm your autonomous enterprise AI assistant. How can I help you today?",
        }}
      >
        <div className="flex h-screen items-center justify-center">
          <div className="max-w-2xl text-center">
            <h1 className="mb-4 text-4xl font-bold text-gray-800">
              NETTRADES AI Assistant
            </h1>
            <p className="text-gray-600">
              {authEnabled
                ? `Logged in as ${session?.user?.email || session?.user?.name || 'user'}`
                : "Your autonomous enterprise AI is ready."}
              Click the chat icon in the corner to get started.
            </p>
            {authEnabled && (
              <button
                onClick={() => signOut()}
                className="mt-4 text-sm text-red-600 hover:underline"
              >
                Logout
              </button>
            )}
          </div>
        </div>
      </CopilotSidebar>
    </CopilotKit>
  );
}

export default function Home() {
  return (
    <SessionProvider>
      <ChatContent />
    </SessionProvider>
  );
}