# app.py
from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Optional, Any
import pandas as pd
import pickle
import logging
import os

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# Import your document generator
from Vendor_agreement import DocumentGenerator

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Supplier Management API", version="1.0.0")

# ----------------- Rate limiting -----------------
limiter = Limiter(key_func=get_remote_address, default_limits=["120/minute"])
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ----------------- CORS -----------------
# Restrict to an explicit allow-list. Override with the ALLOWED_ORIGINS env var
# (comma-separated). "*" is still accepted for local development only.
_default_origins = "http://localhost:5173,https://zealous-wave-0e9e7b600.1.azurestaticapps.net"
_origins_env = os.environ.get("ALLOWED_ORIGINS", _default_origins).strip()
if _origins_env == "*":
    cors_kwargs = dict(allow_origins=["*"], allow_credentials=False)
else:
    cors_kwargs = dict(
        allow_origins=[o.strip() for o in _origins_env.split(",") if o.strip()],
        allow_credentials=True,
    )
app.add_middleware(
    CORSMiddleware,
    allow_methods=["*"],
    allow_headers=["*"],
    **cors_kwargs,
)

SUPPORTED_TEXT_EXT = {".txt", ".csv", ".md", ".json"}


# Health check endpoint (required for Azure)
@app.get("/")
async def root():
    return {"status": "healthy", "message": "Supplier Management API is running"}


# Health check for Azure
@app.get("/health")
async def health_check():
    return {"status": "healthy"}


# ----------------- Supplier Ranking Model -----------------
# Model loading with enhanced error handling
try:
    model = None
    try:
        with open("rank_model.pkl", "rb") as f:
            model = pickle.load(f)
    except Exception:
        try:
            import joblib
            model = joblib.load("rank_model.pkl")
        except Exception:
            logger.warning("Could not load model file")
except Exception as e:
    logger.error(f"Model loading failed: {e}")
    model = None


# ----------------- Supplier Ranking Endpoint -----------------
REQUIRED_FEATURES = {
    'score': 'Score',
    'risk_score': 'Risk Score',
    'sentiment_score': 'Sentiment Score',
    'esg_score': 'ESG Score',
    'delay_days': 'Delay Days',
}

# Fallback columns the Node API already returns for a supplier, used when the
# caller doesn't send the exact model feature keys.
FEATURE_FALLBACKS = {
    'score': ('score', 'rating', 'otd', 'stability_score'),
    'risk_score': ('risk_score', 'risk'),
    'sentiment_score': ('sentiment_score', 'sentiment'),
    'esg_score': ('esg_score', 'stability_score', 'fulfillment_rate'),
    'delay_days': ('delay_days', 'recent_delays', 'lead_time'),
}


def _coerce_num(value, default=0.0):
    try:
        if value in (None, "", True, False):
            return float(default)
        return float(value)
    except (TypeError, ValueError):
        return float(default)


@app.post("/api/suppliers/suggest")
@limiter.limit("30/minute")
async def suggest_suppliers(request: Request, suppliers: List[Dict]):
    try:
        if not suppliers:
            return []
        if model is None:
            # Degrade gracefully instead of 500 — the marketplace has its own fallback.
            logger.warning("Ranking model not loaded; returning input order")
            return suppliers

        logger.info(f"Received {len(suppliers)} suppliers for ranking")
        df = pd.DataFrame(suppliers)

        # Fill any missing model feature from a known fallback column (or 0).
        for feat, model_name in REQUIRED_FEATURES.items():
            if feat in df.columns:
                series = df[feat]
            else:
                series = None
                for alt in FEATURE_FALLBACKS[feat]:
                    if alt in df.columns:
                        series = df[alt]
                        break
            if series is None:
                df[model_name] = 0.0
            else:
                df[model_name] = series.map(lambda v: _coerce_num(v))

        predictions = model.predict(df[list(REQUIRED_FEATURES.values())])
        df['suggested_rank'] = predictions
        result = df.sort_values('suggested_rank').to_dict('records')

        logger.info(f"Successfully ranked {len(result)} suppliers")
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ranking failed: {str(e)}", exc_info=True)
        # Never break the marketplace over ranking — hand back the unranked list.
        return suppliers


# ----------------- Document Generation -----------------
generator = DocumentGenerator()


class AgreementRequest(BaseModel):
    vendor: str = "[SUPPLIER NAME]"
    contract_title: str = "[CONTRACT TITLE]"
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    details: str = "[PRODUCT/SERVICE DESCRIPTION]"
    rfq_po: Dict[str, Any] = {}
    contract_type: str = "General"
    price_type: Optional[str] = None
    procurement_data: Optional[dict] = None


