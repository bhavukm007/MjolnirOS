import { Icon } from "../ui/index.js";

export default function StatusBar({ connectionState, model, moduleCount }) {
  const time = new Intl.DateTimeFormat([], { hour: "2-digit", minute: "2-digit" }).format(new Date());
  return (
    <footer className="os-statusbar" aria-label="System status">
      <div className="os-statusbar__group">
        <span><i className="status-dot status-dot--voice" />Voice ready</span>
        <span><i className={`status-dot status-dot--${connectionState}`} />Backend {connectionState}</span>
        <span><Icon name="memory" size={13} />Memory local</span>
      </div>
      <div className="os-statusbar__group os-statusbar__group--right">
        <span>{moduleCount} modules</span><span>{model || "Local model"}</span><span>CPU nominal</span><span><Icon name="clock" size={13} />{time}</span>
      </div>
    </footer>
  );
}
