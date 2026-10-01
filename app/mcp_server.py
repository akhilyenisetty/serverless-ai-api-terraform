"""
Your own remote AI backend on AWS.

Two things run in one Lambda (served via the Lambda Web Adapter, behind API Gateway):

  POST /chat   -> a chat/agent endpoint. Offloads heavy AI compute to the CLOUD, so a
                  weak laptop only needs a browser. The end user chooses the compute backend:
                    COMPUTE_BACKEND=bedrock  -> AWS Bedrock (runs in their own AWS, no external key)
                    COMPUTE_BACKEND=byok     -> bring-your-own-key (Anthropic / OpenAI / Grok / HF)
                  Conversation memory is persisted in DynamoDB (keyed by conversation_id).

  /mcp         -> a remote MCP server (Model Context Protocol) exposing example tools
                  (add_note, search_notes) backed by DynamoDB. Bonus feature: plug it into
                  Claude Desktop / Cursor / Copilot.

  GET  /health -> readiness probe for the Lambda Web Adapter.

Env vars (set by Terraform):
  TABLE_NAME         DynamoDB table (notes + conversation memory)
  COMPUTE_BACKEND    "bedrock" | "byok"
  BEDROCK_MODEL_ID   e.g. anthropic.claude-3-haiku-20240307-v1:0   (bedrock mode)
  LLM_PROVIDER       "anthropic" | "openai" | "grok" | "huggingface"  (byok mode)
  LLM_MODEL          provider model name                             (byok mode)
  LLM_BASE_URL       OpenAI-compatible base URL (grok/HF)            (byok mode, optional)
  SECRET_ARN         Secrets Manager ARN holding the API key         (byok mode)
"""
import json
import os
import time
import uuid

import boto3
import httpx
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import HTMLResponse, JSONResponse, PlainTextResponse
from starlette.routing import Route
from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Storage (DynamoDB): used for both the MCP "notes" and chat conversation memory.
# ---------------------------------------------------------------------------
TABLE = os.environ.get("TABLE_NAME", "mcp-on-aws-notes")
_table = boto3.resource("dynamodb").Table(TABLE)


def _load_history(conv_id: str) -> list:
    item = _table.get_item(Key={"id": f"conv#{conv_id}"}).get("Item")
    return item.get("messages", []) if item else []


def _save_history(conv_id: str, messages: list) -> None:
    _table.put_item(Item={
        "id": f"conv#{conv_id}",
        "messages": messages,
        "updated_at": int(time.time()),
    })


# ---------------------------------------------------------------------------
# Compute backends — the core "cloud compute for a weak laptop" piece.
# ---------------------------------------------------------------------------
BACKEND = os.environ.get("COMPUTE_BACKEND", "bedrock")


def _generate(messages: list) -> str:
    """Route to the configured cloud compute backend and return the model's reply text."""
    if BACKEND == "byok":
        return _generate_byok(messages)
    return _generate_bedrock(messages)


# --- AWS Bedrock: runs entirely in the user's own AWS, no external API key ---
_bedrock = boto3.client("bedrock-runtime")
BEDROCK_MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0")


def _generate_bedrock(messages: list) -> str:
    # Bedrock Converse API: ONE unified request/response format across providers
    # (Anthropic Claude, Amazon Nova, Meta Llama, ...). Swap models by changing
    # BEDROCK_MODEL_ID, no code change needed.
    resp = _bedrock.converse(
        modelId=BEDROCK_MODEL_ID,
        messages=[{"role": m["role"], "content": [{"text": m["content"]}]} for m in messages],
        inferenceConfig={"maxTokens": 1024},
    )
    return resp["output"]["message"]["content"][0]["text"]


# --- Bring your own key: Anthropic, or any OpenAI-compatible API (OpenAI/Grok/HF) ---
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "anthropic")
LLM_MODEL = os.environ.get("LLM_MODEL", "")
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1")
SECRET_ARN = os.environ.get("SECRET_ARN", "")


def _get_api_key() -> str:
    val = boto3.client("secretsmanager").get_secret_value(SecretId=SECRET_ARN)["SecretString"]
    return val.strip()


