"""Phase 4.1: Customer Brief - LLM-extracted structured requirements."""
import json, re
from dataclasses import dataclass, asdict
from typing import Optional, List, Dict, Any
from anthropic import Anthropic

@dataclass
class CustomerBrief:
    id: str
    industry: Optional[str] = None
    rooms_users: Optional[str] = None
    platforms: List[str] = None
    cloud_requirement: Optional[str] = None
    budget: Optional[str] = None
    constraints: List[str] = None
    must_haves: List[str] = None
    nice_to_haves: List[str] = None
    exclusions: List[str] = None
    raw_text: str = ""
    extracted_at: str = ""
    def __post_init__(self):
        for f in ("platforms","constraints","must_haves","nice_to_haves","exclusions"):
            if getattr(self, f) is None: setattr(self, f, [])
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

def extract_brief_with_llm(text: str, api_key: Optional[str] = None) -> CustomerBrief:
    from datetime import datetime; import uuid
    client = Anthropic(api_key=api_key)
    brief_id = str(uuid.uuid4())[:8]
    sys_prompt = ("You are a requirements analyst. Extract structured customer brief as JSON.\n"
           "Fields: industry, rooms_users, platforms[], cloud_requirement, budget, "
           "constraints[], must_haves[], nice_to_haves[], exclusions[].\n"
           "Output ONLY valid JSON. null for missing fields.")
    resp = client.messages.create(model="claude-3-5-sonnet-20241022", max_tokens=1024,
        system=sys_prompt, messages=[{"role":"user","content":f"Extract brief:\n{text}"}])
    try: data = json.loads(resp.content[0].text.strip())
    except json.JSONDecodeError: data = _regex_fallback(text)
    return CustomerBrief(id=brief_id, industry=data.get("industry"),
        rooms_users=data.get("rooms_users"), platforms=data.get("platforms") or [],
        cloud_requirement=data.get("cloud_requirement"), budget=data.get("budget"),
        constraints=data.get("constraints") or [], must_haves=data.get("must_haves") or [],
        nice_to_haves=data.get("nice_to_haves") or [], exclusions=data.get("exclusions") or [],
        raw_text=text, extracted_at=datetime.now().isoformat())

def _regex_fallback(text: str) -> Dict[str, Any]:
    data = {"industry":None,"rooms_users":None,"platforms":[],"cloud_requirement":None,
            "budget":None,"constraints":[],"must_haves":[],"nice_to_haves":[],"exclusions":[]}
    m = re.search(r"\$[\d,]+k?(?:\s*-\s*\$[\d,]+k?)?|\b\d+(?:k|m)\b\s+(?:budget|cost)", text, re.I)
    if m: data["budget"] = m.group(0)
    m = re.search(r"(\d+)\s+(user|seat|staff|employee|room|conference|meeting)", text, re.I)
    if m: data["rooms_users"] = m.group(0)
    return data

def brief_to_note_content(b: CustomerBrief) -> str:
    L = ["# Customer Brief","",f"**ID:** `{b.id}`",""]
    if b.industry: L.append(f"**Industry:** {b.industry}")
    if b.rooms_users: L.append(f"**Scale:** {b.rooms_users}")
    if b.cloud_requirement: L.append(f"**Cloud:** {b.cloud_requirement}")
    if b.budget: L.append(f"**Budget:** {b.budget}")
    if b.platforms: L.append(f"**Platforms:** {', '.join(b.platforms)}")
    for label, items in [("Constraints",b.constraints),("Must-Haves",b.must_haves),
                         ("Nice-to-Haves",b.nice_to_haves),("Exclusions",b.exclusions)]:
        if items:
            L.append(f"\n**{label}:**")
            L.extend(f"- {i}" for i in items)
    L.append(f"\n**Raw Input:**\n```\n{b.raw_text}\n```")
    return "\n".join(L)

def brief_to_chat_card(b: CustomerBrief) -> Dict[str, Any]:
    return {"type":"brief_card","id":b.id,
        "title":f"Customer Brief ({b.industry or 'Unknown'} / ${b.budget or '?'})",
        "fields":{"industry":b.industry,"scale":b.rooms_users,"platforms":b.platforms,
            "cloud":b.cloud_requirement,"budget":b.budget,"constraints":b.constraints,
            "must_haves":b.must_haves,"nice_to_haves":b.nice_to_haves,"exclusions":b.exclusions},
        "editable":True,"extracted_at":b.extracted_at}
