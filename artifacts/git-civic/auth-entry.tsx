import React, { useEffect } from "react";
import { createRoot } from "react-dom/client";
import { ClerkProvider, SignInButton, UserButton, useAuth } from "@clerk/react";
import { publishableKeyFromHost } from "@clerk/react/internal";

declare global {
  interface Window {
    gitCivicAuth?: { isSignedIn: boolean; getToken: () => Promise<string | null> };
    gitCivicAuthReady?: Promise<void>;
  }
}

let signalAuthReady: () => void = () => {};
window.gitCivicAuthReady = new Promise<void>((resolve) => { signalAuthReady = resolve; });
const publishableKey = publishableKeyFromHost(
  window.location.hostname,
  import.meta.env.VITE_CLERK_PUBLISHABLE_KEY,
);
const clerkProxyUrl = import.meta.env.VITE_CLERK_PROXY_URL;

function AuthBridge() {
  const { isLoaded, isSignedIn, getToken } = useAuth();
  useEffect(() => {
    if (!isLoaded) return;
    window.gitCivicAuth = { isSignedIn: Boolean(isSignedIn), getToken };
    signalAuthReady();
    window.dispatchEvent(new Event("git-civic-auth-changed"));
  }, [getToken, isLoaded, isSignedIn]);
  return (
    <div className="auth-controls" aria-live="polite">
      {isSignedIn ? (
        <UserButton />
      ) : (
        <SignInButton mode="modal">
          <button className="auth-sign-in" type="button">Sign in</button>
        </SignInButton>
      )}
    </div>
  );
}

const target = document.getElementById("auth-controls");
if (target) {
  createRoot(target).render(
    <ClerkProvider
      publishableKey={publishableKey}
      proxyUrl={clerkProxyUrl}
      appearance={{
        variables: {
          colorPrimary: "#176c60",
          colorForeground: "#173d39",
          colorMutedForeground: "#657674",
          colorBackground: "#fbfaf5",
          colorInput: "#fffefa",
          colorInputForeground: "#173d39",
          borderRadius: "0.45rem",
          fontFamily: "Inter, sans-serif",
        },
      }}
    >
      <AuthBridge />
    </ClerkProvider>,
  );
}