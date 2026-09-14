/**
 * The actual request path, drawn. Used on the sign-in hero so the first screen
 * says what Niyan does instead of showing abstract shapes.
 */
const STAGES = [
  { id: "client", label: "Client", note: "OpenAI SDK" },
  { id: "gateway", label: "Gateway", note: ":4000" },
  { id: "guard", label: "Guardrails", note: "in · out" },
  { id: "router", label: "LiteLLM", note: "routing" },
];

const SINKS = [
  { id: "ollama", label: "Ollama", note: "llama · gemma" },
  { id: "cloud", label: "Cloud", note: "gpt · gemini · claude" },
];

export function Schematic() {
  return (
    <figure className="schematic" aria-label="Request path: client to gateway to guardrails to LiteLLM to models">
      <div className="schematic-line">
        {STAGES.map((s, i) => (
          <div key={s.id} className="schematic-node" style={{ animationDelay: `${260 + i * 90}ms` }}>
            <span className="schematic-dot" />
            <span className="schematic-label">{s.label}</span>
            <span className="schematic-note">{s.note}</span>
          </div>
        ))}
      </div>
      <div className="schematic-fan" aria-hidden>
        <span className="schematic-fan-stem" />
        <div className="schematic-sinks">
          {SINKS.map((s, i) => (
            <div key={s.id} className="schematic-sink" style={{ animationDelay: `${640 + i * 90}ms` }}>
              <span className="schematic-label">{s.label}</span>
              <span className="schematic-note">{s.note}</span>
            </div>
          ))}
        </div>
      </div>
    </figure>
  );
}