@app.post("/generate_agreement")
@limiter.limit("20/minute")
async def generate_agreement(request: Request, body: AgreementRequest):
    try:
        procurement_data = body.rfq_po.get('procurementData', {}) if body.rfq_po else {}

        agreement = generator.generate_agreement(
            vendor=body.vendor,
            contract_title=body.contract_title,
            start_date=body.start_date,
            end_date=body.end_date,
            details=body.details,
            rfq_po=body.rfq_po,
            contract_type=body.contract_type,
            price_type=body.price_type,
            procurement_data=procurement_data
        )
        return {"status": "success", "agreement": agreement}
    except Exception as e:
        logger.error(f"Error generating agreement: {str(e)}")
        return {"status": "error", "message": str(e)}


BLOCK_GENERATORS = {
    "title": "_generate_title_block",
    "contract_id": "_generate_contract_id",
    "parties_intro": "_generate_parties_intro",
    "buyer": "_generate_buyer_block",
    "supplier": "_generate_supplier_block",
    "scope": "_generate_scope_block",
    "commercial": "_generate_commercial_block",
    "delivery": "_generate_delivery_block",
    "quality": "_generate_quality_block",
    "penalties": "_generate_penalties_block",
    "confidentiality": "_generate_confidentiality_block",
    "force_majeure": "_generate_force_majeure_block",
    "termination": "_generate_termination_block",
    "dispute_resolution": "_generate_dispute_resolution_block",
    "digital_signatures": "_generate_digital_signatures_block",
}


@app.post("/generate_block/{block_name}")
@limiter.limit("40/minute")
async def generate_single_block(request: Request, block_name: str, body: Dict[str, Any]):
    """Regenerate a single contract section, keeping it consistent with the rest
    of the document by rebuilding context from the current form data."""
    try:
        if block_name not in BLOCK_GENERATORS:
            return {"status": "error", "message": "Invalid block name"}

        fd = body.get("form_data") or {}

        # Rebuild the parsing context (mirrors generate_agreement).
        generator.parsed_prompt = generator._parse_user_prompt(
            vendor=fd.get("vendorLegalName") or fd.get("vendor") or body.get("user_prompt"),
            contract_title=fd.get("contractTitle") or fd.get("contract_title"),
            start_date=fd.get("startDate") or fd.get("start_date"),
            end_date=fd.get("endDate") or fd.get("end_date"),
            details=fd.get("describeProduct") or fd.get("details"),
            rfq_po=fd.get("linkedRfq") or fd.get("rfq_po") or fd,
            contract_type=fd.get("contractType") or fd.get("contract_type") or "General",
            price_type=fd.get("totalContractValue") or fd.get("budget") or fd.get("price_type"),
        )
        generator.generated_content_history = []

        method = getattr(generator, BLOCK_GENERATORS[block_name])
        content = method()
        parsed = generator._parse_to_blocks(content)
        section = parsed.get(block_name) or content

        # Front-end reads `generated_content`; keep the legacy key too.
        return {"status": "success", "generated_content": section, block_name: section}
    except Exception as e:
        logger.error(f"generate_block failed: {str(e)}")
        return {"status": "error", "message": str(e)}


# ----------------- AI Bid Leveling Analysis -----------------
class BidLevelingRequest(BaseModel):
    rfq: Dict[str, Any]
    bids: List[Dict[str, Any]]


