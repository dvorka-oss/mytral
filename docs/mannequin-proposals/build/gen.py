import json
FRONT=open('front.frag').read(); BACK=open('back.frag').read()
O=json.load(open('outline.json')); OUTF=O['front']; OUTB=O['back']
OUTDIR='/home/dvorka/p/mytral/git/mytral/docs/mannequin-proposals/'
Q='&#39;'

def geo(defs_inner):
    return ('    <div class="figs" id="figs">\n'
      '      <div class="fig"><div class="fig-label">Front</div>\n'
      '        <svg class="body" viewBox="0 0 724 1448" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Body front">\n'
      f'          <defs>{defs_inner}</defs>\n          <path class="outline" d="{OUTF}"/>\n{FRONT}\n        </svg></div>\n'
      '      <div class="fig"><div class="fig-label">Back</div>\n'
      '        <svg class="body" viewBox="724 0 724 1448" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Body back">\n'
      f'          <path class="outline" d="{OUTB}"/>\n{BACK}\n        </svg></div>\n    </div>')

GRAD_RED=('\n<radialGradient id="red" cx="42%" cy="30%" r="80%"><stop offset="0" stop-color="#f3a0a8"/><stop offset=".45" stop-color="#e2515f"/><stop offset="1" stop-color="#bf2e3a"/></radialGradient>'
          '\n<radialGradient id="inj" cx="45%" cy="32%" r="80%"><stop offset="0" stop-color="#ff8f96"/><stop offset=".5" stop-color="#e5242f"/><stop offset="1" stop-color="#a3121c"/></radialGradient>')
HS=[("h1","#6fb6e6","#2f86c5"),("h2","#5fd6bf","#1aa589"),("h3","#c4ea7e","#86c12f"),("h4","#ffd778","#e9aa12"),("h5","#ff9a6e","#e2541f"),("h6","#ff7d8c","#cf2336")]
GRAD_HEAT='\n'+'\n'.join(f'<radialGradient id="{i}" cx="42%" cy="30%" r="82%"><stop offset="0" stop-color="{a}"/><stop offset="1" stop-color="{b}"/></radialGradient>' for i,a,b in HS)+'\n<radialGradient id="inj" cx="45%" cy="32%" r="80%"><stop offset="0" stop-color="#ff8f96"/><stop offset=".5" stop-color="#e5242f"/><stop offset="1" stop-color="#a3121c"/></radialGradient>'
GRAD_PICK=('\n<radialGradient id="grn" cx="42%" cy="30%" r="82%"><stop offset="0" stop-color="#7fd99a"/><stop offset="1" stop-color="#2fa353"/></radialGradient>'
           '\n<radialGradient id="amb" cx="42%" cy="30%" r="82%"><stop offset="0" stop-color="#ffd27a"/><stop offset="1" stop-color="#e09a16"/></radialGradient>')

HEAD=('<!doctype html>\n<!-- MyTraL mannequin v3 — realistic anatomy adapted from MIT react-native-body-highlighter -->\n'
'<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">\n'
'<title>__TITLE__</title><style>__STYLE__</style></head><body>\n<div class="page">\n'
'  <span class="tag">__TAG__</span>\n  <h1>__H1__</h1>\n  <p class="sub">__SUB__</p>\n  <div class="card">\n'
'    <div class="card-head"><div class="card-title" id="title">__CARDTITLE__</div>\n'
'      <div class="controls">__CONTROLS__</div></div>\n__GEO__\n__BELOW__\n  </div>\n'
'  <p class="note">__NOTE__</p>\n</div>\n<div id="tip"></div>\n<script>__SCRIPT__</script>\n</body></html>')

