"use client";

import { useEffect, useState } from "react";

export interface ModelConfig {
  provider: string;
  model: string;
  apiKey: string;
}

interface ProviderOption {
  id: string;
  label: string;
  default_model: string;
  requires_key: boolean;
  key_hint: string;
  signup_url: string;
}

const STORAGE_KEY = "di.modelConfig";

/**
 * The key is kept in localStorage on the user's own machine and attached to the
 * brief request as a header. It is never sent anywhere else and the server does
 * not store it. Anyone with access to this browser profile can read it, which is
 * the same trust boundary as a password manager entry — acceptable for a
 * bring-your-own-key demo, not for a shared or kiosk machine.
 */
export function loadModelConfig(): ModelConfig | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<ModelConfig>;
    if (!parsed.provider) return null;
    return {
      provider: parsed.provider,
      model: parsed.model ?? "",
      apiKey: parsed.apiKey ?? "",
    };
  } catch {
    return null;
  }
}

/** Headers carrying the caller's own credentials, or none if they haven't set any. */
export function modelHeaders(config: ModelConfig | null): Record<string, string> {
  if (!config?.provider) return {};
  const headers: Record<string, string> = { "X-LLM-Provider": config.provider };
  if (config.model.trim()) headers["X-LLM-Model"] = config.model.trim();
  if (config.apiKey.trim()) headers["X-LLM-Api-Key"] = config.apiKey.trim();
  return headers;
}

export default function ModelSettings({
  config,
  onChange,
  serverModelConfigured,
}: {
  config: ModelConfig | null;
  onChange: (config: ModelConfig | null) => void;
  serverModelConfigured: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [providers, setProviders] = useState<ProviderOption[]>([]);
  const [draft, setDraft] = useState<ModelConfig>(
    config ?? { provider: "groq", model: "", apiKey: "" },
  );
  const [showKey, setShowKey] = useState(false);

  useEffect(() => {
    if (!open || providers.length) return;
    fetch("/api/providers")
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => d && setProviders(d.providers ?? []))
      .catch(() => setProviders([]));
  }, [open, providers.length]);

  const selected = providers.find((p) => p.id === draft.provider);
  const usingOwnKey = Boolean(config?.provider);

  function save() {
    const next = { ...draft, model: draft.model.trim(), apiKey: draft.apiKey.trim() };
    if (!next.provider) return;
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    onChange(next);
    setOpen(false);
  }

  function clear() {
    window.localStorage.removeItem(STORAGE_KEY);
    onChange(null);
    setDraft({ provider: "groq", model: "", apiKey: "" });
    setOpen(false);
  }

  return (
    <div className="mb-6">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="text-xs text-gray-500">
          {usingOwnKey ? (
            <span>
              Using your own model:{" "}
              <span className="font-medium text-gray-700">
                {config?.provider}
                {config?.model ? ` · ${config.model}` : ""}
              </span>
            </span>
          ) : serverModelConfigured ? (
            <span>Using this server&apos;s model. Add your own key to use your own quota.</span>
          ) : (
            <span className="text-amber-700">
              This server has no model configured — add your own API key to generate a brief.
            </span>
          )}
        </div>
        <button
          onClick={() => setOpen((o) => !o)}
          className="text-xs px-3 py-1.5 border border-gray-200 rounded hover:bg-gray-50 text-gray-600"
        >
          {open ? "Close" : usingOwnKey ? "Change model" : "Use your own model"}
        </button>
      </div>

      {open && (
        <div className="mt-3 p-4 border border-gray-200 rounded-lg bg-gray-50 space-y-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="block">
              <span className="block text-xs font-medium text-gray-700 mb-1">Provider</span>
              <select
                value={draft.provider}
                onChange={(e) => setDraft({ ...draft, provider: e.target.value, model: "" })}
                className="w-full text-sm border border-gray-300 rounded px-2 py-1.5 bg-white"
              >
                {(providers.length
                  ? providers
                  : [{ id: draft.provider, label: draft.provider } as ProviderOption]
                ).map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.label}
                  </option>
                ))}
              </select>
            </label>

            <label className="block">
              <span className="block text-xs font-medium text-gray-700 mb-1">
                Model <span className="text-gray-400 font-normal">(optional)</span>
              </span>
              <input
                type="text"
                value={draft.model}
                onChange={(e) => setDraft({ ...draft, model: e.target.value })}
                placeholder={selected?.default_model ?? "provider default"}
                className="w-full text-sm border border-gray-300 rounded px-2 py-1.5 bg-white"
              />
            </label>
          </div>

          {selected?.requires_key !== false && (
            <label className="block">
              <span className="block text-xs font-medium text-gray-700 mb-1">API key</span>
              <div className="flex gap-2">
                <input
                  type={showKey ? "text" : "password"}
                  value={draft.apiKey}
                  onChange={(e) => setDraft({ ...draft, apiKey: e.target.value })}
                  placeholder={selected?.key_hint ?? "your API key"}
                  autoComplete="off"
                  spellCheck={false}
                  className="flex-1 text-sm border border-gray-300 rounded px-2 py-1.5 bg-white font-mono"
                />
                <button
                  type="button"
                  onClick={() => setShowKey((s) => !s)}
                  className="text-xs px-2 border border-gray-300 rounded bg-white text-gray-600 hover:bg-gray-50"
                >
                  {showKey ? "Hide" : "Show"}
                </button>
              </div>
              {selected?.signup_url && (
                <a
                  href={selected.signup_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-block mt-1 text-xs text-blue-600 hover:underline"
                >
                  Get your {selected.label} key →
                </a>
              )}
            </label>
          )}

          <p className="text-xs text-gray-500 leading-relaxed">
            Your key is stored in this browser only and sent with your brief request so the
            model call runs on your account. It is not saved on the server and is not written
            to the generated brief. Clear it any time with Remove.
          </p>

          <div className="flex gap-2">
            <button
              onClick={save}
              className="text-xs px-3 py-1.5 bg-blue-600 text-white rounded hover:bg-blue-700"
            >
              Save
            </button>
            {usingOwnKey && (
              <button
                onClick={clear}
                className="text-xs px-3 py-1.5 border border-gray-300 rounded text-gray-600 hover:bg-white"
              >
                Remove
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
