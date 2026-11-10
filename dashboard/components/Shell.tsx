"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV = [
  { href: "/", label: "Overview" },
  { href: "/compare", label: "Compare" },
];

export default function Shell({ children }: { children: React.ReactNode }) {
  const path = (usePathname() || "/").replace(/\/$/, "") || "/";
  return (
    <main className="mx-auto max-w-5xl px-4 py-8 sm:px-6">
      <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Indian Market PE Tracker</h1>
          <p className="text-sm text-[var(--text-secondary)]">Is the market cheap or expensive vs its own history?</p>
        </div>
        <nav aria-label="Primary" className="flex gap-1">
          {NAV.map((n) => (
            <Link
              key={n.href}
              href={n.href}
              aria-current={path === n.href ? "page" : undefined}
              className="rounded-lg border border-[var(--border)] px-3 py-1.5 text-sm aria-[current=page]:bg-[var(--text-primary)] aria-[current=page]:text-[var(--surface)]"
            >
              {n.label}
            </Link>
          ))}
        </nav>
      </header>
      {children}
    </main>
  );
}
