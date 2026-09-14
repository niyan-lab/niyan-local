import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { IconArrow, IconSearch } from "./icons";

export type PaletteItem = {
  to: string;
  label: string;
  group: string;
  hint: string;
};

export function CommandPalette({
  items,
  open,
  onClose,
}: {
  items: PaletteItem[];
  open: boolean;
  onClose: () => void;
}) {
  const nav = useNavigate();
  const [query, setQuery] = useState("");
  const [cursor, setCursor] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const results = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return items;
    return items.filter(
      (i) => i.label.toLowerCase().includes(q) || i.hint.toLowerCase().includes(q) || i.group.toLowerCase().includes(q)
    );
  }, [items, query]);

  useEffect(() => {
    if (!open) return;
    setQuery("");
    setCursor(0);
    const id = window.setTimeout(() => inputRef.current?.focus(), 40);
    return () => window.clearTimeout(id);
  }, [open]);

  useEffect(() => {
    setCursor(0);
  }, [query]);

  if (!open) return null;

  function go(to: string) {
    nav(to);
    onClose();
  }

  function onKeyDown(e: React.KeyboardEvent) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setCursor((c) => (results.length ? (c + 1) % results.length : 0));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setCursor((c) => (results.length ? (c - 1 + results.length) % results.length : 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      const item = results[cursor];
      if (item) go(item.to);
    } else if (e.key === "Escape") {
      e.preventDefault();
      onClose();
    }
  }

  return (
    <div className="palette-veil" onMouseDown={onClose} role="presentation">
      <div
        className="palette"
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
        onMouseDown={(e) => e.stopPropagation()}
        onKeyDown={onKeyDown}
      >
        <div className="palette-field">
          <IconSearch className="palette-field-icon" />
          <input
            ref={inputRef}
            value={query}
            placeholder="Jump to a section…"
            onChange={(e) => setQuery(e.target.value)}
            aria-label="Search sections"
          />
          <kbd className="kbd">esc</kbd>
        </div>
        <div className="palette-list">
          {results.length === 0 ? (
            <p className="palette-empty">Nothing matches “{query}”.</p>
          ) : (
            results.map((item, i) => (
              <button
                key={item.to}
                type="button"
                className={`palette-row ${i === cursor ? "is-cursor" : ""}`}
                onMouseEnter={() => setCursor(i)}
                onClick={() => go(item.to)}
              >
                <span className="palette-row-main">
                  <span className="palette-row-label">{item.label}</span>
                  <span className="palette-row-hint">{item.hint}</span>
                </span>
                <span className="palette-row-group">{item.group}</span>
                <IconArrow className="palette-row-arrow" />
              </button>
            ))
          )}
        </div>
        <div className="palette-foot">
          <span>
            <kbd className="kbd">↑</kbd>
            <kbd className="kbd">↓</kbd> navigate
          </span>
          <span>
            <kbd className="kbd">↵</kbd> open
          </span>
        </div>
      </div>
    </div>
  );
}
