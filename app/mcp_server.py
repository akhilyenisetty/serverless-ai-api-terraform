"""
Your own remote AI backend on AWS (served from one Lambda via Mangum + API Gateway).

Routes:
  GET  /        -> browser chat UI (a weak device just opens this page; compute is in the cloud)
  POST /chat    -> chat/agent endpoint. Compute backend chosen by the operator:
                     COMPUTE_BACKEND=bedrock -> AWS Bedrock (Converse API, runs in your AWS)
                     COMPUTE_BACKEND=byok    -> bring-your-own-key (Anthropic / OpenAI / Grok / HF)
                   Conversation memory persists in DynamoDB.
  POST /mcp     -> remote MCP server (Model Context Protocol) implemented as a STATELESS
                   JSON-RPC handler, so it works on Lambda's request/response model.
                   Tools: add_note, search_notes (backed by DynamoDB).
  GET  /health  -> readiness probe.

Env (set by Terraform): TABLE_NAME, COMPUTE_BACKEND, BEDROCK_MODEL_ID, LLM_PROVIDER,
LLM_MODEL, LLM_BASE_URL, SECRET_ARN.
"""
import json
import os
import time
import uuid
from decimal import Decimal

import boto3
import httpx
from mangum import Mangum
from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import HTMLResponse, JSONResponse, PlainTextResponse
from starlette.routing import Route

# ---------------------------------------------------------------------------
# Storage (DynamoDB): MCP notes + chat conversation memory.
# ---------------------------------------------------------------------------
TABLE = os.environ.get("TABLE_NAME", "mcp-on-aws-notes")
_table = boto3.resource("dynamodb").Table(TABLE)


def _load_history(conv_id: str) -> list:
    item = _table.get_item(Key={"id": f"conv#{conv_id}"}).get("Item")
    return item.get("messages", []) if item else []


def _save_history(conv_id: str, messages: list) -> None:
    _table.put_item(Item={"id": f"conv#{conv_id}", "messages": messages, "updated_at": int(time.time())})


# ---------------------------------------------------------------------------
# Compute backends (the "cloud compute for a weak laptop" core).
# ---------------------------------------------------------------------------
BACKEND = os.environ.get("COMPUTE_BACKEND", "bedrock")
_bedrock = boto3.client("bedrock-runtime")
BEDROCK_MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-haiku-4-5-20251001-v1:0")
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "anthropic")
LLM_MODEL = os.environ.get("LLM_MODEL", "")
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1")
SECRET_ARN = os.environ.get("SECRET_ARN", "")


def _generate(messages: list) -> str:
    # Bedrock backend is AGENTIC: it can call the tools (see _bedrock_agent).
    # byok stays a plain chat call.
    return _generate_byok(messages) if BACKEND == "byok" else _bedrock_agent(messages)


