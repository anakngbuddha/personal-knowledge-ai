import React, { useState } from "react";

interface BriefCardProps {
  briefId: string; industry?: string; scale?: string; platforms: string[];
  cloud?: string; budget?: string; constraints: string[]; mustHaves: string[];
  niceToHaves: string[]; exclusions: string[]; extractedAt: string;
  editable?: boolean; onUpdate?: (field: string, value: any) => void;
}

const BriefCard: React.FC<BriefCardProps> = (props) => {
  const [editing, setEditing] = useState(false);
  const [vals, setVals] = useState({ industry: props.industry, scale: props.scale, cloud: props.cloud, budget: props.budget });
  const [lists, setLists] = useState({ platforms: [...props.platforms], constraints: [...props.constraints], mustHaves: [...props.mustHaves], niceToHaves: [...props.niceToHaves], exclusions: [...props.exclusions] });

  const save = () => { if (props.onUpdate) { Object.entries(vals).forEach(([k, v]) => props.onUpdate!(k, v)); Object.entries(lists).forEach(([k, v]) => props.onUpdate!(k, v)); } setEditing(false); };
  const addItem = (key: string, val: string) => { if (val.trim()) setLists({ ...lists, [key]: [...(lists as any)[key], val] }); };
  const rmItem = (key: string, i: number) => setLists({ ...lists, [key]: (lists as any)[key].filter((_: any, idx: number) => idx !== i) });

  return (
    <div className="bg-gradient-to-br from-blue-50 to-indigo-50 border border-blue-200 rounded-lg p-4 max-w-2xl shadow-sm">
      <div className="flex items-start justify-between mb-4">
        <div>
          <h3 className="font-semibold text-gray-900">Customer Brief</h3>
          <p className="text-xs text-gray-600 mt-1">ID: <code className="bg-gray-200 px-1 rounded">{props.briefId}</code></p>
        </div>
        {props.editable !== false && (
          editing
            ? <div className="flex gap-1"><button onClick={save} className="p-2 hover:bg-green-100 rounded text-green-700">Save</button><button onClick={() => setEditing(false)} className="p-2 hover:bg-red-100 rounded text-red-700">Cancel</button></div>
            : <button onClick={() => setEditing(true)} className="p-2 hover:bg-blue-100 rounded text-blue-700">Edit</button>
        )}
      </div>
      <div className="grid grid-cols-2 gap-3 mb-4">
        {(["industry","scale","cloud","budget"] as const).map(f => (
          <div key={f}>
            <label className="text-xs font-medium text-gray-700 block mb-1">{f.charAt(0).toUpperCase()+f.slice(1)}</label>
            {editing ? <input type="text" value={(vals as any)[f] || ""} onChange={e => setVals({...vals, [f]: e.target.value})} className="w-full px-2 py-1 border border-gray-300 rounded text-sm" />
                     : <p className={`text-sm ${f === "budget" ? "font-semibold text-indigo-700" : "text-gray-900"}`}>{(vals as any)[f] || "\u2014"}</p>}
          </div>
        ))}
      </div>
      <div className="mb-3">
        <label className="text-xs font-medium text-gray-700 block mb-1">Platforms</label>
        <div className="flex flex-wrap gap-2">
          {lists.platforms.map((p, i) => <span key={i} className="bg-blue-100 text-blue-900 px-2 py-1 rounded text-xs font-medium">{p}{editing && <button onClick={() => rmItem("platforms", i)} className="ml-1">&times;</button>}</span>)}
          {editing && <input placeholder="+ platform" onKeyDown={e => { if (e.key === "Enter") { addItem("platforms", e.currentTarget.value); e.currentTarget.value = ""; }}} className="px-2 py-1 border border-dashed border-blue-300 rounded text-xs" />}
        </div>
      </div>
      {([["constraints","Constraints"],["mustHaves","Must-Haves"],["niceToHaves","Nice-to-Haves"],["exclusions","Exclusions"]] as const).map(([key, title]) => (
        <div key={key} className="mb-3">
          <label className="text-xs font-medium text-gray-700 block mb-1">{title}</label>
          <ul className="text-sm space-y-1">
            {(lists as any)[key].map((item: string, i: number) => <li key={i} className="flex items-center gap-2 bg-white px-2 py-1 rounded"><span className="flex-1">{item}</span>{editing && <button onClick={() => rmItem(key, i)} className="text-red-500">&times;</button>}</li>)}
          </ul>
          {editing && <input placeholder={`+ ${title.toLowerCase()}`} onKeyDown={e => { if (e.key === "Enter") { addItem(key, e.currentTarget.value); e.currentTarget.value = ""; }}} className="w-full px-2 py-1 border border-dashed border-gray-300 rounded text-sm mt-1" />}
        </div>
      ))}
      <div className="text-xs text-gray-600 pt-2 border-t border-blue-100">Brief used by advisor to recommend solutions. Click Edit to refine.</div>
    </div>
  );
};
export default BriefCard;
