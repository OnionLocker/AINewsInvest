import { Component } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error("ErrorBoundary caught:", error, errorInfo);
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex flex-col items-center justify-center rounded-2xl border border-red-200 bg-red-50 p-8 text-center">
          <AlertTriangle size={36} className="text-red-400" />
          <h2 className="mt-4 text-lg font-semibold text-red-700">页面加载出错</h2>
          <p className="mt-2 max-w-md text-sm text-red-500">
            {this.state.error?.message || "发生了未知错误，请刷新重试"}
          </p>
          <div className="mt-4 flex gap-3">
            <button
              onClick={this.handleReset}
              className="flex items-center gap-2 rounded-lg bg-red-100 px-4 py-2 text-sm font-medium text-red-700 transition-colors hover:bg-red-200"
            >
              <RefreshCw size={14} />
              重试
            </button>
            <button
              onClick={() => window.location.reload()}
              className="rounded-lg bg-surface-3 px-4 py-2 text-sm font-medium text-secondary transition-colors hover:bg-surface-2"
            >
              刷新页面
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
