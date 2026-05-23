import "./globals.css";
import type { Metadata, Viewport } from "next";

export const metadata: Metadata = {
  title: "Ultimate Tracker — 2026 D-I Men's",
  description: "Live pool standings, deterministic scenarios, and projected bracket for the 2026 USAU D-I College Men's Championships.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#0b0d10",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen">
        <main className="mx-auto max-w-screen-md px-3 pb-24 pt-3">{children}</main>
      </body>
    </html>
  );
}
