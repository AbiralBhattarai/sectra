import { Component, type ReactNode } from "react";

interface Props {
  label: string;
  children: ReactNode;
}

/** Keeps a crash in one panel from unmounting the whole app; shows the error instead. */
export class ErrorBoundary extends Component<Props, { error: Error | null }> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error) {
    console.error(`${this.props.label} crashed:`, error);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="panel">
        <p className="error">
          {this.props.label} crashed: {this.state.error.message}
        </p>
        <button type="button" className="small" onClick={() => this.setState({ error: null })}>
          Try again
        </button>
      </div>
    );
  }
}
