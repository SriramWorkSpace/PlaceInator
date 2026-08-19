import type { ReactNode } from "react";

/** Compact table rows -- the chosen density for Jobs/Resumes/match lists. */
export function Table({ children }: { children: ReactNode }) {
  return (
    <div
      className="card overflow-x-auto rounded-[var(--radius-input)] border"
      style={{ borderColor: "var(--border)", background: "var(--canvas-subtle)" }}
    >
      <table className="w-full border-collapse text-sm">{children}</table>
    </div>
  );
}

export function TableHead({ columns }: { columns: string[] }) {
  return (
    <thead>
      <tr>
        {columns.map((col) => (
          <th
            key={col}
            className="eyebrow border-b px-4 py-3 text-left"
            style={{ borderColor: "var(--border)", color: "var(--fg-subtle)" }}
          >
            {col}
          </th>
        ))}
      </tr>
    </thead>
  );
}

export function TableRow({ children }: { children: ReactNode }) {
  return <tr>{children}</tr>;
}

export function TableCell({ children, mono = false }: { children: ReactNode; mono?: boolean }) {
  return (
    <td
      className={`border-b px-4 py-3 ${mono ? "font-mono" : ""}`}
      style={{ borderColor: "var(--border)" }}
    >
      {children}
    </td>
  );
}
