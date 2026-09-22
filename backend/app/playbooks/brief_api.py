"""Phase 4.1: API endpoints for customer brief extraction."""
from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel
from typing import Optional
from playbooks.brief import extract_brief_with_llm, brief_to_note_content, brief_to_chat_card, CustomerBrief

router = APIRouter(prefix="/api/playbooks/brief", tags=["playbooks"])

class BriefExtractRequest(BaseModel):
    text: str
    notebook_id: Optional[str] = None

class BriefResponse(BaseModel):
    id: str; industry: Optional[str]; rooms_users: Optional[str]
    platforms: list; cloud_requirement: Optional[str]; budget: Optional[str]
    constraints: list; must_haves: list; nice_to_haves: list; exclusions: list
    extracted_at: str

class BriefChatCard(BaseModel):
    type: str; id: str; title: str; fields: dict; editable: bool; extracted_at: str

def _to_resp(b: CustomerBrief) -> BriefResponse:
    return BriefResponse(id=b.id, industry=b.industry, rooms_users=b.rooms_users,
        platforms=b.platforms, cloud_requirement=b.cloud_requirement, budget=b.budget,
        constraints=b.constraints, must_haves=b.must_haves, nice_to_haves=b.nice_to_haves,
        exclusions=b.exclusions, extracted_at=b.extracted_at)

@router.post("/extract", response_model=BriefResponse)
async def extract_brief(req: BriefExtractRequest):
    try: return _to_resp(extract_brief_with_llm(req.text))
    except Exception as e: raise HTTPException(500, f"Brief extraction failed: {e}")

@router.post("/extract/file")
async def extract_brief_file(file: UploadFile = File(...)):
    content = await file.read()
    if file.filename and file.filename.endswith(".txt"):
        text = content.decode("utf-8")
    elif file.filename and file.filename.endswith(".pdf"):
        import pdfplumber, io
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            text = "\n".join(p.extract_text() or "" for p in pdf.pages)
    else:
        raise HTTPException(400, "Unsupported file type. Use .txt or .pdf")
    return _to_resp(extract_brief_with_llm(text))

@router.post("/save-as-note")
async def save_as_note(req: BriefExtractRequest):
    b = extract_brief_with_llm(req.text)
    return {"brief": _to_resp(b), "note_markdown": brief_to_note_content(b), "notebook_id": req.notebook_id}

@router.post("/chat-card", response_model=BriefChatCard)
async def get_chat_card(req: BriefExtractRequest):
    return BriefChatCard(**brief_to_chat_card(extract_brief_with_llm(req.text)))

@router.put("/brief/{brief_id}")
async def update_field(brief_id: str, field: str, value: str):
    valid = {"industry","rooms_users","platforms","cloud_requirement","budget",
             "constraints","must_haves","nice_to_haves","exclusions"}
    if field not in valid: raise HTTPException(400, f"Unknown field: {field}")
    return {"brief_id": brief_id, "updated_field": field, "new_value": value}
