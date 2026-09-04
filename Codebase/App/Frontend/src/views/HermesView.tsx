import { useEffect, useState } from "react";
import { api } from "../api";
import { Button, ErrorNote } from "../components/ui";
import type { HermesToolDef } from "../types";

export function HermesView() {
  const [tools, setTools] = useState<HermesToolDef[]>([]);
  const [tool, setTool] = useState("get_relationship");
  const [argumentsText, setArgumentsText] = useState(
    '{\n  "perspective": "mohammad_yahya_hussain",\n  "target": "ezan_asif"\n}',
  );
  const [output, setOutput] = useState<string>("");
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api.hermes
      .tools()
      .then((result) => {
        setTools(result.tools);
        if (result.tools.length) setTool(result.tools[0].name);
      })
      .catch(setError);
  }, []);

  const selectedDef = tools.find((item) => item.name === tool);

  async function run() {
    let parsed: Record<string, unknown> = {};
    if (argumentsText.trim()) {
      try {
        parsed = JSON.parse(argumentsText);
      } catch {
        setError(new Error("Arguments must be valid JSON."));
        return;
      }
    }
    setLoading(true);
    setError(null);
    try {
      const result = await api.hermes.run(tool, parsed);
      setOutput(JSON.stringify(result, null, 2));
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }

  function schemaHint(parameters: HermesToolDef["parameters"]): string {
    const properties = parameters.properties ?? {};
    const required = parameters.required ?? [];
    const lines = Object.entries(properties).map(([name, spec]) => {
      const typed = spec as { type?: string; enum?: string[]; description?: string };
      const type = typed.type ?? "any";
      const choices = typed.enum ? ` (${typed.enum.join(" | ")})` : "";
      return `${name}: ${type}${choices}${required.includes(name) ? " *" : ""}`;
    });
    if (!lines.length) return "{}";
    return "{\n  " + lines.join(",\n  ") + "\n}";
  }

  return (
    <div className="view">
      <div className="view-head">
        <div>
          <h1>Hermes</h1>
          <p className="muted">
            Deterministic tools, not free-form database access. Hermes decides
            intent; this backend performs the operation. The app works fully
            without an external AI — this console is the tool surface.
          </p>
        </div>
      </div>
      <ErrorNote error={error} />
      <div className="hermes-layout">
        <div className="hermes-console">
          <div className="form-grid">
            <label className="form-field">
              <span>Tool</span>
              <select
                className="select-input"
                value={tool}
                onChange={(event) => {
                  setTool(event.target.value);
                  setArgumentsText("");
                  setOutput("");
                }}
              >
                {tools.map((item) => (
                  <option key={item.name} value={item.name}>
                    {item.name}
                  </option>
                ))}
              </select>
            </label>
          </div>
          {selectedDef && (
            <div className="hermes-tool-doc">
              <strong>{selectedDef.name}</strong>
              <p className="muted small">{selectedDef.description}</p>
              <pre className="schema-hint">{schemaHint(selectedDef.parameters)}</pre>
            </div>
          )}
          <label className="form-field">
            <span>Arguments (JSON)</span>
            <textarea
              className="code-input"
              value={argumentsText}
              onChange={(event) => setArgumentsText(event.target.value)}
              spellCheck={false}
              rows={7}
            />
          </label>
          <div className="form-actions">
            <Button kind="primary" onClick={() => void run()} disabled={loading}>
              {loading ? "Running…" : "Run tool"}
            </Button>
          </div>
          {output && (
            <>
              <div className="rel-section-title">Structured output</div>
              <pre className="code-output">{output}</pre>
            </>
          )}
        </div>
        <div className="hermes-catalog">
          <h3>Tool catalog ({tools.length})</h3>
          <div className="hermes-tool-list">
            {tools.map((item) => (
              <button
                type="button"
                key={item.name}
                className={item.name === tool ? "active" : ""}
                onClick={() => {
                  setTool(item.name);
                  setArgumentsText("");
                  setOutput("");
                }}
              >
                <strong>{item.name}</strong>
                <span className="muted tiny">{item.description}</span>
              </button>
            ))}
          </div>
          <div className="muted tiny hermes-note">
            External AI adapters can call these tools over HTTP later; nothing
            in this app depends on one.
          </div>
        </div>
      </div>
    </div>
  );
}
