import type { ReactNode } from "react";

/**
 * Placeholder page chrome. Each MVP route renders a PageStub with its title
 * and a "coming online in week X" hint until its full implementation lands.
 */
export default function PageStub({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children?: ReactNode;
}) {
  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {subtitle ? (
          <p className="text-sm text-zinc-600">{subtitle}</p>
        ) : null}
      </header>
      <section className="rounded-lg border border-dashed border-zinc-300 bg-white p-6 text-sm text-zinc-500">
        {children ?? "This page is scaffolding only; the data and interactions land in a later milestone."}
      </section>
    </div>
  );
}