def _get_api_key() -> str:
    return boto3.client("secretsmanager").get_secret_value(SecretId=SECRET_ARN)["SecretString"].strip()


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
    r = httpx.post(
        f"{LLM_BASE_URL}/chat/completions",
        headers={"Authorization": f"Bearer {key}", "content-type": "application/json"},
        json={"model": LLM_MODEL or "gpt-4o-mini", "messages": messages},
        timeout=60,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


# ---------------------------------------------------------------------------
# MCP tools (backed by DynamoDB) + the stateless JSON-RPC handler.
# ---------------------------------------------------------------------------
MCP_TOOLS = [
    {
        "name": "add_note",
        "description": "Store a note in the knowledge base and return its id.",
        "inputSchema": {
            "type": "object",
            "properties": {"title": {"type": "string"}, "body": {"type": "string"}},
            "required": ["title", "body"],
        },
    },
    {
        "name": "search_notes",
        "description": "Return notes whose title or body contains the query.",
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
]


def _tool_add_note(title: str, body: str) -> dict:
    note_id = str(uuid.uuid4())
    _table.put_item(Item={"id": note_id, "title": title, "body": body, "created_at": int(time.time())})
    return {"id": note_id, "title": title}


def _tool_search_notes(query: str) -> list:
    q = query.lower()
    items = _table.scan().get("Items", [])
    return [i for i in items if q in i.get("title", "").lower() or q in i.get("body", "").lower()]


def _json_default(o):
    # DynamoDB returns numbers as Decimal, which json.dumps can't handle natively.
    if isinstance(o, Decimal):
        return int(o) if o % 1 == 0 else float(o)
    raise TypeError(f"not serializable: {type(o)}")


def _rpc_result(req_id, result):
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _rpc_error(req_id, code, message):
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


async def mcp_endpoint(request):
    # Stateless MCP over Streamable HTTP: JSON-RPC in, JSON out. No session manager,
    # so it works within Lambda's request/response model.
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(_rpc_error(None, -32700, "Parse error"), status_code=400)

    method = body.get("method")
    req_id = body.get("id")

    # Notifications (no id, e.g. notifications/initialized) just get acknowledged.
    if req_id is None and isinstance(method, str) and method.startswith("notifications/"):
        return PlainTextResponse("", status_code=202)

    if method == "initialize":
        proto = (body.get("params") or {}).get("protocolVersion", "2025-03-26")
        return JSONResponse(_rpc_result(req_id, {
            "protocolVersion": proto,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "notes-mcp", "version": "1.0.0"},
        }))

    if method == "ping":
        return JSONResponse(_rpc_result(req_id, {}))

    if method == "tools/list":
        return JSONResponse(_rpc_result(req_id, {"tools": MCP_TOOLS}))

    if method == "tools/call":
        params = body.get("params") or {}
        name = params.get("name")
        args = params.get("arguments") or {}
        try:
            if name == "add_note":
                out = _tool_add_note(args["title"], args["body"])
            elif name == "search_notes":
                out = _tool_search_notes(args["query"])
            else:
                return JSONResponse(_rpc_error(req_id, -32602, f"Unknown tool: {name}"))
            return JSONResponse(_rpc_result(req_id, {
                "content": [{"type": "text", "text": json.dumps(out, default=_json_default)}],
                "isError": False,
            }))
        except Exception as e:  # tool errors are reported in-band, per MCP
            return JSONResponse(_rpc_result(req_id, {
                "content": [{"type": "text", "text": f"Error: {e}"}],
                "isError": True,
            }))

    return JSONResponse(_rpc_error(req_id, -32601, f"Method not found: {method}"))


# ---------------------------------------------------------------------------
# External MCP servers (option C): the chat acts as an MCP CLIENT and can connect to
# other MCP servers you run (e.g. a WhatsApp MCP). Configure them via the
# EXTERNAL_MCP_SERVERS env var: a JSON list of {"name","url","auth"(optional bearer)}.
# Their tools are discovered and merged with the local ones, and the agent routes calls.
# ---------------------------------------------------------------------------
try:
    _EXTERNAL_MCP = json.loads(os.environ.get("EXTERNAL_MCP_SERVERS", "[]"))
except Exception:
    _EXTERNAL_MCP = []
_ext_tools = None     # cached external tool specs (discovered once per container)
_ext_routing = {}     # tool name -> server config


def _mcp_remote_call(server, method, params=None):
    headers = {"content-type": "application/json", "accept": "application/json"}
    if server.get("auth"):
        headers["authorization"] = f"Bearer {server['auth']}"
    payload = {"jsonrpc": "2.0", "id": 1, "method": method}
    if params is not None:
        payload["params"] = params
    r = httpx.post(server["url"], headers=headers, json=payload, timeout=30)
    r.raise_for_status()
    data = r.json()
    if "error" in data:
        raise RuntimeError(data["error"])
    return data.get("result", {})


def _discover_external():
    global _ext_tools, _ext_routing
    if _ext_tools is not None:
        return
    local_names = {t["name"] for t in MCP_TOOLS}
    tools, routing = [], {}
    for s in _EXTERNAL_MCP:
        try:
            _mcp_remote_call(s, "initialize", {"protocolVersion": "2025-03-26",
                "capabilities": {}, "clientInfo": {"name": "cloud-ai-chat", "version": "1.0"}})
            res = _mcp_remote_call(s, "tools/list")
            for t in res.get("tools", []):
                n = t.get("name")
                if not n or n in local_names or n in routing:
                    continue  # local tools win on name clashes
                tools.append({"name": n, "description": t.get("description", ""),
                              "inputSchema": t.get("inputSchema", {"type": "object", "properties": {}})})
                routing[n] = s
        except Exception:
            continue  # a down/misconfigured external server must not break chat
    _ext_tools, _ext_routing = tools, routing


def _all_tools():
    _discover_external()
    return MCP_TOOLS + (_ext_tools or [])


def _tool_config():
    return {"tools": [
        {"toolSpec": {"name": t["name"], "description": t["description"], "inputSchema": {"json": t["inputSchema"]}}}
        for t in _all_tools()
    ]}


def _run_tool(name, args):
    if name in _ext_routing:  # route to the external MCP server that owns this tool
        res = _mcp_remote_call(_ext_routing[name], "tools/call", {"name": name, "arguments": args})
        texts = [c.get("text", "") for c in res.get("content", []) if c.get("type") == "text"]
        return "\n".join(texts) if texts else res
    if name == "add_note":
        return _tool_add_note(args.get("title", ""), args.get("body", ""))
    if name == "search_notes":
        return _tool_search_notes(args.get("query", ""))
    return {"error": f"unknown tool: {name}"}


def _jsonable(o):
    return json.loads(json.dumps(o, default=_json_default))


def _text_of(msg):
    return "".join(b.get("text", "") for b in msg.get("content", []) if "text" in b).strip()


def _bedrock_agent(messages_text, max_steps=8):
    # Tool-use loop: call the model with ALL tools (local + external MCP servers); if it
    # asks for a tool, run/route it, feed the result back, and continue until it answers.
    conv = [{"role": m["role"], "content": [{"text": m["content"]}]} for m in messages_text]
    tool_config = _tool_config()
    for _ in range(max_steps):
        resp = _bedrock.converse(
            modelId=BEDROCK_MODEL_ID,
            messages=conv,
            toolConfig=tool_config,
            inferenceConfig={"maxTokens": 1024},
        )
        out_msg = resp["output"]["message"]
        conv.append(out_msg)
        if resp.get("stopReason") != "tool_use":
            return _text_of(out_msg)
        results = []
        for block in out_msg.get("content", []):
            tu = block.get("toolUse")
            if tu:
                res = _run_tool(tu.get("name"), tu.get("input") or {})
                content = [{"text": res}] if isinstance(res, str) else [{"json": _jsonable(res)}]
                results.append({"toolResult": {"toolUseId": tu["toolUseId"], "content": content}})
        conv.append({"role": "user", "content": results})
    return "(stopped after too many tool steps)"


# ---------------------------------------------------------------------------
# HTTP handlers: health, chat, UI.
# ---------------------------------------------------------------------------
async def health(_request):
    return PlainTextResponse("ok")


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
        reply = _generate(history[-20:])
    except Exception as e:
        return JSONResponse({"error": f"model call failed: {e}"}, status_code=502)
    history.append({"role": "assistant", "content": reply})
    _save_history(conv_id, history[-40:])
    return JSONResponse({"conversation_id": conv_id, "reply": reply})


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


# ---------------------------------------------------------------------------
# App + Lambda entry point.
# ---------------------------------------------------------------------------
app = Starlette(routes=[
    Route("/", ui, methods=["GET"]),
    Route("/health", health, methods=["GET"]),
    Route("/chat", chat, methods=["POST", "OPTIONS"]),
    Route("/mcp", mcp_endpoint, methods=["POST", "OPTIONS"]),
])
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

handler = Mangum(app, lifespan="off")
