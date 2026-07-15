export default function GlassCard({ as: Component = "section", className = "", children, interactive = false, ...props }) {
  return (
    <Component
      className={`glass-card ${interactive ? "glass-card--interactive" : ""} ${className}`.trim()}
      {...props}
    >
      {children}
    </Component>
  );
}