def _generate_byok(messages: list) -> str:
    key = _get_api_key()
    if LLM_PROVIDER == "anthropic":
        r = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": LLM_MODEL or "claude-3-haiku-20240307", "max_tokens": 1024, "messages": messages},
            timeout=60,
        )
        r.raise_for_status()
        return r.json()["content"][0]["text"]
    # openai, grok (base https://api.x.ai/v1), and many HF endpoints are OpenAI-compatible.
    r = httpx.post(
        f"{LLM_BASE_URL}/chat/completions",
        headers={"Authorization": f"Bearer {key}", "content-type": "application/json"},
        json={"model": LLM_MODEL or "gpt-4o-mini", "messages": messages},
        timeout=60,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


# ---------------------------------------------------------------------------
# HTTP handlers
# ---------------------------------------------------------------------------
async def health(_request):
    return PlainTextResponse("ok")


# Minimal browser chat UI, served from the same Lambda (same-origin, no extra infra).
# A weak device just opens this page; all compute runs in the cloud.
UI_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Personal Cloud AI</title>
<style>
 :root{--bg:#0f1221;--panel:#1a1f36;--accent:#5b8cff;--text:#e7eaf3;--muted:#9aa3bd;}
 *{box-sizing:border-box;} body{margin:0;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;
 background:var(--bg);color:var(--text);height:100vh;display:flex;flex-direction:column;}
 header{padding:16px 20px;border-bottom:1px solid #2a3150;}
 header h1{margin:0;font-size:18px;} header p{margin:4px 0 0;color:var(--muted);font-size:13px;}
 #log{flex:1;overflow-y:auto;padding:20px;display:flex;flex-direction:column;gap:12px;}
 .msg{max-width:720px;padding:12px 14px;border-radius:12px;line-height:1.5;white-space:pre-wrap;}
 .user{align-self:flex-end;background:var(--accent);color:#fff;}
 .bot{align-self:flex-start;background:var(--panel);}
 .meta{color:var(--muted);font-size:12px;align-self:center;}
 form{display:flex;gap:10px;padding:16px 20px;border-top:1px solid #2a3150;}
 input{flex:1;padding:12px 14px;border-radius:10px;border:1px solid #2a3150;background:#11152a;color:var(--text);font-size:15px;}
 button{padding:12px 18px;border:0;border-radius:10px;background:var(--accent);color:#fff;font-size:15px;cursor:pointer;}
 button:disabled{opacity:.5;cursor:default;}
</style></head><body>
 <header><h1>Personal Cloud AI</h1><p>Running on your own AWS. Your device just needs this page.</p></header>
 <div id="log"><div class="meta">Ask anything to get started.</div></div>
 <form id="f"><input id="m" autocomplete="off" placeholder="Type a message..."/><button id="s" type="submit">Send</button></form>
<script>
 let convId=null;
 const log=document.getElementById('log'),form=document.getElementById('f'),input=document.getElementById('m'),btn=document.getElementById('s');
 function add(t,c){const d=document.createElement('div');d.className='msg '+c;d.textContent=t;log.appendChild(d);log.scrollTop=log.scrollHeight;return d;}
 form.addEventListener('submit',async(e)=>{
   e.preventDefault();
   const text=input.value.trim(); if(!text) return;
   add(text,'user'); input.value=''; btn.disabled=true;
   const thinking=add('\\u2026','bot');
   try{
     const r=await fetch('/chat',{method:'POST',headers:{'content-type':'application/json'},
       body:JSON.stringify({message:text,conversation_id:convId})});
     const data=await r.json();
     if(data.reply){convId=data.conversation_id; thinking.textContent=data.reply;}
     else{thinking.textContent='Error: '+(data.error||'unknown');}
   }catch(err){thinking.textContent='Network error: '+err;}
   finally{btn.disabled=false; input.focus();}
 });
</script></body></html>"""


async def ui(_request):
    return HTMLResponse(UI_HTML)


async def chat(request):
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON body"}, status_code=400)
    message = (data.get("message") or "").strip()
    if not message:
        return JSONResponse({"error": "message is required"}, status_code=400)

    conv_id = data.get("conversation_id") or str(uuid.uuid4())
    history = _load_history(conv_id)
    history.append({"role": "user", "content": message})
    try:
        reply = _generate(history[-20:])  # bound context to the last ~20 turns
    except Exception as e:
        return JSONResponse({"error": f"model call failed: {e}"}, status_code=502)
    history.append({"role": "assistant", "content": reply})
    _save_history(conv_id, history[-40:])
    return JSONResponse({"conversation_id": conv_id, "reply": reply})


# ---------------------------------------------------------------------------
# MCP server (bonus feature): example tools backed by DynamoDB.
# ---------------------------------------------------------------------------
mcp = FastMCP("notes-mcp", stateless_http=True)


@mcp.tool()
def add_note(title: str, body: str) -> dict:
    """Store a note in the knowledge base and return its id."""
    note_id = str(uuid.uuid4())
    _table.put_item(Item={"id": note_id, "title": title, "body": body, "created_at": int(time.time())})
    return {"id": note_id, "title": title}


@mcp.tool()
def search_notes(query: str) -> list:
    """Return notes whose title or body contains the query (simple substring scan)."""
    q = query.lower()
    items = _table.scan().get("Items", [])
    return [i for i in items if q in i.get("title", "").lower() or q in i.get("body", "").lower()]


# ---------------------------------------------------------------------------
# Assemble the ASGI app: the MCP app (serves /mcp) + our /chat and /health routes.
# ---------------------------------------------------------------------------
app = mcp.streamable_http_app()  # Starlette app; MCP endpoint lives at /mcp, lifespan wired
app.router.routes.append(Route("/", ui, methods=["GET"]))
app.router.routes.append(Route("/health", health, methods=["GET"]))
app.router.routes.append(Route("/chat", chat, methods=["POST", "OPTIONS"]))

# Allow the browser chat UI (added in a later stage) to call /chat.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # personal tool; tighten to your UI's origin for production
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Lambda entry point. Mangum adapts this ASGI app to Lambda/API Gateway events,
# so no Docker and no web server are needed. Terraform sets the handler to
# "mcp_server.handler".
#
# lifespan="off": the chat UI and /chat don't need an ASGI lifespan, and the MCP
# server's session manager can only .run() once per instance, which Mangum's
# per-invocation lifespan breaks on Lambda. Turning it off makes the core rock-solid.
# (The /mcp bonus needs a long-lived server; deploy the container/Web-Adapter variant
# for full MCP support.)
# ---------------------------------------------------------------------------
from mangum import Mangum  # noqa: E402

handler = Mangum(app, lifespan="off")

