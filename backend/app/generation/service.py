"""Generation service - Phase 4.1+5: Brief-aware answer generation."""
from typing import Optional, List, Dict, Any
from app.advisor.brief import CustomerBrief


def brief_to_chat_card(brief: Optional[CustomerBrief]) -> Dict[str, Any]:
    """Convert a brief to a chat card summary."""
    if not brief:
        return None
    return {
        "customer": brief.customer,
        "industry": brief.industry,
        "platforms": brief.platforms,
        "budget": brief.budget,
        "timeline": brief.timeline,
    }


class GenerationService:
    def __init__(self, anthropic_client, embedding_client):
        self.client = anthropic_client
        self.embedding = embedding_client

    async def generate_with_brief(self, question: str, sources: List[str],
            brief: Optional[CustomerBrief] = None,
            selected_source_ids: Optional[List[str]] = None,
            conversation_history: Optional[List[Dict]] = None) -> Dict[str, Any]:
        brief_ctx = self._brief_to_prompt(brief) if brief else ""
        graph = GraphContext()
        matched = await graph.match_products_in_text(question, brief)
        pmap = await graph.expand_product_map(matched, hops=2, max_neighbors=6)
        passages = await self._fetch_passages(matched, sources, selected_source_ids)
        sys_prompt = self._sys_prompt(brief, pmap)
        user_msg = self._user_msg(question, brief_ctx, passages, pmap, conversation_history)
        resp = self.client.messages.create(model="claude-3-5-sonnet-20241022",
            max_tokens=2048, system=sys_prompt, messages=[{"role":"user","content":user_msg}])
        answer = resp.content[0].text
        prods = await graph.extract_products_from_text(answer)
        return {"answer": answer, "products": prods, "brief_used": brief is not None,
            "sources_cited": selected_source_ids or sources[:3],
            "products_map": {"nodes": [{"name":p.name,"category":p.category,"relations":p.relations} for p in pmap.nodes], "edges": pmap.edges},
            "brief_card": brief_to_chat_card(brief) if brief else None}

    async def generate_with_advisor_context(self, brief: CustomerBrief,
            sources: List[str], playbook_type: str = "advisor") -> Dict[str, Any]:
        prompt = f"""You are a solutions architect. Based on this customer brief, recommend a solution bundle.
Customer Brief:
- Industry: {brief.industry or 'Unknown'}
- Scale: {brief.rooms_users or 'Unknown'}
- Platforms: {', '.join(brief.platforms) if brief.platforms else 'Any'}
- Cloud: {brief.cloud_requirement or 'Any'}
- Budget: {brief.budget or 'Unknown'}
- Must-Haves: {', '.join(brief.must_haves) if brief.must_haves else 'None'}
- Constraints: {', '.join(brief.constraints) if brief.constraints else 'None'}
Recommend: 1) Best-fit bundle 2) Why each fits 3) Integration notes 4) Implementation estimate 5) Risks"""
        resp = self.client.messages.create(model="claude-3-5-sonnet-20241022",
            max_tokens=2048, messages=[{"role":"user","content":prompt}])
        text = resp.content[0].text
        return {"playbook": text, "bundles": [], "compatibility_notes": "", "export_formats": ["docx","pptx"], "brief_id": brief.id}

    def _brief_to_prompt(self, b: CustomerBrief) -> str:
        lines = ["## Customer Brief", f"- Industry: {b.industry or 'N/A'}", f"- Scale: {b.rooms_users or 'N/A'}"]
        if b.platforms: lines.append(f"- Platforms: {', '.join(b.platforms)}")
        if b.cloud_requirement: lines.append(f"- Cloud: {b.cloud_requirement}")
        if b.budget: lines.append(f"- Budget: {b.budget}")
        if b.must_haves: lines.extend(["- Must-Haves:"] + [f"  - {m}" for m in b.must_haves])
        if b.constraints: lines.extend(["- Constraints:"] + [f"  - {c}" for c in b.constraints])
        return "\n".join(lines)

    def _sys_prompt(self, brief: Optional[CustomerBrief], pmap: Any) -> str:
        base = "You are a knowledgeable solution architect. Cite products, explain relationships, address constraints, suggest integrations, mention budget implications."
        if brief:
            base += f"\nCustomer requirements:\n{self._brief_to_prompt(brief)}"
        return base

    def _user_msg(self, q, brief_ctx, passages, pmap, history) -> str:
        msg = q
        if brief_ctx: msg += f"\n\n{brief_ctx}"
        if passages: msg += "\n\n## Sources:\n" + "\n".join(f"- {p['source']}: {p['text'][:200]}" for p in passages[:5])
        if pmap and pmap.nodes: msg += "\n\n## Products:\n" + "\n".join(f"- {n.name} ({n.category})" for n in pmap.nodes[:5])
        return msg

    async def _fetch_passages(self, products, sources, selected):
        return [{"source": (selected or sources)[:1] and (selected or sources)[0], "text": f"Info about {p}"} for p in products]


class GraphContext:
    """Placeholder for graph context - Phase 5."""
    pass
