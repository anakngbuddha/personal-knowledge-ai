import React from "react";
import type { MentionCategory, MentionTarget, ProductConnections } from "../types";

export interface SlashCommandItem {
  cmd: string;
  label: string;
  desc: string;
  example: string;
  icon: string;
}

export const SLASH_COMMANDS: SlashCommandItem[] = [
  {
    cmd: "/goal",
    label: "/goal <objective>",
    desc: "Set or update the active conversational session goal",
    example: "/goal Evaluate cloud migration readiness",
    icon: "🎯",
  },
  {
    cmd: "/connections",
    label: "/connections <product>",
    desc: "Inspect catalog product dependencies, prerequisites & conflicts",
    example: "/connections Atlas-Core",
    icon: "🕸️",
  },
  {
    cmd: "/plan",
    label: "/plan <task>",
    desc: "Formulate a grounded step-by-step implementation & execution plan",
    example: "/plan Deploy Kubernetes high-availability cluster",
    icon: "📋",
  },
  {
    cmd: "/graphify-sync",
    label: "/graphify-sync",
    desc: "Audit knowledge graph health & catalog integrity status",
    example: "/graphify-sync",
    icon: "🔄",
  },
  {
    cmd: "/briefing",
    label: "/briefing [topic]",
    desc: "Generate an executive briefing from workspace collateral",
    example: "/briefing Cloud Platform highlights",
    icon: "📑",
  },
  {
    cmd: "/faq",
    label: "/faq [topic]",
    desc: "Generate a comprehensive FAQ grounded in sources",
    example: "/faq Authentication and SSO",
    icon: "❓",
  },
  {
    cmd: "/compare",
    label: "/compare <items>",
    desc: "Perform comparative analysis between products or sources",
    example: "/compare Atlas-Core and Cloud-V2",
    icon: "⚖️",
  },
  {
    cmd: "/help",
    label: "/help",
    desc: "Display cheatsheet of all mentions (@) and commands (/)",
    example: "/help",
    icon: "💡",
  },
];

interface ActiveGoalBannerProps {
  goal: string;
  onEdit: () => void;
  onClear: () => void;
  onComplete?: () => void;
  disabled?: boolean;
}

export function ActiveGoalBanner({ goal, onEdit, onClear, onComplete, disabled }: ActiveGoalBannerProps) {
  return (
    <div className="active-goal-banner">
      <div className="goal-banner-left">
        <span className="goal-banner-icon">🎯</span>
        <div className="goal-banner-text-group">
          <span className="goal-banner-badge">ACTIVE SESSION GOAL</span>
          <p className="goal-banner-title">{goal}</p>
        </div>
      </div>
      <div className="goal-banner-actions">
        <button type="button" disabled={disabled} className="goal-btn edit" onClick={onEdit} title="Edit goal">
          Edit
        </button>
        {onComplete && <button type="button" disabled={disabled} className="goal-btn" onClick={onComplete}>Achieved</button>}
        <button type="button" disabled={disabled} className="goal-btn clear" onClick={onClear} title="Clear active goal">
          Clear
        </button>
      </div>
    </div>
  );
}

interface ProductConnectionsCardProps {
  connections: ProductConnections;
  onNavigateMap: () => void;
}

