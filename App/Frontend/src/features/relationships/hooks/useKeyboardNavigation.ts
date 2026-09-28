import { useEffect } from "react";

function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return Boolean(
    target.closest(
      "input, textarea, select, [contenteditable='true'], .code-input, .journal-editor",
    ),
  );
}

export function useKeyboardNavigation(handlers: {
  onSearch: () => void;
  onViewFromSelected: () => void;
  onCompare: () => void;
  onShowPrimaryPath: () => void;
  onReturnHome: () => void;
  onExitPath: () => void;
  onEscape: () => void;
}) {
  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (isTypingTarget(event.target)) return;
      const key = event.key.toLowerCase();
      const modifier = event.ctrlKey || event.metaKey;
      if (modifier && key === "k") {
        event.preventDefault();
        handlers.onSearch();
        return;
      }
      if (event.altKey || event.ctrlKey || event.metaKey) return;
      if (key === "escape") {
        handlers.onEscape();
      } else if (key === "v") {
        handlers.onViewFromSelected();
      } else if (key === "c") {
        handlers.onCompare();
      } else if (key === "p") {
        handlers.onShowPrimaryPath();
      } else if (key === "h") {
        handlers.onReturnHome();
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [handlers]);
}
