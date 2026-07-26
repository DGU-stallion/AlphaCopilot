import { useNavigate } from "react-router-dom";
import { Bot } from "lucide-react";

interface ContextualAgentEntryProps {
  /** Prompt template with {key} placeholders */
  prompt: string;
  /** Context values to replace placeholders */
  context?: Record<string, string>;
  /** Button label (default: "问 Agent") */
  label?: string;
}

/**
 * Resolve {key} placeholders in a prompt template.
 * - Matched keys are replaced with their values
 * - Unmatched {key} patterns are removed
 */
export function resolvePrompt(prompt: string, context: Record<string, string> = {}): string {
  return prompt.replace(/\{(\w+)\}/g, (_, key) => context[key] ?? "");
}

/**
 * Contextual shortcut button that navigates to the Agent page with a
 * pre-filled prompt derived from the current page context.
 */
export function ContextualAgentEntry({ prompt, context, label = "问 Agent" }: ContextualAgentEntryProps) {
  const navigate = useNavigate();

  function handleClick() {
    const resolved = resolvePrompt(prompt, context).trim();
    navigate(`/agent?prefill=${encodeURIComponent(resolved)}`);
  }

  return (
    <button
      onClick={handleClick}
      className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground transition-opacity hover:opacity-90"
      title={label}
    >
      <Bot size={14} />
      <span>{label}</span>
    </button>
  );
}
