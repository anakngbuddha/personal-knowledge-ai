import React, { useState } from "react";

interface ChatMessage { id: string; role: "user" | "assistant"; content: string; briefCard?: any; products?: string[]; timestamp: string; }
interface ThreePaneAskProps { sourceContext: string[]; chatHistory: ChatMessage[]; mapData: any; onSendMessage: (msg: string) => void; onSelectSource: (src: string) => void; }

const ThreePaneAsk: React.FC<ThreePaneAskProps> = ({ sourceContext, chatHistory, mapData, onSendMessage, onSelectSource }) => {
  const [msg, setMsg] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const send = () => { if (msg.trim()) { onSendMessage(msg); setMsg(""); } };
  const toggleSrc = (src: string) => { const s = new Set(selected); s.has(src) ? s.delete(src) : s.add(src); setSelected(s); onSelectSource(src); };

  return (
    <div className="flex h-full bg-white">
      {/* Left: Sources */}
      <div className="w-64 border-r border-gray-200 p-4 overflow-y-auto">
        <h3 className="font-semibold mb-3 text-gray-900">Sources</h3>
        {sourceContext.map(src => (
          <label key={src} className="flex items-center gap-2 p-2 rounded hover:bg-gray-100 cursor-pointer">
            <input type="checkbox" checked={selected.has(src)} onChange={() => toggleSrc(src)} className="rounded" />
            <span className="text-sm text-gray-700">{src}</span>
          </label>
        ))}
        <div className="mt-6 pt-4 border-t border-gray-200">
          <div className="bg-blue-50 p-3 rounded border border-blue-200"><p className="text-xs text-blue-900">{selected.size} source(s) selected</p></div>
        </div>
      </div>

      {/* Center: Chat */}
      <div className="flex-1 flex flex-col">
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {chatHistory.map(m => (
            <div key={m.id} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
              <div className={`max-w-lg px-4 py-2 rounded-lg ${m.role === "user" ? "bg-blue-500 text-white" : "bg-gray-100 text-gray-900"}`}>
                {m.briefCard && <div className="mb-2 p-2 bg-white text-gray-900 rounded border border-gray-300 text-sm"><strong>{m.briefCard.title}</strong></div>}
                <p className="text-sm">{m.content}</p>
                {m.products && m.products.length > 0 && <div className="mt-2 text-xs opacity-75"><strong>Products:</strong> {m.products.join(", ")}</div>}
                <p className="text-xs opacity-60 mt-1">{m.timestamp}</p>
              </div>
            </div>
          ))}
        </div>
        <div className="border-t border-gray-200 p-4">
          <div className="flex gap-2">
            <input value={msg} onChange={e => setMsg(e.target.value)} onKeyDown={e => e.key === "Enter" && send()}
              placeholder="Ask about solutions..." className="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500" />
            <button onClick={send} className="px-6 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition">Send</button>
          </div>
        </div>
      </div>

      {/* Right: Product Map */}
      <div className="w-80 border-l border-gray-200 p-4 overflow-y-auto">
        <h3 className="font-semibold mb-3 text-gray-900">Product Map</h3>
        {mapData?.nodes?.length > 0
          ? mapData.nodes.map((n: any, i: number) => (
              <div key={i} className="p-2 bg-gray-50 rounded border border-gray-200 text-sm mb-2">
                <p className="font-medium text-gray-900">{n.name}</p>
                <p className="text-xs text-gray-600 mt-1">{n.category}</p>
                {n.relations?.length > 0 && <p className="text-xs text-blue-600 mt-1">{n.relations.length} relation(s)</p>}
              </div>))
          : <p className="text-sm text-gray-500">No products matched</p>}
        <div className="mt-6 pt-4 border-t border-gray-200">
          <h4 className="text-xs font-semibold text-gray-700 mb-2">Graph Stats</h4>
          <p className="text-xs text-gray-600">Nodes: {mapData?.nodes?.length || 0}</p>
        </div>
      </div>
    </div>
  );
};

export { ThreePaneAsk };
