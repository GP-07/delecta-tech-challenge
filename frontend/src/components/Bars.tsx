import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { ReactNode } from "react";

// One series of bars in a single color (slot 1). Horizontal for ranked categories (long labels), vertical for
// ordered buckets. Hovering a bar shows `tooltip`; with `onSelect` a click selects it and the others fade.
export function Bars<T extends object>({ data, label, value, format, tooltip, layout = "horizontal", selected,
  onSelect, height }: {
  data: T[];
  label: keyof T & string;
  value: keyof T & string;
  format: (value: number) => string;
  tooltip: (row: T) => ReactNode;
  layout?: "horizontal" | "vertical";
  selected?: string | null;
  onSelect?: (row: T) => void;
  height?: number;
}) {
  const horizontal = layout === "horizontal";
  const chartHeight = height ?? (horizontal ? Math.max(120, data.length * 30 + 30) : 220);
  return (
    <ResponsiveContainer width="100%" height={chartHeight}>
      <BarChart data={data} layout={horizontal ? "vertical" : "horizontal"} barCategoryGap={horizontal ? 6 : "18%"}
        margin={{ top: 4, right: 16, bottom: 4, left: 4 }}>
        <CartesianGrid stroke="var(--grid)" horizontal={!horizontal} vertical={horizontal} />
        {horizontal ? (
          <>
            <XAxis type="number" tickFormatter={format} stroke="var(--axis)" tickLine={false} />
            <YAxis type="category" dataKey={label as string} width={150} stroke="var(--axis)" tickLine={false} interval={0} />
          </>
        ) : (
          <>
            <XAxis type="category" dataKey={label as string} stroke="var(--axis)" tickLine={false} interval={0} />
            <YAxis type="number" tickFormatter={format} stroke="var(--axis)" tickLine={false} width={56} />
          </>
        )}
        <Tooltip cursor={{ fill: "var(--hover)" }} isAnimationActive={false}
          content={({ active, payload }) =>
            active && payload?.length ? <div className="chart-tooltip">{tooltip(payload[0].payload as T)}</div> : null} />
        <Bar dataKey={value as string} radius={horizontal ? [0, 4, 4, 0] : [4, 4, 0, 0]} isAnimationActive={false}
          cursor={onSelect ? "pointer" : undefined} onClick={onSelect ? (entry) => onSelect(entry.payload as T) : undefined}>
          {data.map((row) => {
            const key = String(row[label]);
            const faded = selected != null && selected !== key;
            return <Cell key={key} fill={faded ? "var(--series-1-soft)" : "var(--series-1)"} />;
          })}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
