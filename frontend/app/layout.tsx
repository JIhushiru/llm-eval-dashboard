import type { Metadata } from "next";
import "./globals.css";
import Nav from "@/components/Nav";
import { ThemeProvider } from "@/components/ThemeProvider";

export const metadata: Metadata = {
  title: "EvalForge",
  description: "LLM evaluation dashboard — suites, runs, scoring, regressions",
};

// Runs synchronously before first paint to set the theme attribute from the
// stored preference (default: system), so there's no flash of the wrong theme.
const NO_FLASH = `!function(){try{var t=localStorage.getItem("theme")||"system",d="dark"===t||("system"===t&&matchMedia("(prefers-color-scheme: dark)").matches),e=document.documentElement;e.setAttribute("data-theme",d?"dark":"light"),e.style.colorScheme=d?"dark":"light"}catch(e){}}();`;

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="min-h-screen bg-page font-sans text-ink antialiased">
        <script dangerouslySetInnerHTML={{ __html: NO_FLASH }} />
        <ThemeProvider>
          <Nav />
          <main className="mx-auto max-w-6xl px-6 py-8">{children}</main>
        </ThemeProvider>
      </body>
    </html>
  );
}
