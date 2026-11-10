import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Nifty 50 PE Tracker",
  description: "Is the market cheap or expensive vs its own history? A SIP-timing helper.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">{children}</body>
    </html>
  );
}
