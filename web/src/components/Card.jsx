export default function Card({ children, className = "", ...props }) {
  return (
    <div
      className={`rounded-2xl border border-border bg-white shadow-sm p-6 ${className}`}
      {...props}
    >
      {children}
    </div>
  );
}

export function CardTitle({ children, className = "" }) {
  return (
    <h3 className={`mb-4 text-sm font-semibold tracking-normal text-secondary ${className}`}>
      {children}
    </h3>
  );
}
