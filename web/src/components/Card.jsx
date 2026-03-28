export default function Card({ children, className = "", ...props }) {
  return (
    <div
      className={`rounded-lg border border-[#2a2e39] bg-[#1e222d] p-4 ${className}`}
      {...props}
    >
      {children}
    </div>
  );
}

export function CardTitle({ children, className = "" }) {
  return (
    <h3 className={`mb-3 text-xs font-semibold text-[#d1d4dc] ${className}`}>
      {children}
    </h3>
  );
}
