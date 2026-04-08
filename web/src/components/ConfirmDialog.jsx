import { createContext, useContext, useState, useCallback } from "react";
import { createPortal } from "react-dom";

const ConfirmContext = createContext(null);

export function ConfirmProvider({ children }) {
  const [state, setState] = useState(null);

  const confirm = useCallback(({ title = "确认操作", message, variant = "danger" }) => {
    return new Promise((resolve) => {
      setState({ title, message, variant, resolve });
    });
  }, []);

  function handleClose(result) {
    state?.resolve(result);
    setState(null);
  }

  const btnColor =
    state?.variant === "danger"
      ? "bg-down hover:bg-[#B91C1C] text-white shadow-md shadow-down/15"
      : "bg-brand hover:bg-[#A04E30] text-white shadow-md shadow-brand/15";

  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      {state &&
        createPortal(
          <div className="fixed inset-0 z-[9998] flex items-center justify-center">
            <div
              className="absolute inset-0 bg-primary/30 backdrop-blur-sm"
              onClick={() => handleClose(false)}
            />
            <div className="relative w-full max-w-sm rounded-2xl border border-border bg-white p-7 shadow-xl">
              <h3 className="text-base font-semibold text-primary">{state.title}</h3>
              <p className="mt-2 text-[15px] text-secondary">{state.message}</p>
              <div className="mt-6 flex justify-end gap-3">
                <button
                  onClick={() => handleClose(false)}
                  className="rounded-xl px-5 py-2.5 text-[15px] text-secondary transition-colors hover:bg-surface-2 hover:text-primary"
                >
                  取消
                </button>
                <button
                  onClick={() => handleClose(true)}
                  className={`rounded-xl px-5 py-2.5 text-[15px] font-medium transition-colors ${btnColor}`}
                >
                  确认
                </button>
              </div>
            </div>
          </div>,
          document.body,
        )}
    </ConfirmContext.Provider>
  );
}

export function useConfirm() {
  const ctx = useContext(ConfirmContext);
  if (!ctx) throw new Error("useConfirm must be used within ConfirmProvider");
  return ctx;
}