@app.post("/api/ai/level-bids")
@limiter.limit("30/minute")
async def ai_level_bids(request: Request, body: BidLevelingRequest):
    bids = body.bids
    rfq = body.rfq
    if not bids:
        return {"status": "error", "message": "No bids provided"}

    try:
        bids_desc = []
        for i, b in enumerate(bids):
            bids_desc.append(
                f"Vendor {i+1}: {b.get('vendor_email', 'Unknown')}\n"
                f"- Landed Total: ${b.get('landed_total')} (Unit Price: ${b.get('unit_price')}, Freight: ${b.get('freight')}, Tax: {b.get('tax_pct')}%)\n"
                f"- Payment Terms: {b.get('payment_terms')} (Working Capital Impact: ${b.get('payment_term_adj')})\n"
                f"- Lead Time: {b.get('lead_time_days')} days (Lead Penalty: ${b.get('lead_time_penalty')})\n"
                f"- Warranty: {b.get('warranty_months')} months (Warranty Credit: ${b.get('warranty_adj')})\n"
                f"- Calculated TCO: ${b.get('tco_total')} (${b.get('tco_per_unit')}/unit)\n"
                f"- Notes: {b.get('bid_notes', 'None')}"
            )

        prompt = (
            f"You are an expert enterprise procurement leveling specialist.\n"
            f"Analyze the following normalized vendor bids for RFQ: {rfq.get('title', 'Procurement Request')} "
            f"(Qty: {rfq.get('quantity', 1)} {rfq.get('unit', 'units')}, Budget: ${rfq.get('budget', 'N/A')}).\n\n"
            f"NORMALIZED BIDS:\n" + "\n\n".join(bids_desc) + "\n\n"
            f"Provide an objective, executive bid leveling evaluation in JSON format with exactly the following keys:\n"
            f"1. \"recommended_vendor_email\": email of the recommended vendor\n"
            f"2. \"recommendation_summary\": 2-3 concise sentences explaining why this vendor is recommended (TCO vs raw price, terms, lead time)\n"
            f"3. \"commercial_tradeoffs\": narrative explaining the trade-offs\n"
            f"4. \"vendor_evaluations\": list of objects with \"vendor_email\", \"pros\" (list of strings), \"cons\" (list of strings)\n\n"
            f"Respond ONLY with valid JSON."
        )

        response_text = ""
        azure_key = os.getenv("AZURE_OPENAI_KEY")
        azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        azure_deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-5-mini")
        azure_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")

        if azure_key and azure_endpoint:
            try:
                from openai import AzureOpenAI
                az_client = AzureOpenAI(
                    api_key=azure_key,
                    api_version=azure_version,
                    azure_endpoint=azure_endpoint,
                )
                az_res = az_client.chat.completions.create(
                    model=azure_deployment,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.2,
                    max_tokens=1000,
                )
                response_text = az_res.choices[0].message.content.strip()
            except Exception as e_az:
                logger.warning(f"Azure OpenAI call failed, falling back to Groq: {e_az}")
                response_text = ""

        if not response_text:
            response_text = generator._call_groq(prompt)

        import json, re
        cleaned = re.sub(r"^```json\s*", "", response_text)
        cleaned = re.sub(r"```$", "", cleaned).strip()
        parsed = json.loads(cleaned)
        return parsed
    except Exception as e:
        logger.error(f"AI level bids fallback triggered: {e}")
        best = bids[0] if bids else {}
        return {
            "recommended_vendor_email": best.get("vendor_email"),
            "recommendation_summary": f"Recommended award to {best.get('vendor_email')} with the lowest Total Cost of Ownership (${best.get('tco_total')}) and favorable terms ({best.get('payment_terms')}).",
            "commercial_tradeoffs": "Leveling evaluated landed freight, working capital payment term benefits, and lead-time penalties.",
            "vendor_evaluations": [
                {
                    "vendor_email": b.get("vendor_email"),
                    "pros": ["Lowest TCO" if i == 0 else "Competitive alternative"],
                    "cons": [],
                }
                for i, b in enumerate(bids)
            ],
        }


# ----------------- Chatbot -----------------
class ChatRequest(BaseModel):
    message: str
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    category: Optional[str] = None
    file_references: List[Dict[str, Any]] = []


@app.get("/api/user/profile")
async def user_profile(x_user_email: Optional[str] = Header(default=None)):
    # The AI service has no database; return what the request already knows.
    return {"email": x_user_email, "user_type": "user"}


@app.post("/api/upload/files")
@limiter.limit("30/minute")
async def upload_files(request: Request, files: List[UploadFile] = File(...)):
    uploaded = []
    for f in files:
        raw = await f.read()
        ext = os.path.splitext(f.filename or "")[1].lower()
        excerpt = ""
        if ext in SUPPORTED_TEXT_EXT:
            try:
                excerpt = raw.decode("utf-8", errors="ignore")[:4000]
            except Exception:
                excerpt = ""
        uploaded.append({
            "filename": f.filename,
            "content_type": f.content_type,
            "bytes": len(raw),
            "text_excerpt": excerpt,
        })
    return {"uploaded_files": uploaded}


@app.post("/api/chat")
@limiter.limit("30/minute")
async def chat(request: Request, body: ChatRequest):
    try:
        context_parts = []
        for ref in body.file_references or []:
            snippet = ref.get("text_excerpt") or ""
            if snippet:
                context_parts.append(f"--- {ref.get('filename', 'file')} ---\n{snippet}")
        file_context = "\n\n".join(context_parts)

        prompt = (
            "You are SVM GPT, an assistant for a supplier & vendor management platform. "
            "Answer concisely and practically for procurement, contract and supplier-performance questions.\n\n"
        )
        if body.category:
            prompt += f"Focus area: {body.category}\n"
        if file_context:
            prompt += f"The user attached documents:\n{file_context}\n\n"
        prompt += f"User: {body.message}"

        answer = generator._call_groq(prompt)
        return {
            "status": "success",
            "response": {
                "content": answer,
                "type": "intelligence_response",
                "user_specific": False,
                "file_analysis": bool(file_context),
                "files": [],
            },
        }
    except Exception as e:
        logger.error(f"Chat failed: {str(e)}")
        return {"status": "error", "message": str(e)}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
