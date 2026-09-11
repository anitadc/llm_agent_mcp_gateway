import { useState } from "react";
import { NavLink } from "react-router-dom";

import { useAuth } from "../hooks/useAuth";

const GROUPS = [
  {
    label: null,
    links: [{ to: "/", label: "Dashboard", roles: null }],
  },
  {
    label: "LLM Gateway",
    links: [
      { to: "/usage", label: "Usage & Cost", roles: null },
      { to: "/logs", label: "Request Logs", roles: null },
      { to: "/routing-rules", label: "Routing Rules", roles: ["admin"] },
      { to: "/budgets", label: "Budgets", roles: ["admin", "team_lead"] },
      { to: "/providers", label: "Providers", roles: ["admin"] },
      { to: "/model-pricing", label: "Model Pricing", roles: ["admin"] },
    ],
  },
  {
    label: "MCP Gateway",
    links: [
      { to: "/mcp/servers", label: "MCP Servers", roles: ["admin"] },
      { to: "/mcp/api-services", label: "API Services (REST)", roles: ["admin"] },
      { to: "/mcp/tools", label: "MCP Tools", roles: null },
      { to: "/mcp/playground", label: "MCP Playground", roles: null },
      { to: "/mcp/sessions", label: "MCP Sessions", roles: null },
    ],
  },
  {
    label: "Agent Gateway",
    links: [
      { to: "/agent-catalog", label: "Agent Catalog", roles: null },
      { to: "/agents", label: "Agent Registry", roles: ["admin"] },
      { to: "/agent-approvals", label: "Agent Approvals", roles: ["admin"] },
    ],
  },
  {
    label: "Platform Administration",
    links: [
      { to: "/keys", label: "API Keys", roles: null },
      { to: "/organizations", label: "Organizations", roles: ["admin"] },
      { to: "/projects", label: "Projects", roles: ["admin", "team_lead"] },
      { to: "/users", label: "Users", roles: ["admin"] },
      { to: "/settings/secrets", label: "Secrets", roles: ["admin"] },
      { to: "/settings/identity-providers", label: "Identity Providers", roles: ["admin"] },
    ],
  },
];

export function Sidebar() {
  const { roles } = useAuth();
  const [collapsed, setCollapsed] = useState({});

  const visibleGroups = GROUPS.map((group) => ({
    ...group,
    links: group.links.filter((link) => !link.roles || link.roles.some((r) => roles.includes(r))),
  })).filter((group) => group.links.length > 0);

  function toggleGroup(label) {
    setCollapsed((prev) => ({ ...prev, [label]: !prev[label] }));
  }

  return (
    <nav className="w-56 shrink-0 space-y-4 border-r border-gray-200 bg-white p-4">
      {visibleGroups.map((group, i) => {
        const isCollapsed = group.label ? Boolean(collapsed[group.label]) : false;
        return (
          <div key={group.label ?? `top-${i}`}>
            {group.label && (
              <button
                type="button"
                onClick={() => toggleGroup(group.label)}
                aria-expanded={!isCollapsed}
                className="mb-1 flex w-full items-center justify-between gap-2 rounded px-3 py-1 text-left text-xs font-semibold uppercase tracking-wide text-gray-400 hover:text-gray-600"
              >
                <span className="text-left">{group.label}</span>
                <span
                  className={`shrink-0 text-[10px] transition-transform duration-150 ${isCollapsed ? "-rotate-90" : "rotate-0"}`}
                >
                  ▾
                </span>
              </button>
            )}
            {!isCollapsed && (
              <ul className="space-y-1">
                {group.links.map((link) => (
                  <li key={link.to}>
                    <NavLink
                      to={link.to}
                      end={link.to === "/"}
                      className={({ isActive }) =>
                        `block rounded px-3 py-2 text-sm font-medium ${
                          isActive ? "bg-brand-50 text-brand-700" : "text-gray-600 hover:bg-gray-100"
                        }`
                      }
                    >
                      {link.label}
                    </NavLink>
                  </li>
                ))}
              </ul>
            )}
          </div>
        );
      })}
    </nav>
  );
}