COMMON_CSS='''
  *{box-sizing:border-box}
  .page{max-width:760px;margin:0 auto;padding:30px 20px 60px}
  h1{font-size:1.34rem;margin:0 0 2px} .sub{color:var(--muted);font-size:.9rem;margin:0 0 20px}
  .card-head{display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap;margin-bottom:6px}
  .card-title{font-weight:650;font-size:1.04rem} .controls{display:flex;gap:8px;flex-wrap:wrap}
  .figs{display:flex;gap:2px;justify-content:center;flex-wrap:wrap;margin-top:8px;position:relative}
  .fig{flex:1 1 0;min-width:215px;max-width:300px;text-align:center}
  .fig-label{font-size:.72rem;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);margin-bottom:2px}
  svg.body{width:100%;height:auto;display:block;overflow:visible}
  .legend{display:flex;gap:16px;flex-wrap:wrap;justify-content:center;margin-top:14px;font-size:.8rem;color:var(--muted)}
  .legend i{display:inline-block;width:13px;height:13px;border-radius:3px;vertical-align:-2px;margin-right:5px}
  .note{color:var(--muted);font-size:.82rem;margin-top:20px;line-height:1.55}
  #tip{position:fixed;pointer-events:none;font-size:.76rem;padding:5px 9px;border-radius:7px;transform:translate(-50%,-130%);opacity:0;transition:opacity .12s;white-space:nowrap;z-index:9}
  #tip.on{opacity:1}'''

TIP_JS='''
const tip=document.getElementById("tip"),figs=document.getElementById("figs");
figs.addEventListener("mousemove",function(e){var el=e.target.closest("[data-name]");
 if(el){tip.textContent=el.dataset.name;tip.classList.add("on");tip.style.left=e.clientX+"px";tip.style.top=e.clientY+"px";}else tip.classList.remove("on");});
figs.addEventListener("mouseleave",function(){tip.classList.remove("on");});'''
KEYS='["pecs","shoulders","biceps","triceps","forearms","abs","obliques","traps","lats","lower_back","glutes","quads","hamstrings","calves","neck","hip_flexors"]'

def write(fn,**kw):
    h=HEAD
    for k,v in kw.items(): h=h.replace('__'+k+'__',v)
    open(OUTDIR+fn,'w').write(h); print("wrote",fn,len(h),"bytes")

