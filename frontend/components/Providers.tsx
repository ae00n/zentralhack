"use client";

// Client-side providers, mounted once in the layout: the sonner toaster (bottom centre, white, hairline).
import { Toaster } from "sonner";

export default function Providers({ children }: { children: React.ReactNode }) {
  return (
    <>
      {children}
      <Toaster
        position="bottom-center"
        toastOptions={{
          classNames: { toast: "bg-paper border border-rule/[0.08] shadow-pop text-ui rounded-lg font-sans text-ink" },
        }}
      />
    </>
  );
}
