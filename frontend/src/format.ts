const integer = new Intl.NumberFormat("es-ES");
const percent = new Intl.NumberFormat("es-ES", { style: "percent", maximumFractionDigits: 1 });
const euros = new Intl.NumberFormat("es-ES", { style: "currency", currency: "EUR" });
const decimal = new Intl.NumberFormat("es-ES", { maximumFractionDigits: 2 });

export const fmt = {
  int: (value: number) => integer.format(value),
  pct: (value: number) => percent.format(value),
  eur: (value: number | null) => (value == null ? "—" : euros.format(value)),
  num: (value: number | null) => (value == null ? "—" : decimal.format(value)),
  share: (part: number, total: number) => (total ? percent.format(part / total) : "—"),
  duration: (seconds: number | null) => {
    if (seconds == null) return "—";
    if (seconds < 60) return `${seconds} s`;
    const minutes = Math.round(seconds / 60);
    return minutes < 60 ? `${minutes} min` : `${Math.floor(minutes / 60)} h ${minutes % 60} min`;
  },
  date: (iso: string) =>
    new Date(iso).toLocaleString("es-ES", { dateStyle: "medium", timeStyle: "short", timeZone: "Europe/Madrid" }),
};