# ---------- Proposal 1: Atlas (light) ----------
write('proposal-1-anatomical-atlas.html',
 TITLE='MyTraL Mannequin v3 — Anatomical Atlas', TAG='Proposal 1 · Anatomical Atlas',
 H1='Realistic anatomical muscle map — pure SVG',
 SUB='Real anatomical muscle paths on a grey silhouette. Muscles light up by data; hover for a name. Reload / Randomize for new data.',
 CARDTITLE='Muscles worked — last 7 days',
 CONTROLS=f'<button id="btnLoad" class="active" onclick="setMode({Q}load{Q})">Muscle load</button><button id="btnInjury" onclick="setMode({Q}injury{Q})">Injury</button><button onclick="randomize()">Randomize ⟳</button>',
 STYLE=COMMON_CSS+'''
  :root{--bg:#f6f8fb;--card:#fff;--ink:#1d2733;--muted:#6b7785;--line:#e3e8ef}
  body{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Roboto,sans-serif;background:var(--bg);color:var(--ink)}
  .tag{display:inline-block;font-size:.7rem;letter-spacing:.09em;text-transform:uppercase;color:#a8202f;background:#fde8ea;border:1px solid #f6c9ce;border-radius:99px;padding:2px 10px;margin-bottom:12px}
  .card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:22px;box-shadow:0 1px 2px rgba(16,24,40,.04),0 10px 28px rgba(16,24,40,.06)}
  button{font:inherit;font-size:.83rem;border:1px solid var(--line);background:#fff;color:var(--ink);border-radius:9px;padding:6px 12px;cursor:pointer}
  button:hover{border-color:#c3ccd8} button.active{background:var(--ink);color:#fff;border-color:var(--ink)}
  .outline{fill:#cdd6e1;stroke:#aeb9c7;stroke-width:2}
  .silh{fill:#cdd6e1;stroke:#b9c4d1;stroke-width:1}
  .joint{fill:#cdd6e1;stroke:#b9c4d1;stroke-width:1;transition:fill .5s}.joint.inj{fill:#d83a48;stroke:#8f1d2a}
  .m{fill:#c0cad7;stroke:#9aa6b5;stroke-width:1;transition:fill .5s,opacity .5s}
  .m.act{fill:url(#red);stroke:#a82b37}
  .m.act.i1{opacity:.55}.m.act.i2{opacity:.68}.m.act.i3{opacity:.8}.m.act.i4{opacity:.9}.m.act.i5{opacity:1}
  .m.inj{fill:url(#inj);stroke:#8f1d2a}
  .legend i{border:1px solid rgba(0,0,0,.12)} .ramp{display:inline-flex;gap:2px;vertical-align:-2px;margin:0 5px}.ramp i{background:#d83a48;border:none}
  #tip{background:#0b0f14e6;color:#fff}''',
 GEO=geo(GRAD_RED), BELOW='    <div class="legend" id="legend"></div>',
 NOTE='<b>Geometry: MIT react-native-body-highlighter muscle paths, re-tagged with the 16 <code>muscle_groups.py</code> keys.</b> Same <code>data-muscle-key</code> / <code>data-part-id</code> contract — the Python side is reused unchanged; only <code>macros/mannequin.html</code> swaps geometry.',
 SCRIPT='\nconst MUSCLE_KEYS='+KEYS+';\nconst JOINTS=["front-knee","front-ankle","back-ankle"];\nlet mode="load";const I=["i1","i2","i3","i4","i5"];\n'
 'function rnd(n){return Math.floor(Math.random()*n);}\n'
 'function paintKey(k,c){document.querySelectorAll(\'[data-muscle-key="\'+k+\'"]\').forEach(function(e){e.classList.add.apply(e.classList,c);});}\n'
 'function clearAll(){document.querySelectorAll(".m").forEach(function(e){e.classList.remove("act","inj","i1","i2","i3","i4","i5");});document.querySelectorAll(".joint").forEach(function(e){e.classList.remove("inj");});}\n'
 'function randomize(){clearAll();if(mode==="load"){MUSCLE_KEYS.forEach(function(k){if(Math.random()<.6)paintKey(k,["act",I[rnd(5)]]);});}'
 'else{MUSCLE_KEYS.slice().sort(function(){return Math.random()-.5;}).slice(0,1+rnd(2)).forEach(function(k){paintKey(k,["inj"]);});'
 'JOINTS.slice().sort(function(){return Math.random()-.5;}).slice(0,1+rnd(2)).forEach(function(p){document.querySelectorAll(\'[data-part-id="\'+p+\'"]\').forEach(function(e){e.classList.add("inj");});});}}\n'
 'function setMode(m){mode=m;document.getElementById("btnLoad").classList.toggle("active",m==="load");document.getElementById("btnInjury").classList.toggle("active",m==="injury");'
 'document.getElementById("title").textContent=m==="load"?"Muscles worked — last 7 days":"Active injuries & sickness";'
 'document.getElementById("legend").innerHTML=m==="load"?\'<span><i style="background:#c0cad7"></i>Not worked</span><span>Load<span class="ramp"><i style="opacity:.55"></i><i style="opacity:.68"></i><i style="opacity:.8"></i><i style="opacity:.9"></i><i></i></span>low&rarr;high</span>\':\'<span><i style="background:#d83a48"></i>Injury / sickness</span><span><i style="background:#c0cad7"></i>Healthy</span>\';randomize();}\n'
 +TIP_JS+'\nsetMode("load");')

