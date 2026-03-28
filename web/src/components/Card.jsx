export default function Card({ children, className = "", ...props }) {
  return (
    <div
      className={`rounded-xl border border-surface-3 bg-surface-1 p-4 ${className}`}
      {...props}
    >
      {children}
    </div>
  );
}

export function CardTitle({ children, className = "" }) {
  return (
    <h3 className={`mb-3 text-sm font-semibold text-gray-300 ${className}`}>
      {children}
    </h3>
  );
}
