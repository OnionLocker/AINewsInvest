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
      ? "bg-rose-500 hover:bg-rose-600 shadow-rose-500/20"
      : "bg-indigo-500 hover:bg-indigo-600 shadow-indigo-500/20";

  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      {state &&
        createPortal(
          <div className="fixed inset-0 z-[9998] flex items-center justify-center">
            <div
              className="absolute inset-0 bg-black/60 backdrop-blur-sm"
              onClick={() => handleClose(false)}
            />
            <div className="relative w-full max-w-sm rounded-3xl border border-white/[0.06] bg-neutral-900/95 p-7 shadow-2xl backdrop-blur-xl">
              <h3 className="text-base font-semibold text-white">{state.title}</h3>
              <p className="mt-2 text-[15px] text-neutral-400">{state.message}</p>
              <div className="mt-6 flex justify-end gap-3">
                <button
                  onClick={() => handleClose(false)}
                  className="rounded-xl px-5 py-2.5 text-[15px] text-neutral-400 transition-colors hover:bg-white/[0.06] hover:text-white"
                >
                  取消
                </button>
                <button
                  onClick={() => handleClose(true)}
                  className={`rounded-xl px-5 py-2.5 text-[15px] font-medium text-white shadow-lg transition-colors ${btnColor}`}
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
