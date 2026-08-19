import type { ReactNode } from "react";

/** Compact table rows -- the chosen density for Jobs/Resumes/match lists. */
export function Table({ children }: { children: ReactNode }) {
  return (
    <div className="overflow-x-auto rounded border" style={{ borderColor: "var(--border)" }}>
      <table className="w-full border-collapse text-sm">{children}</table>
    </div>
  );
}

export function TableHead({ columns }: { columns: string[] }) {
  return (
    <thead>
      <tr style={{ background: "var(--canvas-subtle)" }}>
        {columns.map((col) => (
          <th
            key={col}
            className="border-b px-3 py-2 text-left font-medium"
            style={{ borderColor: "var(--border)", color: "var(--fg-muted)" }}
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
      className={`border-b px-3 py-2 ${mono ? "font-mono" : ""}`}
      style={{ borderColor: "var(--border)" }}
    >
      {children}
    </td>
  );
}
