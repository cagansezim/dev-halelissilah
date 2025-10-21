from __future__ import annotations
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["ai-chat"])

@router.get("/ai_chat", response_class=HTMLResponse)
def ai_chat_page() -> str:
    return r"""<!doctype html>
<html>
<head>
<meta charset="utf-8"/>
<title>Pruva AI — AI Chat</title>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<style>
:root{
  --ink:#0b1222; --muted:#64748b; --line:#e9edf3; --bg:#f6f8fb; --card:#fff;
  --chip:#eef3ff; --primary:#2563eb; --ok:#10b981; --warn:#f59e0b; --danger:#ef4444;
  --shadow:0 6px 24px rgba(15,23,42,.06), 0 2px 6px rgba(15,23,42,.04);
}
*{box-sizing:border-box}
html,body{height:100%}
body{margin:0;background:var(--bg);color:var(--ink);font:14px system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
button,input,select,textarea{font:inherit}
a{color:inherit;text-decoration:none}
.app{display:grid;grid-template-columns:320px 1fr;min-height:100vh}

/* Rail (tree) */
.rail{background:#fff;border-right:1px solid var(--line);padding:14px 12px;display:flex;flex-direction:column;gap:12px}
.brand{display:flex;gap:10px;align-items:center}
.logo{width:34px;height:34px;border-radius:10px;background:#eef3ff}
.brand .name{font-weight:700}
.small{font-size:12px;color:var(--muted)}
.sec{display:flex;align-items:center;justify-content:space-between;margin-top:4px}
.controls{display:flex;gap:6px}
.btn{border:1px solid var(--line);background:#fff;border-radius:10px;padding:6px 9px;cursor:pointer}
.btn.primary{background:var(--primary);border-color:var(--primary);color:#fff}
.btn.bad{background:#fff;border-color:#ffd1d1}
.tree{display:flex;flex-direction:column;gap:6px}
.node{border:1px solid var(--line);border-radius:10px}
.nodeHead{display:flex;align-items:center;gap:8px;padding:8px 10px;cursor:pointer}
.nodeHead:hover{background:#f7faff}
.nodeTitle{flex:1}
.nodeAct{display:flex;gap:6px}
.nodeBody{padding:8px 10px;border-top:1px dashed var(--line);display:none}
.node.open>.nodeBody{display:block}
.tag{background:var(--chip);padding:2px 6px;border-radius:6px;font-size:12px}
.item{display:flex;align-items:center;gap:8px;padding:8px;border:1px solid var(--line);border-radius:10px;cursor:pointer;margin:6px 0}
.item.active{background:#f5f8ff;border-color:#cfe0ff}
.inlineInput{border:1px solid var(--line);border-radius:8px;padding:4px 6px;width:100%}

/* Main */
.main{display:grid;grid-template-rows:auto 1fr auto;gap:10px;padding:14px 16px}
.toolbar{display:flex;align-items:center;justify-content:space-between}
.toolbar .group{display:flex;gap:8px;align-items:center}
select{border:1px solid var(--line);border-radius:10px;background:#fff;padding:8px 10px}
.chip{background:var(--chip);padding:2px 6px;border-radius:6px;font-size:12px}
.status{display:inline-flex;align-items:center;gap:8px;border:1px solid #dbe5ff;background:#f6faff;border-radius:999px;padding:4px 8px}
.blink{width:6px;height:6px;background:var(--primary);border-radius:50%;animation:blink 1s infinite}
@keyframes blink{0%,100%{opacity:.2}50%{opacity:1}}

.card{background:var(--card);border:1px solid var(--line);border-radius:14px;box-shadow:var(--shadow)}
.thread{padding:14px;overflow:auto}
.bubble{max-width:900px;margin:12px auto;padding:14px 16px;border:1px solid var(--line);border-radius:14px;line-height:1.45;position:relative}
.me{background:#f6faff}
.ai{background:#fff}
.meta{display:flex;align-items:center;gap:8px;font-size:12px;color:var(--muted);margin-bottom:6px}
.attachRow{display:flex;gap:6px;flex-wrap:wrap;margin-top:8px}
.attach{display:inline-flex;align-items:center;gap:6px;padding:4px 8px;border:1px dashed var(--line);border-radius:10px}
.attach img{width:22px;height:22px;border-radius:4px;border:1px solid var(--line);object-fit:cover}
details.disc{background:#f8fafc;border:1px dashed var(--line);border-radius:10px;padding:8px 10px;margin-top:8px}
details.disc>summary{cursor:pointer;font-weight:600}
pre.json{margin:0;padding:12px;background:#0f172a;color:#d7e3ff;border-radius:10px;overflow:auto;font:12px ui-monospace,Menlo,Consolas,monospace;max-height:360px}

/* Composer */
.composerWrap{position:sticky;bottom:0}
.composer{display:grid;grid-template-columns:1fr auto;gap:10px;padding:10px}
.composeBox{display:grid;grid-template-rows:auto 1fr auto;gap:8px;border:1px solid var(--line);border-radius:14px;background:#fff;padding:10px}
.icons{display:flex;gap:8px}
.ic{width:36px;height:36px;border:1px solid var(--line);border-radius:10px;display:grid;place-items:center;background:#fff;cursor:pointer;position:relative}
.pop{position:absolute;bottom:42px;right:0;background:#fff;border:1px solid var(--line);border-radius:10px;box-shadow:var(--shadow);min-width:260px;padding:8px;z-index:5;display:none}
.ic.open .pop{display:block}
.menu{display:flex;flex-direction:column;gap:6px}
.menu .row{display:flex;align-items:center;justify-content:space-between}
.textarea{min-height:84px;max-height:220px;overflow:auto}
.textarea textarea{width:100%;height:100%;border:none;outline:none;resize:vertical;padding:0 2px}
.thumbs{display:flex;gap:8px;flex-wrap:wrap}
.thumb{width:74px;height:74px;border:1px solid var(--line);border-radius:10px;overflow:hidden;position:relative;background:#0b1222}
.thumb img{width:100%;height:100%;object-fit:cover}
.thumb .x{position:absolute;top:4px;right:4px;background:rgba(0,0,0,.55);color:#fff;border:0;border-radius:6px;font-size:11px;line-height:1;padding:4px 6px;cursor:pointer}

.toast{position:fixed;left:50%;bottom:22px;transform:translateX(-50%);background:#111;color:#fff;padding:10px 14px;border-radius:10px;box-shadow:var(--shadow);opacity:0;pointer-events:none;transition:opacity .2s}
.toast.show{opacity:1}
.mono{font-family:ui-monospace,Menlo,Consolas,monospace}
.preview{width:34px;height:34px;border:1px solid var(--line);border-radius:8px;overflow:hidden;background:#f5f7ff;display:grid;place-items:center}
.preview img{width:100%;height:100%;object-fit:cover}
</style>
</head>
<body>
<div class="app">
  <!-- LEFT: Workspaces -> Chats -->
  <div class="rail">
    <div class="brand">
      <div class="logo"></div>
      <div><div class="name">Pruva AI</div><div class="small">Invoice Extraction</div></div>
    </div>

    <div class="sec"><b>Workspaces</b>
      <div class="controls">
        <button id="wsAdd" class="btn">＋</button>
      </div>
    </div>
    <div id="tree" class="tree"></div>

    <div class="sec"><b>Utilities</b>
      <div class="controls">
        <button id="btnExportChat" class="btn">Export</button>
        <button id="btnClearChat" class="btn bad">Clear</button>
      </div>
    </div>
  </div>

  <!-- RIGHT: Toolbar, Thread, Composer -->
  <div class="main">
    <div class="toolbar">
      <div class="group">
        <button id="btnBack" class="btn">← Back</button>
        <span class="chip" id="crumb">Workspace / Chat</span>
        <span class="small">via <span class="chip">/api/llm/chat</span></span>
      </div>
      <div class="group">
        <select id="modelSel"><option>Loading models…</option></select>
        <label class="small" style="display:flex;align-items:center;gap:6px">
          <input id="chkOcr" type="checkbox"> OCR first if not vision
        </label>
        <span id="status" class="status" style="display:none"><span class="blink"></span> Thinking…</span>
      </div>
    </div>

    <div id="thread" class="card thread" aria-live="polite"></div>

    <div class="composerWrap card">
      <div class="composer">
        <div class="composeBox">
          <div style="display:flex;align-items:center;justify-content:space-between">
            <div class="small">Fields preset & selection</div>
            <div class="icons">
              <!-- Fields popup -->
              <div class="ic" id="icFields" title="Fields">
                🧩
                <div class="pop">
                  <div class="menu">
                    <div class="row"><b>Presets</b>
                      <div class="controls">
                        <button class="btn" data-preset="typical">Typical</button>
                        <button class="btn" data-preset="all">All</button>
                        <button class="btn" data-preset="none">None</button>
                      </div>
                    </div>
                    <hr style="border:none;border-top:1px solid var(--line)">
                    <b>Header (masraf)</b>
                    <div id="fldHeader" style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin:6px 0"></div>
                    <b>Items (MasrafAlt)</b>
                    <div id="fldItem" style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin:6px 0"></div>
                    <b>File (Dosya)</b>
                    <div id="fldFile" style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin:6px 0"></div>
                  </div>
                </div>
              </div>

              <!-- Dataset picker -->
              <div class="ic" id="icDataset" title="Dataset">
                🗂️
                <div class="pop" style="min-width:700px;max-width:880px">
                  <div class="menu">
                    <div class="row">
                      <b>Dataset</b>
                      <div class="controls">
                        <button id="btnLoadDataset" class="btn">Load from API</button>
                        <button id="btnApplyDataset" class="btn primary">Add selected</button>
                      </div>
                    </div>
                    <div id="dsInfo" class="small">
                      API endpoints tried:
                      <code>/api/dataset/list</code> → expenses,
                      then files via
                      <code>/api/expense/{kod}</code> (preferred),
                      <code>/api/dataset/expense_files</code>,
                      <code>/api/dataset/files?expense_id=…</code>,
                      <code>/api/expense/{kod}/files</code>,
                      <code>/api/expense_files?expense_id=…</code>
                      (first match wins).
                    </div>
                    <div id="dsList" style="max-height:300px;overflow:auto;border:1px solid var(--line);border-radius:10px;padding:6px;margin-top:6px"></div>
                    <details id="dsRawWrap" class="disc" style="margin-top:6px;display:none">
                      <summary>Last dataset API raw (debug)</summary>
                      <pre id="dsRaw" class="json">{}</pre>
                    </details>
                    <details class="disc" style="margin-top:6px">
                      <summary>Paste JSON (expense or file objects)</summary>
                      <textarea id="dsJson" rows="8" style="width:100%;border:1px solid var(--line);border-radius:10px;padding:8px" placeholder="Paste your expense JSON here and click Parse"></textarea>
                      <div class="row" style="margin-top:6px;justify-content:flex-end">
                        <button id="btnParseJson" class="btn">Parse</button>
                      </div>
                    </details>
                  </div>
                </div>
              </div>

              <!-- Attach local files -->
              <label class="ic" title="Attach files">
                📎
                <input id="filePick" type="file" multiple accept="image/*,.pdf,.png,.jpg,.jpeg" style="display:none">
              </label>

              <!-- System prompt -->
              <div class="ic" id="icSys" title="System">
                📝
                <div class="pop" style="min-width:540px">
                  <div class="menu">
                    <textarea id="sysPrompt" rows="6" placeholder="Optional system prompt (English enforced)" style="width:100%;border:1px solid var(--line);border-radius:10px;padding:8px"></textarea>
                  </div>
                </div>
              </div>

              <!-- Help -->
              <div class="ic" id="icHelp" title="Help">
                ❔
                <div class="pop" style="min-width:360px">
                  <div class="menu small">
                    <div>• Pick a model. Vision models receive images as context.</div>
                    <div>• Use OCR first for non-vision models (needs <code>POST /api/ocr/extract</code>).</div>
                    <div>• Use 🗂️ to attach dataset images/PDFs or whole expenses.</div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div id="dropzone" class="textarea">
            <textarea id="msgBox" placeholder="Type a message. Enter to send • Shift+Enter for newline"></textarea>
          </div>

          <div class="thumbs" id="thumbs"></div>
        </div>

        <div style="display:flex;align-items:flex-end;gap:8px">
          <button id="btnSend" class="btn primary" style="width:120px;height:44px">Send</button>
          <button id="btnRunOCR" class="btn" title="Run OCR on attachments">Run OCR</button>
          <button id="btnClear" class="btn">Clear</button>
        </div>
      </div>
    </div>
  </div>
</div>

<div id="toast" class="toast"></div>

<script>
/* ---------------- Utils ---------------- */
const $  = (s)=>document.querySelector(s);
const $$ = (s)=>Array.from(document.querySelectorAll(s));
function toast(m,ms=2200){const t=$("#toast");t.textContent=m;t.classList.add("show");setTimeout(()=>t.classList.remove("show"),ms)}
function esc(s){return (s||"").replace(/&/g,"&amp;").replace(/</g,"&lt;")}
function now(){return new Date().toLocaleTimeString()}
function visionish(name){const n=(name||"").toLowerCase();return /vllm|vision|llava|bakllava|moondream|gpt-4o|llava\-phi|vl\-/.test(n)}
function firstJSONBlock(t){
  const fenced=t.match(/```json\s*([\s\S]*?)```/i); if(fenced){try{return JSON.parse(fenced[1])}catch{}}
  const i=t.indexOf("{"), j=t.lastIndexOf("}"); if(i!==-1&&j>i){try{return JSON.parse(t.slice(i,j+1))}catch{}}
  return null;
}
const PLACEHOLDER = 'data:image/svg+xml;utf8,'+encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="40" height="40"><rect width="40" height="40" rx="8" fill="#eef2ff"/></svg>');
const PDFICON = 'data:image/svg+xml;utf8,'+encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="40" height="40"><rect width="40" height="40" rx="8" fill="#fef2f2"/><text x="20" y="24" text-anchor="middle" font-size="11" fill="#991b1b">PDF</text></svg>');

/* ---------------- Field catalog ---------------- */
const FIELD_CATALOG = {
  header:["Kod","BaslangicTarihi","BitisTarihi","Aciklama","Bolum","Hash"],
  item:["Kod","MasrafTarihi","MasrafTuru","Butce","Tedarikci","Miktar","Birim","BirimMasrafTutari","KDVOrani","ToplamMasrafTutari","Aciklama"],
  file:["Kod","Adi","OrjinalAdi","Hash","MimeType","Size","Md5","EklenmeTarihi"]
};
const PRESETS = {
  typical:{ header:["BaslangicTarihi","BitisTarihi","Bolum"], item:["MasrafTarihi","MasrafTuru","Tedarikci","Miktar","BirimMasrafTutari","ToplamMasrafTutari"], file:["OrjinalAdi","MimeType","Size"] },
  all:{ header:[...FIELD_CATALOG.header], item:[...FIELD_CATALOG.item], file:[...FIELD_CATALOG.file] },
  none:{ header:[], item:[], file:[] }
};
let selectedFields = JSON.parse(localStorage.getItem("pruva.fields.v1")||"null") || PRESETS.typical;
function saveFields(){ localStorage.setItem("pruva.fields.v1", JSON.stringify(selectedFields)); }
function renderFieldGrid(){
  const mk=(id,arr,sel)=>{ const root=$(id); root.innerHTML="";
    arr.forEach(k=>{
      const lab=document.createElement("label");
      lab.style.display="flex"; lab.style.alignItems="center"; lab.style.gap="6px";
      lab.innerHTML=`<input type="checkbox" ${sel.includes(k)?"checked":""} data-k="${k}">${k}`;
      lab.querySelector("input").onchange=e=>{
        const list = id==="#fldHeader"?selectedFields.header: id==="#fldItem"?selectedFields.item:selectedFields.file;
        const i=list.indexOf(k); e.target.checked ? (i==-1 && list.push(k)) : (i!=-1 && list.splice(i,1));
        saveFields();
      };
      root.appendChild(lab);
    });
  };
  mk("#fldHeader", FIELD_CATALOG.header, selectedFields.header);
  mk("#fldItem", FIELD_CATALOG.item, selectedFields.item);
  mk("#fldFile", FIELD_CATALOG.file, selectedFields.file);
}
$$('#icFields [data-preset]').forEach(b=>b.onclick=(e)=>{ e.stopPropagation();
  selectedFields = JSON.parse(JSON.stringify(PRESETS[b.dataset.preset] || PRESETS.typical));
  saveFields(); renderFieldGrid(); toast("Preset applied: "+b.dataset.preset);
});

/* ---------------- State (workspaces/chats) ---------------- */
const STORE="pruva.ai.tree.v2";
function uid(){return Math.random().toString(36).slice(2,10)}
let state = JSON.parse(localStorage.getItem(STORE)||"null");
if(!state){
  const ws = uid(), ch = uid();
  state = { workspaces:{}, curWs:ws, curChat:ch };
  state.workspaces[ws] = {name:"Workspace 1", open:true, chats:{}};
  state.workspaces[ws].chats[ch] = {name:"Chat 1", system:"", messages:[]};
  localStorage.setItem(STORE, JSON.stringify(state));
}
function save(){ localStorage.setItem(STORE, JSON.stringify(state)); }
function cur(){ return state.workspaces[state.curWs].chats[state.curChat]; }

/* ---------------- Sidebar tree ---------------- */
function inlineRename(el, current, cb){
  const input=document.createElement("input"); input.value=current; input.className="inlineInput";
  el.innerHTML=""; el.appendChild(input); input.focus(); input.select();
  input.onkeydown=(e)=>{ if(e.key==="Enter"){ cb(input.value.trim()||current); } if(e.key==="Escape"){ cb(current,true); } };
  input.onblur=()=>cb(input.value.trim()||current);
}
function renderTree(){
  const T=$("#tree"); T.innerHTML="";
  Object.entries(state.workspaces).forEach(([wsId,ws])=>{
    const node=document.createElement("div"); node.className="node"+(ws.open?" open":"");
    node.innerHTML=`
      <div class="nodeHead">
        <div class="nodeTitle" data-rename="ws">${esc(ws.name)}</div>
        <span class="tag">${Object.keys(ws.chats).length} chats</span>
        <div class="nodeAct">
          <button class="btn" data-addchat>＋</button>
          <button class="btn" data-rename>✎</button>
          <button class="btn bad" data-del>🗑</button>
        </div>
      </div>
      <div class="nodeBody"></div>`;
    const head=node.querySelector(".nodeHead");
    head.onclick=(e)=>{ if(e.target.closest(".nodeAct")) return; ws.open=!ws.open; save(); renderTree(); };
    head.querySelector("[data-rename]").onclick=(e)=>{ e.stopPropagation(); inlineRename(node.querySelector('[data-rename="ws"]'), ws.name, (val,cancel)=>{ if(!cancel){ ws.name=val; save(); renderTree(); }}); };
    head.querySelector("[data-addchat]").onclick=(e)=>{ e.stopPropagation(); const id=uid(); ws.chats[id]={name:"Thread "+(Object.keys(ws.chats).length+1), system:"", messages:[]}; state.curWs=wsId; state.curChat=id; save(); renderAll(); };
    head.querySelector("[data-del]").onclick=(e)=>{ e.stopPropagation(); if(Object.keys(state.workspaces).length<=1) return toast("Keep at least one workspace"); if(confirm("Delete workspace?")){ delete state.workspaces[wsId]; state.curWs=Object.keys(state.workspaces)[0]; state.curChat=Object.keys(state.workspaces[state.curWs].chats)[0]; save(); renderAll(); } };

    const body=node.querySelector(".nodeBody");
    Object.entries(ws.chats).forEach(([chatId,ch])=>{
      const item=document.createElement("div"); item.className="item"+(state.curWs===wsId && state.curChat===chatId?" active":"");
      item.innerHTML=`<div style="flex:1" data-rename="chat">${esc(ch.name)}</div>
        <div class="controls">
          <button class="btn" data-rename>✎</button>
          <button class="btn bad" data-del>🗑</button>
        </div>`;
      item.onclick=(e)=>{ if(e.target.closest(".controls")) return; state.curWs=wsId; state.curChat=chatId; save(); renderAll(); };
      item.querySelector("[data-rename]").onclick=(e)=>{ e.stopPropagation(); inlineRename(item.querySelector('[data-rename="chat"]'), ch.name, (val,cancel)=>{ if(!cancel){ ch.name=val; save(); renderTree(); renderCrumb(); }}); };
      item.querySelector("[data-del]").onclick=(e)=>{ e.stopPropagation(); if(Object.keys(ws.chats).length<=1) return toast("Keep one chat at least"); if(confirm("Delete chat?")){ delete ws.chats[chatId]; state.curWs=wsId; state.curChat=Object.keys(ws.chats)[0]; save(); renderAll(); } };
      body.appendChild(item);
    });
    T.appendChild(node);
  });
}
$("#wsAdd").onclick=()=>{ const id=uid(); state.workspaces[id]={name:"Workspace "+(Object.keys(state.workspaces).length+1), open:true, chats:{}}; const ch=uid(); state.workspaces[id].chats[ch]={name:"Chat 1", system:"", messages:[]}; state.curWs=id; state.curChat=ch; save(); renderAll(); };
function renderCrumb(){ const ws=state.workspaces[state.curWs]; const ch=ws.chats[state.curChat]; $("#crumb").textContent=`${ws.name} / ${ch.name}`; }

/* ---------------- Thread ---------------- */
function bubble(role, text, opt={}){
  const b=document.createElement("div");
  b.className="bubble "+(role==="user"?"me":"ai");
  b.innerHTML=`
    <div class="meta"><b>${role==="user"?"You":"AI"}</b>
      ${opt.model?`<span class="chip mono">${esc(opt.model)}</span>`:""}
      <span class="small">${opt.time||now()}</span>
    </div>
    <div>${esc(text).replace(/\n/g,"<br>")}</div>
  `;
  if(opt.attach && opt.attach.length){
    const row=document.createElement("div"); row.className="attachRow";
    opt.attach.forEach(a=>{
      const chip=document.createElement("span"); chip.className="attach";
      const src = a.url || PLACEHOLDER;
      chip.innerHTML=`<img src="${src}" alt=""><span class="small">${esc(a.name||"file")}</span>`;
      row.appendChild(chip);
    });
    b.appendChild(row);
  }
  if(opt.extract){
    const det=document.createElement("details"); det.className="disc";
    det.innerHTML=`<summary>Extracted JSON</summary><pre class="json">${esc(JSON.stringify(opt.extract,null,2))}</pre>`;
    b.appendChild(det);
  }
  if(opt.raw){
    const det=document.createElement("details"); det.className="disc";
    det.innerHTML=`<summary>Model raw</summary><pre class="json">${esc(JSON.stringify(opt.raw,null,2))}</pre>`;
    b.appendChild(det);
  }
  return b;
}
function renderThread(){
  const t=$("#thread"); t.innerHTML="";
  (cur().messages||[]).forEach(m=>{
    const atts=(m.attach||[]).map(a=>({url:a.url,name:a.name}));
    t.appendChild(bubble(m.role, m.content||"", {model:m.model, time:m.time, attach:atts, extract:m.extract, raw:m.raw}));
  });
  t.scrollTop=t.scrollHeight;
}

/* ---------------- Models ---------------- */
async function reloadModels(){
  const sel=$("#modelSel"); sel.innerHTML=`<option>Loading…</option>`;
  try{
    const js=await (await fetch("/api/llm/models")).json();
    sel.innerHTML=""; (js.models||[]).forEach(m=>{ const o=document.createElement("option"); o.value=m.name; o.textContent=m.name; sel.appendChild(o); });
  }catch{ sel.innerHTML=`<option value="">(no models)</option>`; }
}
$("#btnExportChat").onclick=()=>{ const ws=state.workspaces[state.curWs], ch=ws.chats[state.curChat]; const data=JSON.stringify(ch,null,2); const url=URL.createObjectURL(new Blob([data],{type:"application/json"})); const a=document.createElement("a"); a.href=url; a.download=`${ws.name}__${ch.name}.json`; a.click(); URL.revokeObjectURL(url); };
$("#btnClearChat").onclick=()=>{ if(confirm("Clear this chat?")){ cur().messages=[]; save(); renderThread(); } };

/* ---------------- Icons popups ---------------- */
function togglePop(ic){ ic.classList.toggle("open"); }
$("#icFields").addEventListener("click",(e)=>{ if(e.target.closest(".pop")) return; togglePop($("#icFields")); });
$("#icSys").addEventListener("click",(e)=>{ if(e.target.closest(".pop")) return; togglePop($("#icSys")); });
$("#icHelp").addEventListener("click",(e)=>{ if(e.target.closest(".pop")) return; togglePop($("#icHelp")); });
$("#icDataset").addEventListener("click",(e)=>{ if(e.target.closest(".pop")) return; togglePop($("#icDataset")); });
document.addEventListener("click",(e)=>{ [$("#icFields"),$("#icSys"),$("#icHelp"),$("#icDataset")].forEach(ic=>{ if(ic && !ic.contains(e.target)) ic.classList.remove("open"); }); });

renderFieldGrid();

/* ---------------- Attachments: local files ---------------- */
let staged=[], stagedUrls=[];
function refreshThumbs(){
  const wrap=$("#thumbs"); wrap.innerHTML="";
  // local uploads
  stagedUrls.forEach((u,i)=>{
    const d=document.createElement("div"); d.className="thumb";
    d.innerHTML=`<img src="${u}" alt=""><button class="x">×</button>`;
    d.querySelector(".x").onclick=()=>{ URL.revokeObjectURL(stagedUrls[i]); staged.splice(i,1); stagedUrls.splice(i,1); refreshThumbs(); };
    wrap.appendChild(d);
  });
  // dataset picks
  DATASET.selected.forEach((ref, idx)=>{
    const url = previewURL(ref) || (isPDF(ref.type)?PDFICON:PLACEHOLDER);
    const d=document.createElement("div"); d.className="thumb"; d.innerHTML=`<img src="${url}" alt=""><button class="x">×</button>`;
    d.title = ref.name || ref.key;
    d.querySelector(".x").onclick=()=>{ DATASET.selected.splice(idx,1); refreshThumbs(); };
    wrap.appendChild(d);
  });
}
$("#filePick").onchange=e=>{ const files=[...e.target.files]; files.forEach(f=>{ staged.push(f); stagedUrls.push(URL.createObjectURL(f)); }); e.target.value=""; refreshThumbs(); };
const dz=$("#dropzone");
["dragenter","dragover"].forEach(ev=>dz.addEventListener(ev,e=>{e.preventDefault();dz.style.outline="2px dashed #a3bffa"}));
["dragleave","drop"].forEach(ev=>dz.addEventListener(ev,e=>{e.preventDefault();dz.style.outline="none"}));
dz.addEventListener("drop",e=>{ const files=[...e.dataTransfer.files]; files.forEach(f=>{ staged.push(f); stagedUrls.push(URL.createObjectURL(f)); }); refreshThumbs(); });
async function uploadStaged(sessionId){
  if(!staged.length) return [];
  const fd=new FormData(); fd.append("session_id", sessionId);
  staged.forEach(f=>fd.append("files", f));
  try{
    const r=await fetch("/api/llm/upload",{method:"POST",body:fd});
    const js=await r.json(); if(!r.ok||js.error) throw 0;
    return (js.files||[]); 
  }catch{ toast("Upload failed"); return []; }
}

/* ---------------- Dataset picker ---------------- */
const DATASET = { list:[], selected:[] }; // flat *files* with expense context
let LAST_DS_RAW = null;

function showDsRaw(raw){
  LAST_DS_RAW = raw;
  $("#dsRaw").textContent = typeof raw==='string' ? raw : JSON.stringify(raw,null,2);
  $("#dsRawWrap").style.display = 'block';
}

/* ---------- Expense→Files expansion layer ---------- */
function looksLikeExpense(o){
  if(!o || typeof o!=="object") return false;
  const hasExpenseish = ("Kod" in o) || ("Tedarikci" in o) || ("MasrafTarihi" in o) || ("internal_detail" in o);
  const hasFileish = o?.internal_detail?.MasrafAlt || o?.Files || o?.files || o?.images || o?.attachments;
  return hasExpenseish && !hasFileish;
}
function getExpenseId(o){
  return o?.Kod || o?.kod || o?.id || o?.Id || o?._id || o?.uuid || o?.Hash || o?.hash || o?.Code || "";
}

async function fetchFilesForExpense(exp){
  // embedded?
  const embed = exp?.internal_detail?.MasrafAlt;
  if (embed && typeof embed==="object"){
    const out=[];
    Object.values(embed).forEach(alt=>{
      const dos=alt.Dosya||alt.Files||alt.files||alt.images;
      if(Array.isArray(dos)) out.push(...dos);
      else if(dos && typeof dos==="object") out.push(...Object.values(dos));
    });
    if(out.length) return out;
  }
  const id=getExpenseId(exp);
  const q=encodeURIComponent(id);

  // preferred: get the full expense like your Data Source page
  const fullCandidates = [
    `/api/expense/${q}`,
    `/api/expense?kod=${q}`,
    `/api/expense?id=${q}`
  ];
  for(const u of fullCandidates){
    try{
      const r=await fetch(u);
      if(!r.ok) continue;
      const js=await r.json().catch(()=>null);
      if(js && js.internal_detail && js.internal_detail.MasrafAlt){
        const acc=[];
        Object.values(js.internal_detail.MasrafAlt).forEach(alt=>{
          const f=alt.Dosya||alt.Files||alt.files||alt.images;
          if(Array.isArray(f)) acc.push(...f);
          else if(f && typeof f==="object") acc.push(...Object.values(f));
        });
        if(acc.length) return acc;
      }
    }catch{}
  }

  // fallbacks: explicit file lists
  const getCandidates = [
    `/api/dataset/expense_files?kod=${q}`,
    `/api/dataset/expense_files?id=${q}`,
    `/api/dataset/files?expense_id=${q}`,
    `/api/dataset/files?Kod=${q}`,
    `/api/expense/${q}/files`,
    `/api/expenses/${q}/files`,
    `/api/expense_files?expense_id=${q}`
  ];
  for(const url of getCandidates){
    try{
      const r=await fetch(url);
      if(!r.ok) continue;
      const js=await r.json().catch(()=>null);
      const arr = Array.isArray(js) ? js : (js?.files || js?.items || js?.data || js?.results);
      if (Array.isArray(arr) && arr.length) return arr;
    }catch{}
  }

  // POST fallbacks accepting payloads (some gateways expect POST)
  const postCandidates = [
    {url:'/api/dataset/expense_files', data:{expense:exp}},
    {url:'/api/expense_files', data:{expense:exp}},
  ];
  for(const c of postCandidates){
    try{
      const r=await fetch(c.url,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(c.data)});
      if(!r.ok) continue;
      const js=await r.json().catch(()=>null);
      const arr = Array.isArray(js) ? js : (js?.files || js?.items || js?.data || js?.results);
      if (Array.isArray(arr) && arr.length) return arr;
    }catch{}
  }

  return [];
}

/* ---------------- Normalization ---------------- */
function isPDF(mt){ return (mt||"").toLowerCase().includes("pdf") || /\.pdf$/i.test(mt||""); }
function isImageType(mtOrName){ const s=(mtOrName||"").toLowerCase(); return s.startsWith("image/") || /\.(png|jpe?g|webp|gif)$/.test(s); }

function previewURL(row){
  // synthesize preview url from FileId/Hash if present (your /api/preview flow)
  const f = row?.meta?.file || {};
  const ctx = row?.meta?.context || {};
  if ((f.FileId || f.fileId || f.fid) && (f.FileHash || f.fileHash || f.Hash) && (ctx.Kod || ctx.kod)){
    const fid = f.FileId || f.fileId || f.fid;
    const fh  = f.FileHash || f.fileHash || f.Hash;
    const kod = ctx.Kod || ctx.kod;
    return `/api/preview?kod=${encodeURIComponent(kod)}&fid=${encodeURIComponent(fid)}&hash=${encodeURIComponent(fh)}`;
  }
  const direct = f.signed_url || f.SignedUrl || f.url || f.Url || f.public_url || f.preview_url || row.url;
  if (direct) return direct;
  if (typeof row.key === "string" && /^https?:/i.test(row.key)) return row.key;
  const key = encodeURIComponent(row.key||"");
  if (!key) return "";
  return `/api/dataset/preview?key=${key}`;
}

function normalizeFileRow(file, expenseCtx={}){
  const key = file.s3_key_image || file.s3_key || file.S3Key || file.s3Path || file.S3Path || file.fileHash || file.Hash || file.Kod || file.path || file.key || file.url || file.Url || (file.FileId && file.FileHash ? `${expenseCtx?.Kod||''}:${file.FileId}:${file.FileHash}` : "");
  if(!key) return null;
  const name = file.OrjinalAdi || file.Adi || file.original || file.name || file.FileName || (expenseCtx?.Tedarikci?`${expenseCtx.Tedarikci}-${(file.Kod||file.Hash||file.FileHash||'file')}`:'file');
  const guessFromName = /\.(pdf)$/i.test(String(name)) ? "application/pdf" : (isImageType(name) ? "image/*" : "file");
  const type = (file.MimeType || file.mime || file.content_type || "").toLowerCase() || guessFromName;
  const row = {
    key,
    name,
    type,
    size: file.Size || file.size_bytes || file.FileSize || 0,
    url: file.url || file.signed_url || file.SignedUrl || file.preview_url || "",
    meta: { file, context: expenseCtx }
  };
  // attach preview if we can synthesize
  const p = previewURL(row);
  if (p) row.url = p;
  return row;
}

// First pass: flatten any embedded files, record "expenses missing files"
function normalizeFirstPass(input){
  const fileRows=[];
  const expenseRows=[];
  const pushFile=(row)=>{ if(row && row.key) fileRows.push(row); };

  const takeFilesArray=(arr, ctx)=>{ if(Array.isArray(arr)) arr.forEach(f=>pushFile(normalizeFileRow(f, ctx||{}))); };

  const walkExpense=(exp)=>{
    const ctx=(exp?.internal_detail?.masraf || exp?.masraf || {});
    if (exp?.Kod && !ctx.Kod) ctx.Kod = exp.Kod; // ensure Kod is present in ctx for preview urls

    const MasrafAlt = exp?.internal_detail?.MasrafAlt;
    if(MasrafAlt && typeof MasrafAlt==="object"){
      Object.values(MasrafAlt).forEach(alt=>{
        const files = alt.Dosya || alt.Files || alt.files || alt.images;
        if (Array.isArray(files)) files.forEach(f=>pushFile(normalizeFileRow(f, {...ctx, ...alt})));
        else if (files && typeof files==="object"){ Object.values(files).forEach(f=>pushFile(normalizeFileRow(f, {...ctx, ...alt}))); }
      });
    }
    takeFilesArray(exp?.Files, ctx);
    takeFilesArray(exp?.files, ctx);
    takeFilesArray(exp?.images, ctx);
    takeFilesArray(exp?.attachments, ctx);

    if(!(MasrafAlt||exp?.Files||exp?.files||exp?.images||exp?.attachments)) expenseRows.push(exp);
  };

  const tryArray=(arr)=>{
    if(!Array.isArray(arr)) return false;
    arr.forEach(it=>{
      if(looksLikeExpense(it) || it?.internal_detail?.MasrafAlt || it?.Files || it?.files || it?.images || it?.attachments) walkExpense(it);
      else if(it?.Dosya || it?.OrjinalAdi || it?.S3Key || it?.s3_key_image || it?.key || it?.path || it?.url || it?.FileId){ pushFile(normalizeFileRow(it, {})); }
    });
    return true;
  };

  if(tryArray(input)) return {fileRows, expenseRows};
  const maybeArr = input?.items || input?.data || input?.results || input?.expenses || input?.files || input?.Files;
  if(tryArray(maybeArr)) return {fileRows, expenseRows};

  if(input && typeof input==="object"){
    if(looksLikeExpense(input) || input.internal_detail?.MasrafAlt || input.Files || input.files || input.images || input.attachments){ walkExpense(input); }
    else if(input.Dosya || input.OrjinalAdi || input.S3Key || input.s3_key_image || input.key || input.path || input.url || input.FileId){ pushFile(normalizeFileRow(input, {})); }
  }
  return {fileRows, expenseRows};
}

/* ---------- Load from API then EXPAND expenses to files ---------- */
async function fetchDatasetFlexible(){
  const paths = ["/api/dataset/list","/api/dataset","/api/dataset/items","/api/expenses"];
  let lastErr=null;
  for(const p of paths){
    try{
      const r=await fetch(p);
      const txt=await r.text();
      if(!r.ok) { lastErr=txt||r.status; continue; }
      try{
        const js=JSON.parse(txt); showDsRaw(js); return js;
      }catch{
        const lines=txt.split(/\r?\n/).map(s=>s.trim()).filter(Boolean);
        const arr=[]; for(const ln of lines){ try{ arr.push(JSON.parse(ln)); }catch{} }
        if(arr.length){ showDsRaw(arr); return arr; }
        showDsRaw(txt); return txt;
      }
    }catch(e){ lastErr=e; }
  }
  toast("Dataset API not available ("+(lastErr||"no response")+")");
  showDsRaw(String(lastErr||""));
  return null;
}

function groupKey(ctx){
  return String(ctx?.Kod || ctx?.MasrafTarihi || ctx?.Tedarikci || ctx?.Aciklama || "Expense");
}
function groupTitle(ctx){
  const parts=[ctx?.Tedarikci||"Expense", ctx?.MasrafTarihi, ctx?.ToplamMasrafTutari].filter(Boolean);
  return parts.join(" · ");
}

function renderDatasetList(){
  const box=$("#dsList"); box.innerHTML="";
  if(!DATASET.list.length){ box.innerHTML=`<div class="small" style="padding:6px">No items yet. Click “Load from API” or paste JSON.</div>`; return; }

  const groups={};
  DATASET.list.forEach(r=>{
    const ctx=r.meta?.context||{};
    const gid=groupKey(ctx);
    (groups[gid]=groups[gid]||{ctx, items:[]}).items.push(r);
  });

  Object.entries(groups).forEach(([gid,g])=>{
    const wrap=document.createElement("div");
    wrap.style.border="1px solid var(--line)"; wrap.style.borderRadius="10px"; wrap.style.margin="6px 0"; wrap.style.overflow="hidden";

    const head=document.createElement("div");
    head.style.display="grid"; head.style.gridTemplateColumns="auto 1fr auto"; head.style.gap="8px"; head.style.alignItems="center";
    head.style.padding="6px"; head.style.background="#f8fafc";
    head.innerHTML=`<input type="checkbox" data-gid="${gid}"><b>${esc(groupTitle(g.ctx))}</b><span class="small">${g.items.length} file(s)</span>`;
    head.querySelector("input").onchange=(e)=>{
      const checked=e.target.checked;
      $$(`#dsList input[type="checkbox"][data-g="${gid}"]`).forEach(cb=>{ cb.checked=checked; });
    };
    wrap.appendChild(head);

    g.items.forEach((r,i)=>{
      const row=document.createElement("label");
      row.style.display="grid"; row.style.gridTemplateColumns="auto auto 1fr auto"; row.style.gap="10px"; row.style.alignItems="center"; row.style.padding="6px"; row.style.borderTop="1px solid var(--line)";
      const purl = isPDF(r.type) ? PDFICON : (previewURL(r) || PLACEHOLDER);
      row.innerHTML=`<input type="checkbox" data-g="${gid}" data-i="${i}">
        <div class="preview"><img src="${purl}" alt="" onerror="this.src='${PLACEHOLDER}'"></div>
        <div><b>${esc(r.name||r.key)}</b><div class="small mono">${esc(r.key)}</div></div>
        <span class="tag">${esc(r.type||"file")}</span>`;
      wrap.appendChild(row);
    });

    box.appendChild(wrap);
  });
}

$("#btnApplyDataset").onclick=(e)=>{
  e.stopPropagation();

  const groupsIdx={};
  DATASET.list.forEach(r=>{
    const gid=groupKey(r.meta?.context||{});
    (groupsIdx[gid]=groupsIdx[gid]||[]).push(r);
  });

  const whole = $$('#dsList input[type="checkbox"][data-gid]:checked').map(cb => cb.getAttribute('data-gid'));
  const files = $$('#dsList input[type="checkbox"][data-i]:checked').map(cb => ({ gid: cb.getAttribute('data-g'), idx: Number(cb.getAttribute('data-i')) }));

  const pickedRows = new Map();
  whole.forEach(gid=>{ (groupsIdx[gid]||[]).forEach(r=>pickedRows.set(r.key,r)); });
  files.forEach(sel=>{ const r=(groupsIdx[sel.gid]||[])[sel.idx]; if(r) pickedRows.set(r.key,r); });

  if(!pickedRows.size){ toast("Nothing selected"); return; }

  const already = new Set(DATASET.selected.map(x=>x.key));
  let added=0;
  pickedRows.forEach(r=>{
    if(!already.has(r.key)){
      DATASET.selected.push({key:r.key, name:r.name||r.key, type:r.type, url: previewURL(r)});
      added++;
    }
  });

  refreshThumbs();
  toast(`${added} file(s) added from ${whole.length} expense(s)`);
};

async function loadDatasetFromAPI(){
  $("#dsList").innerHTML=`<div class="small" style="padding:6px">Loading…</div>`;
  const raw = await fetchDatasetFlexible();
  if(raw==null){ DATASET.list=[]; renderDatasetList(); return; }

  const {fileRows, expenseRows} = normalizeFirstPass(raw);

  let expandedFiles=[];
  if(expenseRows.length){
    const results = await Promise.allSettled(
      expenseRows.map(async exp=>{
        const ctx = exp?.internal_detail?.masraf || exp?.masraf || {};
        if (exp?.Kod && !ctx.Kod) ctx.Kod = exp.Kod;
        const files = await fetchFilesForExpense(exp);
        return files.map(f=>normalizeFileRow(f, ctx)).filter(Boolean);
      })
    );
    results.forEach(r=>{ if(r.status==="fulfilled" && Array.isArray(r.value)) expandedFiles.push(...r.value); });
  }

  DATASET.list = [...fileRows, ...expandedFiles];

  if(!DATASET.list.length){
    toast("Loaded but no files found. Check the raw payload and file endpoints (debug below).");
  }else{
    toast(`Loaded ${DATASET.list.length} file(s) from ${expenseRows.length} expense(s)`);
  }
  renderDatasetList();
}
$("#btnLoadDataset").onclick=(e)=>{ e.stopPropagation(); loadDatasetFromAPI(); };

$("#btnParseJson").onclick=(e)=>{
  e.stopPropagation();
  const txt=$("#dsJson").value.trim();
  if(!txt) return toast("Paste JSON first");
  try{
    const obj=JSON.parse(txt);
    showDsRaw(obj);
    const first = normalizeFirstPass(obj);
    DATASET.list = [...first.fileRows];
    renderDatasetList(); toast(`Parsed ${DATASET.list.length} file(s)`);
  }catch{ toast("Invalid JSON"); }
};

/* ---------------- OCR ---------------- */
async function runOCRPreview(){
  if(!staged.length && !DATASET.selected.length) return toast("Attach files first");
  const fd=new FormData();
  staged.forEach(f=>fd.append("files", f));
  if(DATASET.selected.length){ fd.append("dataset_keys", JSON.stringify(DATASET.selected.map(x=>x.key))); }
  $("#status").style.display="inline-flex";
  try{
    const r=await fetch("/api/ocr/extract",{method:"POST",body:fd});
    const js=await r.json().catch(()=>null);
    $("#status").style.display="none";
    if(!r.ok||!js){ addMsg("assistant","(OCR error)"); return; }
    addMsg("assistant", js.text || "(OCR done)", {raw:js});
  }catch{ $("#status").style.display="none"; addMsg("assistant","(network error)"); }
}
$("#btnRunOCR").onclick=runOCRPreview;

/* ---------------- DATASET → IMAGE TOKENS (for VLLM etc.) ---------------- */
async function resolveImageUrlsForRef(ref){
  const f = ref?.meta?.file || {};
  const ctx = ref?.meta?.context || {};
  if ((f.FileId||f.fileId||f.fid) && (f.FileHash||f.fileHash||f.Hash) && (ctx.Kod||ctx.kod)){
    const fid = f.FileId || f.fileId || f.fid;
    const fh  = f.FileHash || f.fileHash || f.Hash;
    const kod = ctx.Kod || ctx.kod;
    // ask preview service to render all pages if PDF
    return [`/api/preview?kod=${encodeURIComponent(kod)}&fid=${encodeURIComponent(fid)}&hash=${encodeURIComponent(fh)}&all=1`];
  }
  const key = encodeURIComponent(ref.key||"");
  const candidatesJSON = [
    `/api/dataset/images?key=${key}`,
    `/api/dataset/preview?key=${key}&all=1`,
    `/api/dataset/pages?key=${key}`
  ];
  for(const u of candidatesJSON){
    try{
      const r = await fetch(u);
      if(!r.ok) continue;
      const js = await r.json().catch(()=>null);
      if(js && Array.isArray(js.images) && js.images.length) return js.images;
    }catch{}
  }
  if (ref.url && isImageType(ref.url)) return [ref.url];
  if (isImageType(ref.type) || isImageType(ref.name) ){
    return [`/api/dataset/file?key=${key}`];
  }
  return [`/api/dataset/preview?key=${key}`];
}
async function fetchAsFile(url, filenameFallback){
  const r = await fetch(url);
  if(!r.ok) throw new Error("fetch fail");
  const blob = await r.blob();
  let name = filenameFallback;
  const ct = (r.headers.get("content-type")||"").toLowerCase();
  if(ct.startsWith("image/")){
    const ext = ct.split("/")[1].split(";")[0] || "jpg";
    if(!/\.(png|jpe?g|webp|gif)$/i.test(name)) name = name.replace(/\.[^\.]+$/,"")+"."+ext;
  }
  return new File([blob], name, {type: ct || "image/jpeg"});
}
async function datasetSelectedToImageTokens(sessionId){
  if(!DATASET.selected.length) return [];
  const filesToUpload = [];
  for(const ref of DATASET.selected){
    try{
      const urls = await resolveImageUrlsForRef(ref);
      let page = 0;
      for(const u of urls){
        page++;
        const safeNameBase = (ref.name || ref.key || "file").replace(/[^\w.\-]+/g,"_");
        const f = await fetchAsFile(u, `${safeNameBase}_${page}.jpg`);
        filesToUpload.push(f);
      }
    }catch(e){}
  }
  if(!filesToUpload.length) return [];
  const fd = new FormData();
  fd.append("session_id", sessionId);
  filesToUpload.forEach(f=>fd.append("files", f));
  try{
    const r=await fetch("/api/llm/upload",{method:"POST",body:fd});
    const js=await r.json();
    if(!r.ok || js.error) throw 0;
    return (js.files||[]).map(x=>x.token);
  }catch{
    toast("Failed to materialize dataset files as images");
    return [];
  }
}

/* ---------------- Send ---------------- */
function addMsg(role, content, extras={}){
  const m={role, content, time:now(), ...extras};
  cur().messages=cur().messages||[]; cur().messages.push(m); save(); renderThread();
}
function keySend(e){ if(e.key==="Enter" && !e.shiftKey){ e.preventDefault(); $("#btnSend").click(); } }
$("#msgBox").addEventListener("keydown", keySend);

async function send(){
  const text=$("#msgBox").value.trim();
  const model=$("#modelSel").value||"";
  const wantOCR=$("#chkOcr").checked;
  if(!text && !staged.length && !DATASET.selected.length) return;

  const ws=state.workspaces[state.curWs], ch=ws.chats[state.curChat];
  const sessionId = `${ws.name} — ${ch.name}`;

  const userAttach = [
    ...stagedUrls.map((u,i)=>({url:u,name:staged[i].name})),
    ...DATASET.selected.map(ref=>({url:ref.url||'',name:ref.name||ref.key}))
  ];
  addMsg("user", text, {attach:userAttach});

  const isVision=visionish(model);
  if(!isVision && wantOCR && (staged.length || DATASET.selected.length)){ await runOCRPreview(); }

  let tokens = [];
  if(isVision){
    if(staged.length){ const ups = await uploadStaged(sessionId); tokens = tokens.concat(ups.map(x=>x.token)); }
    if(DATASET.selected.length){
      const tok2 = await datasetSelectedToImageTokens(sessionId);
      tokens = tokens.concat(tok2);
    }
  }

  $("#msgBox").value="";
  staged.forEach((_,i)=>URL.revokeObjectURL(stagedUrls[i]));
  staged=[]; stagedUrls=[]; refreshThumbs();

  const system=(ch.system||$("#sysPrompt").value||"").trim(); ch.system=system; save();

  const enforced="You are a helpful assistant. Reply in English. "+(system||"");
  const msgs=(ch.messages||[]).filter(m=>m.role==="user"||m.role==="assistant").map(m=>({role:m.role,content:m.content||"",image_tokens:[]}));
  if(isVision && tokens.length) msgs[msgs.length-1].image_tokens=tokens;

  const dedup = Array.from(new Set(DATASET.selected.map(x=>x.key)));
  const payload={ session_id: sessionId, model, system: enforced, messages: msgs, fields: selectedFields };
  if(dedup.length) payload.dataset_keys = dedup;

  $("#status").style.display="inline-flex";
  try{
    const r=await fetch("/api/llm/chat",{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify(payload)});
    const js=await r.json().catch(()=>({}));
    $("#status").style.display="none";
    if(!r.ok||js.error){ addMsg("assistant","(error) "+(js.error||r.status)); return; }
    const reply=js.reply||""; const extract=firstJSONBlock(reply);
    addMsg("assistant", reply, {extract, raw:js.raw||null, model});
  }catch{ $("#status").style.display="none"; addMsg("assistant","(network error)"); }
}
$("#btnSend").onclick=send;
$("#btnClear").onclick=()=>{$("#msgBox").value="";};

/* ---------------- Back button ---------------- */
$("#btnBack").onclick=()=>{
  try{ if (document.referrer && !document.referrer.includes("/ai_chat")) { history.back(); return; } }catch{}
  window.location.href = "/ui";
};

/* ---------------- Boot ---------------- */
function renderAll(){ renderTree(); renderCrumb(); renderThread(); }
document.addEventListener("DOMContentLoaded", async()=>{
  renderAll();
  await reloadModels();
  renderFieldGrid();
});
</script>
</body>
</html>
"""
