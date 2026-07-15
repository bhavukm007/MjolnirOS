export default function Button({ variant = "secondary", size = "md", className = "", children, ...props }) {
  return (
    <button className={`os-button os-button--${variant} os-button--${size} ${className}`.trim()} {...props}>
      <span className="os-button__content">{children}</span>
    </button>
  );
}