export function ProductConnectionsCard({ connections, onNavigateMap }: ProductConnectionsCardProps) {
  return (
    <div className="product-connections-card">
      <div className="pcc-header">
        <div className="pcc-title-area">
          <span className="pcc-icon">🕸️</span>
          <div>
            <h4 className="pcc-title">{connections.product_name}</h4>
            <div className="pcc-badges">
              {connections.vendor && <span className="pcc-badge vendor">{connections.vendor}</span>}
              {connections.category && <span className="pcc-badge category">{connections.category}</span>}
              <span className="pcc-badge docs">{connections.collateral_count} collateral docs</span>
            </div>
          </div>
        </div>
        <button type="button" className="pcc-map-btn" onClick={onNavigateMap}>
          Explore in Map &rarr;
        </button>
      </div>

      <div className="pcc-grid">
        {/* Prerequisites */}
        <div className="pcc-column prereqs">
          <div className="pcc-col-header">
            <span className="pcc-indicator req" />
            <h5>Prerequisites ({connections.prerequisites.length})</h5>
          </div>
          {connections.prerequisites.length === 0 ? (
            <p className="pcc-empty">No mapped prerequisites</p>
          ) : (
            <ul className="pcc-list">
              {connections.prerequisites.map((p) => (
                <li key={p.id} className="pcc-item">
                  <span className="pcc-item-name">{p.name}</span>
                  {p.evidence && <span className="pcc-item-detail">{p.evidence}</span>}
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Conflicts */}
        <div className="pcc-column conflicts">
          <div className="pcc-col-header">
            <span className="pcc-indicator conf" />
            <h5>Conflicts ({connections.conflicts.length})</h5>
          </div>
          {connections.conflicts.length === 0 ? (
            <p className="pcc-empty">No known conflicts</p>
          ) : (
            <ul className="pcc-list">
              {connections.conflicts.map((c) => (
                <li key={c.id} className="pcc-item conflict">
                  <span className="pcc-item-name">{c.name}</span>
                  {c.evidence && <span className="pcc-item-detail">{c.evidence}</span>}
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Integrations */}
        <div className="pcc-column integrations">
          <div className="pcc-col-header">
            <span className="pcc-indicator itg" />
            <h5>Direct Integrations ({connections.integrations.length})</h5>
          </div>
          {connections.integrations.length === 0 ? (
            <p className="pcc-empty">No mapped integrations</p>
          ) : (
            <ul className="pcc-list">
              {connections.integrations.map((i) => (
                <li key={i.id} className="pcc-item">
                  <span className="pcc-item-name">{i.name}</span>
                  {i.evidence && <span className="pcc-item-detail">{i.evidence}</span>}
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Alternatives */}
        <div className="pcc-column alternatives">
          <div className="pcc-col-header">
            <span className="pcc-indicator alt" />
            <h5>Alternatives ({connections.alternatives.length})</h5>
          </div>
          {connections.alternatives.length === 0 ? (
            <p className="pcc-empty">None mapped</p>
          ) : (
            <ul className="pcc-list">
              {connections.alternatives.map((a) => (
                <li key={a.id} className="pcc-item">
                  <span className="pcc-item-name">{a.name}</span>
                  {a.evidence && <span className="pcc-item-detail">{a.evidence}</span>}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}

interface MentionPaletteProps {
  targets: MentionTarget[];
  selectedIndex: number;
  category: "all" | MentionCategory;
  onSelectCategory: (cat: "all" | MentionCategory) => void;
  onSelectTarget: (target: MentionTarget) => void;
  loading: boolean;
}

export function MentionPalette({
  targets,
  selectedIndex,
  category,
  onSelectCategory,
  onSelectTarget,
  loading,
}: MentionPaletteProps) {
  const listRef = React.useRef<HTMLDivElement>(null);
  React.useEffect(() => {
    listRef.current?.querySelector<HTMLElement>('[aria-selected="true"]')?.scrollIntoView?.({block: "nearest"});
  }, [selectedIndex, targets]);
  const categories: Array<{ id: "all" | MentionCategory; label: string; icon: string }> = [
    { id: "all", label: "All", icon: "✨" },
    { id: "note", label: "Notes", icon: "📝" },
    { id: "product", label: "Products", icon: "📦" },
    { id: "connector", label: "Connectors", icon: "🔌" },
    { id: "website", label: "Websites", icon: "🌐" },
  ];

  return (
    <div className="mention-autocomplete-menu">
      <div className="mam-header">
        <span className="mam-title">Mention & Context</span>
        <div className="mam-tabs">
          {categories.map((c) => (
            <button
              key={c.id}
              type="button"
              className={`mam-tab ${category === c.id ? "active" : ""}`}
              onClick={() => onSelectCategory(c.id)}
            >
              <span>{c.icon}</span> {c.label}
            </button>
          ))}
        </div>
      </div>

      <div className="mam-list" ref={listRef} id="ask-mentions-list" role="listbox" aria-label="Mention targets">
        {loading ? (
          <div className="mam-empty">Searching workspace targets…</div>
        ) : targets.length === 0 ? (
          <div className="mam-empty">No matching notes, products, connectors, or websites.</div>
        ) : (
          targets.map((t, idx) => {
            const isSelected = idx === selectedIndex;
            const categoryIcon =
              t.category === "note" ? "📝" : t.category === "product" ? "📦" : t.category === "connector" ? "🔌" : "🌐";
            return (
              <button
                key={t.id}
                id={`ask-mention-${idx}`}
                type="button"
                className={`mam-item ${isSelected ? "selected" : ""}`}
                onClick={() => onSelectTarget(t)}
                role="option"
                aria-selected={isSelected}
              >
                <span className="mam-item-icon">{categoryIcon}</span>
                <div className="mam-item-info">
                  <div className="mam-item-name-row">
                    <span className="mam-item-name">{t.name}</span>
                    <span className={`mam-item-cat-badge ${t.category}`}>{t.category}</span>
                  </div>
                  {t.subtitle && <span className="mam-item-sub">{t.subtitle}</span>}
                </div>
              </button>
            );
          })
        )}
      </div>
      <div className="mam-footer">
        <span>Use &uarr;&darr; to navigate, Enter to select, Esc to close</span>
      </div>
    </div>
  );
}

interface SlashPaletteProps {
  commands: SlashCommandItem[];
  selectedIndex: number;
  onSelectCommand: (cmd: SlashCommandItem) => void;
}

export function SlashPalette({ commands, selectedIndex, onSelectCommand }: SlashPaletteProps) {
  const listRef = React.useRef<HTMLDivElement>(null);
  React.useEffect(() => {
    listRef.current?.querySelector<HTMLElement>('[aria-selected="true"]')?.scrollIntoView?.({block: "nearest"});
  }, [selectedIndex, commands]);
  return (
    <div className="slash-autocomplete-menu">
      <div className="sam-header">
        <span className="sam-title">Intelligent Functions & Slash Commands</span>
      </div>
      <div className="sam-list" ref={listRef} id="ask-commands-list" role="listbox" aria-label="Commands">
        {commands.map((c, idx) => {
          const isSelected = idx === selectedIndex;
          return (
            <button
              key={c.cmd}
              id={`ask-command-${idx}`}
              type="button"
              className={`sam-item ${isSelected ? "selected" : ""}`}
              onClick={() => onSelectCommand(c)}
              role="option"
              aria-selected={isSelected}
            >
              <span className="sam-item-icon">{c.icon}</span>
              <div className="sam-item-info">
                <div className="sam-item-label-row">
                  <span className="sam-item-cmd">{c.cmd}</span>
                  <span className="sam-item-label">{c.label}</span>
                </div>
                <span className="sam-item-desc">{c.desc}</span>
              </div>
            </button>
          );
        })}
      </div>
      <div className="sam-footer">
        <span>Type command or press Enter to choose</span>
      </div>
    </div>
  );
}

interface QuickActionBarProps {
  onTriggerMention: (category: "all" | MentionCategory) => void;
  onTriggerSlash: (cmd: string) => void;
}

export function QuickActionBar({ onTriggerMention, onTriggerSlash }: QuickActionBarProps) {
  return (
    <div className="composer-quick-bar">
      <div className="cqb-group">
        <span className="cqb-label">Mention:</span>
        <button type="button" className="cqb-pill" onClick={() => onTriggerMention("all")}>@ Mention</button>
        <button type="button" className="cqb-pill" onClick={() => onTriggerMention("note")} title="Mention notes">
          📝 Notes
        </button>
        <button type="button" className="cqb-pill" onClick={() => onTriggerMention("product")} title="Mention catalog products">
          📦 Products
        </button>
        <button type="button" className="cqb-pill" onClick={() => onTriggerMention("connector")} title="Mention MCP connectors">
          🔌 Connectors
        </button>
        <button type="button" className="cqb-pill" onClick={() => onTriggerMention("website")} title="Mention websites & URLs">
          🌐 Web
        </button>
      </div>

      <div className="cqb-group commands">
        <span className="cqb-label">Commands:</span>
        <button type="button" className="cqb-pill cmd" onClick={() => onTriggerSlash("/")}>/ Commands</button>
        <button type="button" className="cqb-pill cmd" onClick={() => onTriggerSlash("/goal ")} title="Set or call goal">
          🎯 /goal
        </button>
        <button type="button" className="cqb-pill cmd" onClick={() => onTriggerSlash("/connections ")} title="See product connections">
          🕸️ /connections
        </button>
        <button type="button" className="cqb-pill cmd" onClick={() => onTriggerSlash("/plan ")} title="Build implementation plan">
          📋 /plan
        </button>
        <button type="button" className="cqb-pill cmd" onClick={() => onTriggerSlash("/graphify-sync")} title="Check graph sync">
          🔄 /graphify-sync
        </button>
        <button type="button" className="cqb-pill cmd" onClick={() => onTriggerSlash("/help")} title="Show cheatsheet">
          💡 /help
        </button>
      </div>
    </div>
  );
}

interface ActiveMentionsBarProps {
  mentions: MentionTarget[];
  onRemoveMention: (id: string) => void;
}

export function ActiveMentionsBar({ mentions, onRemoveMention }: ActiveMentionsBarProps) {
  if (mentions.length === 0) return null;
  return (
    <div className="active-mentions-bar">
      <span className="amb-label">Context Focus:</span>
      <div className="amb-chips">
        {mentions.map((m) => {
          const icon = m.category === "note" ? "📝" : m.category === "product" ? "📦" : m.category === "connector" ? "🔌" : "🌐";
          return (
            <span key={m.id} className={`mention-chip ${m.category}`}>
              <span className="chip-icon">{icon}</span>
              <span className="chip-name">{m.name}</span>
              <button
                type="button"
                className="chip-remove-btn"
                onClick={() => onRemoveMention(m.id)}
                aria-label={`Remove mention ${m.name}`}
              >
                &times;
              </button>
            </span>
          );
        })}
      </div>
    </div>
  );
}
