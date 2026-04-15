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
  success: { text: "#16A34A", bg: "rgba(22,163,74,0.08)", border: "rgba(22,163,74,0.2)" },
  error: { text: "#DC2626", bg: "rgba(220,38,38,0.08)", border: "rgba(220,38,38,0.2)" },
  info: { text: "#2563EB", bg: "rgba(37,99,235,0.08)", border: "rgba(37,99,235,0.2)" },
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
      className="pointer-events-auto flex items-start gap-3 rounded-2xl border border-border bg-white px-5 py-4 shadow-lg transition-all duration-200"
      style={{
        borderLeftColor: c.border,
        borderLeftWidth: 3,
        opacity: visible ? 1 : 0,
        transform: visible ? "translateX(0)" : "translateX(100%)",
        maxWidth: 360,
      }}
    >
      <Icon size={18} style={{ color: c.text, marginTop: 2, flexShrink: 0 }} />
      <p className="flex-1 text-[15px] text-primary">{item.message}</p>
      <button
        onClick={() => { setVisible(false); setTimeout(() => onRemove(item.id), 200); }}
        className="text-tertiary hover:text-primary"
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

  useEffect(() => {
    const handler = (e) => {
      const { message, status } = e.detail || {};
      // Don't toast 401s (handled by redirect)
      if (status === 401) return;
      toast({
        type: "error",
        message: message || "请求失败，请稍后重试",
        duration: 4000,
      });
    };
    window.addEventListener("api-error", handler);
    return () => window.removeEventListener("api-error", handler);
  }, [toast]);

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
