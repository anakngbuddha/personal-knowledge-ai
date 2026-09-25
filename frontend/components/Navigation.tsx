import React, { useState } from "react";

interface NavItem { id: string; label: string; href: string; active?: boolean; badge?: number; }
interface NavSection { id: string; title: string; icon: string; items: NavItem[]; collapsed?: boolean; }

const Navigation: React.FC<{ sections: NavSection[]; onNavigate: (id: string) => void }> = ({ sections, onNavigate }) => {
  const [secs, setSecs] = useState(sections);
  const toggle = (id: string) => setSecs(secs.map(s => s.id === id ? { ...s, collapsed: !s.collapsed } : s));

  return (
    <nav className="w-64 bg-gray-50 border-r border-gray-200 flex flex-col h-screen p-4">
      <div className="mb-6"><h1 className="text-lg font-bold">Deep Atlas</h1><p className="text-xs text-gray-600">Autonomous Knowledge Engine</p></div>
      <div className="space-y-2 flex-1 overflow-y-auto">
        {secs.map(sec => (
          <div key={sec.id} className="mb-4">
            <button onClick={() => toggle(sec.id)} className="w-full flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-gray-200 transition text-gray-900 font-medium">
              <span>{sec.icon}</span><span className="flex-1 text-left">{sec.title}</span>
              <span className={`transition-transform ${sec.collapsed ? "-rotate-90" : ""}`}>&#9662;</span>
            </button>
            {!sec.collapsed && (
              <div className="ml-4 mt-1 space-y-1">
                {sec.items.map(item => (
                  <a key={item.id} href={item.href} onClick={() => onNavigate(item.id)}
                    className={`block px-3 py-2 rounded-lg text-sm transition ${item.active ? "bg-blue-100 text-blue-900" : "text-gray-700 hover:bg-gray-100"}`}>
                    <span className="flex items-center gap-2">{item.label}
                      {item.badge ? <span className="ml-auto bg-red-500 text-white text-xs px-2 py-0.5 rounded-full">{item.badge}</span> : null}
                    </span>
                  </a>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
      <div className="border-t border-gray-200 pt-4">
        <button className="w-full flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-gray-200 text-gray-700">Settings</button>
      </div>
    </nav>
  );
};

export { Navigation, type NavSection, type NavItem };