# ---------- Proposal 2: Heatmap (dark) ----------
write('proposal-2-anatomical-heatmap.html',
 TITLE='MyTraL Mannequin v3 — Anatomical Heatmap', TAG='Proposal 2 · Anatomical Heatmap',
 H1='Same anatomy, dark — a cool&rarr;hot volume heatmap',
 SUB='The Proposal 1 geometry re-skinned for a premium dark UI: training volume maps to a perceptual cool&rarr;hot ramp with per-muscle glow; injuries pulse.',
 CARDTITLE='Weekly training volume',
 CONTROLS=f'<button id="btnLoad" class="active" onclick="setMode({Q}load{Q})">Volume</button><button id="btnInjury" onclick="setMode({Q}injury{Q})">Injury</button><button onclick="randomize()">Randomize ⟳</button>',
 STYLE=COMMON_CSS+'''
  :root{--bg:#0d1117;--bg2:#11161d;--card:#161b22;--ink:#e6edf3;--muted:#8b97a6;--line:#222b36}
  body{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Roboto,sans-serif;background:radial-gradient(1200px 600px at 50% -10%,var(--bg2),var(--bg));color:var(--ink);min-height:100vh}
  .tag{display:inline-block;font-size:.7rem;letter-spacing:.1em;text-transform:uppercase;color:#04121a;background:linear-gradient(90deg,#23b89a,#2f86c5);border-radius:99px;padding:3px 11px;margin-bottom:12px}
  .card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:22px;box-shadow:0 20px 50px rgba(0,0,0,.3)}
  button{font:inherit;font-size:.83rem;border:1px solid var(--line);background:var(--bg2);color:var(--ink);border-radius:9px;padding:6px 12px;cursor:pointer}
  button:hover{border-color:#3a4a5a} button.active{background:linear-gradient(90deg,#23b89a,#2f86c5);color:#04121a;border-color:transparent;font-weight:600}
  .outline{fill:#161e28;stroke:#2a3744;stroke-width:2}
  .silh{fill:#1b2530;stroke:#2a3744;stroke-width:1}
  .joint{fill:#1b2530;stroke:#2a3744;stroke-width:1;transition:fill .5s}.joint.inj{fill:#ff4d6d;filter:drop-shadow(0 0 6px rgba(255,77,109,.6))}
  .m{fill:#243241;stroke:#33424f;stroke-width:1;transition:fill .5s,filter .5s}
  .m.h1{fill:url(#h1)}.m.h2{fill:url(#h2)}.m.h3{fill:url(#h3)}.m.h4{fill:url(#h4)}.m.h5{fill:url(#h5)}.m.h6{fill:url(#h6)}
  .m.h3,.m.h4{filter:drop-shadow(0 0 4px rgba(246,194,68,.5))}
  .m.h5,.m.h6{filter:drop-shadow(0 0 6px rgba(226,59,78,.6))}
  .m.inj{fill:url(#inj);filter:drop-shadow(0 0 6px rgba(255,77,109,.6));animation:pulse 1.6s ease-in-out infinite}
  @keyframes pulse{0%,100%{opacity:.9}50%{opacity:1}}
  .ramp{height:12px;width:170px;border-radius:99px;display:inline-block;vertical-align:-2px;margin:0 6px;background:linear-gradient(90deg,#2f86c5,#23b89a,#9ed64a,#f6c244,#ef6b3a,#e23b4e)}
  #tip{background:#000d;color:#fff}''',
 GEO=geo(GRAD_HEAT), BELOW='    <div class="legend" id="legend"></div>',
 NOTE='<b>Identical geometry to Proposal&nbsp;1 — only the skin changes.</b> Muscles fill from a 6-stop cool&rarr;hot gradient set with a CSS glow; injuries pulse. Dark/light is one swap of CSS custom properties (drive it from Tabler&#39;s theme).',
 SCRIPT='\nconst MUSCLE_KEYS='+KEYS+';\nconst JOINTS=["front-knee","front-ankle","back-ankle"];\nlet mode="load";const H=["h1","h2","h3","h4","h5","h6"];\n'
 'function rnd(n){return Math.floor(Math.random()*n);}\n'
 'function paintKey(k,c){document.querySelectorAll(\'[data-muscle-key="\'+k+\'"]\').forEach(function(e){e.classList.add.apply(e.classList,c);});}\n'
 'function clearAll(){document.querySelectorAll(".m").forEach(function(e){e.classList.remove("inj","h1","h2","h3","h4","h5","h6");});document.querySelectorAll(".joint").forEach(function(e){e.classList.remove("inj");});}\n'
 'function randomize(){clearAll();if(mode==="load"){MUSCLE_KEYS.forEach(function(k){if(Math.random()<.62)paintKey(k,[H[rnd(6)]]);});}'
 'else{MUSCLE_KEYS.slice().sort(function(){return Math.random()-.5;}).slice(0,1+rnd(2)).forEach(function(k){paintKey(k,["inj"]);});'
 'JOINTS.slice().sort(function(){return Math.random()-.5;}).slice(0,1+rnd(2)).forEach(function(p){document.querySelectorAll(\'[data-part-id="\'+p+\'"]\').forEach(function(e){e.classList.add("inj");});});}}\n'
 'function setMode(m){mode=m;document.getElementById("btnLoad").classList.toggle("active",m==="load");document.getElementById("btnInjury").classList.toggle("active",m==="injury");'
 'document.getElementById("title").textContent=m==="load"?"Weekly training volume":"Active injuries & sickness";'
 'document.getElementById("legend").innerHTML=m==="load"?\'<span>Low volume<span class="ramp"></span>High volume</span>\':\'<span><i style="background:#ff4d6d"></i>Injury / sickness</span><span><i style="background:#243241"></i>Healthy</span>\';randomize();}\n'
 +TIP_JS+'\nsetMode("load");')

