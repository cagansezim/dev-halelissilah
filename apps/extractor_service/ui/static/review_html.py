HTML = r"""<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Review {{RID}}</title>
  <style>
    body { font-family: ui-sans-serif, system-ui, -apple-system; margin: 24px; }
    .wrap { max-width: 980px; margin: 0 auto; }
    textarea, input { width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 8px; }
    button { padding: 8px 14px; border-radius: 8px; border: 0; background: #111; color: #fff; }
    .row { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
    .box { border: 1px solid #eee; padding: 12px; border-radius: 10px; }
  </style>
</head>
<body>
<div class="wrap">
  <h2>Review: {{RID}}</h2>
  <p>Use your admin UI for full controls; or submit quick corrections below.</p>
  <div class="box">
    <label>Corrections (JSON):</label>
    <textarea id="corr" rows="8">{ "Masraf": { "Aciklama": "" } }</textarea>
    <label style="margin-top:10px;">Instructions (optional):</label>
    <input id="inst" placeholder="Örn: Toplamı imzalı bölümden al." />
    <div style="margin-top:12px;">
      <button onclick="send()">Send</button>
      <span id="msg"></span>
    </div>
  </div>
</div>
<script>
async function send(){
  const rid = "{{RID}}";
  const corr = document.getElementById('corr').value;
  const inst = document.getElementById('inst').value;
  try {
    const body = { corrections: JSON.parse(corr||"{}"), instructions: inst||null };
    const r = await fetch(`/extractor/requests/${rid}/retry`, {method:'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(body)});
    const j = await r.json();
    document.getElementById('msg').textContent = j.ok ? 'Saved.' : 'Failed.';
  } catch(e) {
    document.getElementById('msg').textContent = 'Invalid JSON';
  }
}
</script>
</body>
</html>"""
