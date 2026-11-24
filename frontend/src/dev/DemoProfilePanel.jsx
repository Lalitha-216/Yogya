import "./demoProfile.css";
import { DEMO_COPY } from "./demoProfile";

// DEVELOPMENT ONLY. Rendered from App.jsx behind `import.meta.env.DEV`.
export default function DemoProfilePanel({ language, tradeLabel, disabled, onUse }) {
  const c = DEMO_COPY[language] || DEMO_COPY.en;
  return (
    <div className="dev-demo" role="region" aria-label={c.useDemo}>
      <div className="dev-demo-body">
        <span className="dev-demo-tag">{c.tag}</span>
        <p>{c.hint.replace("{trade}", tradeLabel)}</p>
      </div>
      <button type="button" className="dev-demo-button" onClick={onUse} disabled={disabled}>
        {c.useDemo}
      </button>
    </div>
  );
}
