export default function StatusPill({ status = "idle", label, className = "" }) {
  return (
    <span className={`status-pill status-pill--${status} ${className}`.trim()}>
      <span aria-hidden="true" className="status-pill__dot" />
      <span>{label ?? status}</span>
    </span>
  );
}
