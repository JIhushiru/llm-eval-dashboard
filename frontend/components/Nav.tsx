"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/", label: "Dashboard" },
  { href: "/suites", label: "Suites" },
  { href: "/runs", label: "Runs" },
  { href: "/compare", label: "Compare" },
] as const;

export default function Nav() {
  const pathname = usePathname();
  return (
    <header className="border-b border-hairline bg-surface">
      <nav className="mx-auto flex max-w-6xl items-center gap-8 px-6 py-3">
        <Link href="/" className="text-base font-semibold text-ink">
          EvalForge
        </Link>
        <div className="flex items-center gap-1">
          {LINKS.map((l) => {
            const active =
              l.href === "/" ? pathname === "/" : pathname.startsWith(l.href);
            return (
              <Link
                key={l.href}
                href={l.href}
                className={
                  active
                    ? "rounded-md bg-page px-3 py-1.5 text-sm font-medium text-ink"
                    : "rounded-md px-3 py-1.5 text-sm text-ink2 hover:bg-page hover:text-ink"
                }
              >
                {l.label}
              </Link>
            );
          })}
        </div>
      </nav>
    </header>
  );
}
