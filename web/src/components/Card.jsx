export default function Card({ children, className = "", ...props }) {
  return (
    <div
      className={`rounded-2xl border border-slate-800/80 bg-slate-900/40 backdrop-blur-md p-4 shadow-xl ${className}`}
      {...props}
    >
      {children}
    </div>
  );
}

export function CardTitle({ children, className = "" }) {
  return (
    <h3 className={`mb-3 text-xs font-semibold uppercase tracking-wider text-slate-400 ${className}`}>
      {children}
    </h3>
  );
}
