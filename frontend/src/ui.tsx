import { useEffect, useRef } from "react";
import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
export const segmentName = (value: string) =>
  ({
    inventory: "Stock & inventory",
    contractors: "Projects & contractors",
    no_mail: "No-mail control",
    excluded: "Excluded",
  })[value] ?? value;
export function Badge({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: string;
}) {
  return <span className={`badge ${tone}`}>{children}</span>;
}
export function Empty({
  icon: Icon,
  title,
  children,
}: {
  icon: LucideIcon;
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="empty">
      <Icon size={28} />
      <h2>{title}</h2>
      <div>{children}</div>
    </div>
  );
}
export function Modal({
  children,
  label,
  busy,
  onClose,
}: {
  children: ReactNode;
  label: string;
  busy: boolean;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    dialog?.showModal();
    dialog?.querySelector<HTMLElement>("textarea, input")?.focus();
    return () => {
      dialog?.close();
    };
  }, []);
  return (
    <dialog
      ref={ref}
      className="modal"
      aria-labelledby={label}
      onCancel={(e) => {
        e.preventDefault();
        if (!busy) onClose();
      }}
      onClick={(e) => {
        if (e.target === ref.current && !busy) {
          const r = ref.current!.getBoundingClientRect();
          if (
            e.clientX < r.left ||
            e.clientX > r.right ||
            e.clientY < r.top ||
            e.clientY > r.bottom
          )
            onClose();
        }
      }}
    >
      {children}
    </dialog>
  );
}