# ---------- Proposal 3: Picker ----------
write('proposal-3-interactive-picker.html',
 TITLE='MyTraL Mannequin v3 — Interactive Picker', TAG='Proposal 3 · Interactive Picker',
 H1='The same realistic body as a click-to-select picker',
 SUB='Proves the geometry keeps today&#39;s picker UX: click a muscle once for primary (green), twice for secondary (amber), a third time to clear. Writes the same CSV inputs.',
 CARDTITLE='Assign muscles to this exercise',
 CONTROLS='<button onclick="clearAll()">Clear</button>',
 STYLE=COMMON_CSS+'''
  :root{--bg:#f6f8fb;--card:#fff;--ink:#1d2733;--muted:#6b7785;--line:#e3e8ef}
  body{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Roboto,sans-serif;background:var(--bg);color:var(--ink)}
  .tag{display:inline-block;font-size:.7rem;letter-spacing:.09em;text-transform:uppercase;color:#1a7431;background:#e7f6ec;border:1px solid #bfe6c9;border-radius:99px;padding:2px 10px;margin-bottom:12px}
  .card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:22px;box-shadow:0 1px 2px rgba(16,24,40,.04),0 10px 28px rgba(16,24,40,.06)}
  button{font:inherit;font-size:.83rem;border:1px solid var(--line);background:#fff;color:var(--ink);border-radius:9px;padding:6px 12px;cursor:pointer}
  button:hover{border-color:#c3ccd8}
  .outline{fill:#cdd6e1;stroke:#aeb9c7;stroke-width:2}
  .silh{fill:#cdd6e1;stroke:#b9c4d1;stroke-width:1} .joint{fill:#cdd6e1;stroke:#b9c4d1;stroke-width:1}
  .m{fill:#c0cad7;stroke:#9aa6b5;stroke-width:1;cursor:pointer;transition:fill .3s}
  .m.prim{fill:url(#grn);stroke:#1a7431}.m.sec{fill:url(#amb);stroke:#b36d00}
  .m.hov{stroke:#206bc4;stroke-width:2}
  .badges{min-height:30px;display:flex;flex-wrap:wrap;gap:6px;justify-content:center;margin-top:12px}
  .badge{font-size:.78rem;border-radius:99px;padding:3px 10px;display:inline-flex;align-items:center;gap:6px}
  .badge.p{background:#e7f6ec;color:#1a7431;border:1px solid #bfe6c9}.badge.s{background:#fff3da;color:#9a6400;border:1px solid #f3dca0}
  .badge b{cursor:pointer;opacity:.6}.badge b:hover{opacity:1}
  .legend i{border:1px solid rgba(0,0,0,.12)} #tip{background:#0b0f14e6;color:#fff}''',
 GEO=geo(GRAD_PICK),
 BELOW='    <div class="legend"><span><i style="background:#2fa353"></i>Primary — main target</span><span><i style="background:#e09a16"></i>Secondary — assists</span><span><i style="background:#c0cad7"></i>Not selected</span></div>\n    <div class="badges" id="badges"></div>\n    <input type="hidden" name="muscle_groups" id="mg-primary"><input type="hidden" name="muscle_groups_secondary" id="mg-secondary">',
 NOTE='<b>The picker is just an interaction layer over the same geometry.</b> Click cycling + the hidden <code>muscle_groups</code> / <code>muscle_groups_secondary</code> CSV inputs are unchanged from today&#39;s macro — the CRUD blueprints need no change.',
 SCRIPT='\nconst LABELS={pecs:"Pectorals",shoulders:"Shoulders",biceps:"Biceps",triceps:"Triceps",forearms:"Forearms",abs:"Abs",obliques:"Obliques",traps:"Trapezius",lats:"Lats",lower_back:"Lower Back",glutes:"Glutes",quads:"Quadriceps",hamstrings:"Hamstrings",calves:"Calves",neck:"Neck",hip_flexors:"Hip Flexors"};\n'
 'var state={};\n'
 'function paint(){document.querySelectorAll("[data-muscle-key]").forEach(function(el){var s=state[el.dataset.muscleKey]||0;el.classList.remove("prim","sec");if(s===1)el.classList.add("prim");if(s===2)el.classList.add("sec");});'
 'var prim=[],sec=[];Object.keys(state).forEach(function(k){if(state[k]===1)prim.push(k);if(state[k]===2)sec.push(k);});'
 'document.getElementById("mg-primary").value=prim.join(",");document.getElementById("mg-secondary").value=sec.join(",");'
 'var B=document.getElementById("badges");B.innerHTML=(prim.length||sec.length)?prim.map(function(k){return \'<span class="badge p">\'+LABELS[k]+\' <b onclick="drop(&#39;\'+k+\'&#39;)">&times;</b></span>\';}).join("")+sec.map(function(k){return \'<span class="badge s">\'+LABELS[k]+\' <b onclick="drop(&#39;\'+k+\'&#39;)">&times;</b></span>\';}).join(""):\'<span style="color:var(--muted);font-size:.8rem">Click a muscle: once = primary, twice = secondary, third = clear</span>\';}\n'
 'function cycle(k){state[k]=((state[k]||0)+1)%3;if(!state[k])delete state[k];paint();}\n'
 'window.drop=function(k){delete state[k];paint();};\n'
 'function clearAll(){for(var k in state)delete state[k];paint();}\n'
 'document.querySelectorAll("[data-muscle-key]").forEach(function(el){el.addEventListener("click",function(){cycle(el.dataset.muscleKey);});'
 'el.addEventListener("mouseenter",function(){document.querySelectorAll(\'[data-muscle-key="\'+el.dataset.muscleKey+\'"]\').forEach(function(x){x.classList.add("hov");});});'
 'el.addEventListener("mouseleave",function(){document.querySelectorAll(\'[data-muscle-key="\'+el.dataset.muscleKey+\'"]\').forEach(function(x){x.classList.remove("hov");});});});\n'
 +TIP_JS+'\nstate.pecs=1;state.triceps=1;state.shoulders=2;state.abs=2;paint();')

print("ALL DONE")
