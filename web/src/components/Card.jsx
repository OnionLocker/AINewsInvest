export default function Card({ children, className = "", ...props }) {
  return (
    <div
      className={`rounded-3xl border border-white/[0.06] bg-white/[0.04] backdrop-blur-md p-6 ${className}`}
      {...props}
    >
      {children}
    </div>
  );
}

export function CardTitle({ children, className = "" }) {
  return (
    <h3 className={`mb-4 text-sm font-semibold tracking-normal text-neutral-500 ${className}`}>
      {children}
    </h3>
  );
}
