import { createContext, useContext, useState, useCallback, useEffect } from "react";
import { createPortal } from "react-dom";
import { CheckCircle2, XCircle, Info, X } from "lucide-react";

const ToastContext = createContext(null);

const ICONS = {
  success: CheckCircle2,
  error: XCircle,
  info: Info,
};

const COLORS = {
  success: { text: "#34d399", bg: "rgba(52,211,153,0.08)", border: "rgba(52,211,153,0.2)" },
  error: { text: "#fb7185", bg: "rgba(251,113,133,0.08)", border: "rgba(251,113,133,0.2)" },
  info: { text: "#818cf8", bg: "rgba(129,140,248,0.08)", border: "rgba(129,140,248,0.2)" },
};

let toastId = 0;

function ToastItem({ item, onRemove }) {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    requestAnimationFrame(() => setVisible(true));
    const timer = setTimeout(() => {
      setVisible(false);
      setTimeout(() => onRemove(item.id), 200);
    }, item.duration || 3000);
    return () => clearTimeout(timer);
  }, [item, onRemove]);

  const Icon = ICONS[item.type] || ICONS.info;
  const c = COLORS[item.type] || COLORS.info;

  return (
    <div
      className="pointer-events-auto flex items-start gap-3 rounded-2xl border px-5 py-4 shadow-2xl backdrop-blur-xl transition-all duration-200"
      style={{
        background: "rgba(10,10,10,0.95)",
        borderColor: c.border,
        opacity: visible ? 1 : 0,
        transform: visible ? "translateX(0)" : "translateX(100%)",
        maxWidth: 360,
      }}
    >
      <Icon size={18} style={{ color: c.text, marginTop: 2, flexShrink: 0 }} />
      <p className="flex-1 text-[15px] text-white/90">{item.message}</p>
      <button
        onClick={() => { setVisible(false); setTimeout(() => onRemove(item.id), 200); }}
        className="text-neutral-500 hover:text-white"
      >
        <X size={14} />
      </button>
    </div>
  );
}

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);

  const toast = useCallback(({ type = "info", message, duration = 3000 }) => {
    const id = ++toastId;
    setToasts((prev) => [...prev, { id, type, message, duration }]);
  }, []);

  const remove = useCallback((id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  return (
    <ToastContext.Provider value={toast}>
      {children}
      {createPortal(
        <div className="pointer-events-none fixed top-4 right-4 z-[9999] flex flex-col gap-2">
          {toasts.map((t) => (
            <ToastItem key={t.id} item={t} onRemove={remove} />
          ))}
        </div>,
        document.body,
      )}
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within ToastProvider");
  return ctx;
}
