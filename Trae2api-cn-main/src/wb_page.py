"""WorkBuddy 管理页（wb-switch 同款 UI，MIT 设计参考 changexbc/workbuddy-switch）。

纯静态单页（原生 HTML/CSS/JS，零依赖、零构建链），由 main.py 的 /web/wb 路由返回。
注意：本文件整份字符串内不允许出现反斜杠字符（Python 转义会破坏 JS）。
"""

WB_PAGE_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>WorkBuddy 池 · 控制台</title>
<style>
:root{
  --bg:#fafafa;--fg:#18181b;--muted:#71717a;--border:#e4e4e7;--card:#ffffff;
  --primary:#18181b;--primary-fg:#fafafa;--ring:#a1a1aa;--destructive:#dc2626;
  --ok:#16a34a;--warn:#d97706;--sidebar:#fafafa;--chip:#f4f4f5;--overlay:rgba(24,24,27,.45);
  --radius:12px;--shadow:0 1px 2px rgba(0,0,0,.05),0 4px 16px rgba(0,0,0,.04);
}
html[data-theme="dark"]{
  --bg:#09090b;--fg:#fafafa;--muted:#a1a1aa;--border:#27272a;--card:#18181b;
  --primary:#fafafa;--primary-fg:#18181b;--ring:#52525b;--destructive:#f87171;
  --ok:#4ade80;--warn:#fbbf24;--sidebar:#0c0c0e;--chip:#27272a;--overlay:rgba(0,0,0,.6);
  --shadow:0 1px 2px rgba(0,0,0,.4),0 6px 24px rgba(0,0,0,.35);
}
*{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%}
body{font:14px/1.6 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif;background:var(--bg);color:var(--fg)}
.app{display:flex;min-height:100vh}
a{color:inherit;text-decoration:none}
button{font:inherit}

/* ---------- sidebar ---------- */
.sidebar{width:248px;flex:0 0 248px;background:var(--sidebar);border-right:1px solid var(--border);
  display:flex;flex-direction:column;padding:14px 12px;gap:4px;position:sticky;top:0;height:100vh}
.brand{display:flex;align-items:center;gap:10px;padding:8px 10px 16px}
.brand-mark{width:34px;height:34px;border-radius:10px;background:var(--primary);color:var(--primary-fg);
  display:flex;align-items:center;justify-content:center;font-weight:700;font-size:15px}
.brand-name{font-weight:700;font-size:15px}
.brand-sub{font-size:11px;color:var(--muted)}
.nav{display:flex;flex-direction:column;gap:2px}
.nav a{display:flex;align-items:center;gap:10px;padding:9px 12px;border-radius:9px;font-size:13.5px;
  color:var(--muted);transition:background .15s,color .15s;cursor:pointer}
.nav a:hover{background:rgba(24,24,27,.05);color:var(--fg)}
html[data-theme="dark"] .nav a:hover{background:rgba(250,250,250,.06)}
.nav a.active{background:rgba(24,24,27,.06);color:var(--fg);font-weight:600}
html[data-theme="dark"] .nav a.active{background:rgba(250,250,250,.08)}
.nav a svg{width:16px;height:16px}
.sidebar-foot{margin-top:auto;padding:10px;display:flex;flex-direction:column;gap:8px}
.foot-note{font-size:11px;color:var(--muted);line-height:1.5}

/* ---------- main ---------- */
.main{flex:1;min-width:0;padding:22px 26px 40px;max-width:1120px}
.page-title{font-size:19px;font-weight:700;margin-bottom:2px}
.page-desc{font-size:12.5px;color:var(--muted);margin-bottom:18px}
.toolbar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:16px}
.spacer{flex:1}

/* ---------- buttons / inputs ---------- */
.btn{display:inline-flex;align-items:center;gap:6px;border:1px solid var(--border);background:var(--card);
  color:var(--fg);border-radius:9px;padding:7px 13px;font-size:13px;cursor:pointer;transition:all .15s;white-space:nowrap}
.btn:hover{border-color:var(--ring)}
.btn svg{width:14px;height:14px}
.btn.primary{background:var(--primary);color:var(--primary-fg);border-color:var(--primary)}
.btn.primary:hover{opacity:.86}
.btn.destructive{color:var(--destructive)}
.btn.destructive:hover{border-color:var(--destructive)}
.btn.sm{padding:4px 10px;font-size:12.5px;border-radius:8px}
.btn:disabled{opacity:.5;cursor:not-allowed}
.select,.input,textarea.input{border:1px solid var(--border);background:var(--card);color:var(--fg);
  border-radius:9px;padding:7px 10px;font-size:13px;outline:none}
.select:focus,.input:focus{border-color:var(--ring);box-shadow:0 0 0 3px rgba(161,161,170,.25)}
textarea.input{width:100%;min-height:130px;font-family:ui-monospace,Consolas,monospace;font-size:12px;resize:vertical}
.switch{position:relative;width:38px;height:22px;flex:0 0 38px}
.switch input{opacity:0;width:0;height:0}
.switch i{position:absolute;inset:0;background:var(--chip);border:1px solid var(--border);border-radius:999px;cursor:pointer;transition:.2s}
.switch i:before{content:"";position:absolute;width:16px;height:16px;left:2px;top:2px;border-radius:50%;background:var(--muted);transition:.2s}
.switch input:checked + i{background:var(--ok);border-color:var(--ok)}
.switch input:checked + i:before{background:#fff;transform:translateX(16px)}
.seg{display:inline-flex;background:var(--chip);border-radius:9px;padding:3px;gap:2px}
.seg button{border:0;background:transparent;color:var(--muted);border-radius:7px;padding:5px 12px;font-size:12.5px;cursor:pointer}
.seg button.on{background:var(--card);color:var(--fg);font-weight:600;box-shadow:var(--shadow)}

/* ---------- cards ---------- */
.card{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);box-shadow:var(--shadow);padding:16px;margin-bottom:14px}
.card h3{font-size:14px;margin-bottom:10px}
.grid{display:grid;gap:14px}
.grid.cols2{grid-template-columns:repeat(auto-fill,minmax(420px,1fr))}
.grid.cols4{grid-template-columns:repeat(auto-fill,minmax(200px,1fr))}
.grid.cols3{grid-template-columns:repeat(auto-fill,minmax(250px,1fr))}
.acct{display:flex;flex-direction:column;gap:10px}
.acct.compact{padding:12px}
.acct-head{display:flex;align-items:center;gap:11px}
.avatar{width:40px;height:40px;border-radius:50%;background:var(--chip);display:flex;align-items:center;
  justify-content:center;font-weight:700;font-size:16px;color:var(--fg);flex:0 0 40px;overflow:hidden}
.acct-name{font-weight:700;font-size:14.5px;display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.acct-meta{font-size:11.5px;color:var(--muted);word-break:break-all}
.badge{display:inline-flex;align-items:center;gap:3px;border-radius:6px;padding:1px 7px;font-size:11px;
  background:var(--chip);color:var(--muted);white-space:nowrap}
.badge.ok{background:rgba(22,163,74,.12);color:var(--ok)}
.badge.warn{background:rgba(217,119,6,.14);color:var(--warn)}
.badge.bad{background:rgba(220,38,38,.12);color:var(--destructive)}
.badge.info{background:rgba(59,130,246,.12);color:#3b82f6}
.badge.pri{background:var(--primary);color:var(--primary-fg)}
.bar{height:6px;border-radius:999px;background:var(--chip);overflow:hidden}
.bar i{display:block;height:100%;border-radius:999px;background:var(--primary)}
.bar i.ok{background:var(--ok)}
.bar i.warn{background:var(--warn)}
.bar i.bad{background:var(--destructive)}
.rowline{display:flex;align-items:center;justify-content:space-between;gap:10px;font-size:12.5px}
.rowline .k{color:var(--muted)}
.acct-actions{display:flex;gap:6px;flex-wrap:wrap;margin-top:2px}
.dropdown{position:relative}
.dropdown-menu{position:absolute;right:0;top:calc(100% + 4px);background:var(--card);border:1px solid var(--border);
  border-radius:10px;box-shadow:var(--shadow);min-width:150px;padding:4px;z-index:40;display:none}
.dropdown.open .dropdown-menu{display:block}
.dropdown-menu button{display:flex;width:100%;align-items:center;gap:8px;border:0;background:transparent;
  color:var(--fg);border-radius:7px;padding:7px 10px;font-size:13px;cursor:pointer;text-align:left}
.dropdown-menu button:hover{background:var(--chip)}
.dropdown-menu button.danger{color:var(--destructive)}

/* ---------- table / stats ---------- */
.table-wrap{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{text-align:left;padding:9px 10px;border-bottom:1px solid var(--border);white-space:nowrap}
th{color:var(--muted);font-size:12px;font-weight:600}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
.stat{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:14px 16px}
.stat .k{font-size:12px;color:var(--muted)}
.stat .v{font-size:22px;font-weight:700;font-variant-numeric:tabular-nums;margin-top:2px}
.stat .s{font-size:11.5px;color:var(--muted)}
.chart{width:100%;height:180px}
.chart rect.bar1{fill:var(--primary)}
.chart rect.bar2{fill:var(--ok)}
.chart text{fill:var(--muted);font-size:10px}
.sortable{cursor:pointer;user-select:none}
.sortable:hover{color:var(--fg)}
.legend{display:flex;gap:14px;font-size:12px;color:var(--muted);margin-top:6px}
.legend i{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:5px;vertical-align:-1px}

/* ---------- dialog / toast ---------- */
.overlay{position:fixed;inset:0;background:var(--overlay);z-index:100;display:flex;align-items:center;justify-content:center;padding:20px}
.dialog{background:var(--card);border:1px solid var(--border);border-radius:14px;box-shadow:var(--shadow);
  width:min(560px,94vw);max-height:88vh;overflow:auto;padding:18px;animation:pop .16s ease-out}
@keyframes pop{from{transform:scale(.96);opacity:0}to{transform:scale(1);opacity:1}}
.dialog h3{font-size:15px;margin-bottom:12px;display:flex;align-items:center;justify-content:space-between}
.dialog h3 .x{border:0;background:transparent;color:var(--muted);cursor:pointer;font-size:16px;padding:2px 6px}
.dlg-foot{display:flex;justify-content:flex-end;gap:8px;margin-top:14px}
.linkbox{border:1px dashed var(--border);border-radius:10px;padding:12px;font-size:13px;margin-top:10px;word-break:break-all}
.linkbox a{color:#3b82f6}
.spin{display:inline-block;width:13px;height:13px;border:2px solid var(--ring);border-top-color:transparent;border-radius:50%;animation:sp 1s linear infinite;vertical-align:-2px;margin-right:6px}
@keyframes sp{to{transform:rotate(360deg)}}
#toasts{position:fixed;right:18px;bottom:18px;z-index:200;display:flex;flex-direction:column;gap:8px}
.toast{background:var(--card);border:1px solid var(--border);border-left:3px solid var(--primary);border-radius:10px;
  box-shadow:var(--shadow);padding:10px 14px;font-size:13px;min-width:240px;max-width:380px;animation:pop .18s ease-out}
.toast.ok{border-left-color:var(--ok)}
.toast.bad{border-left-color:var(--destructive)}
.toast.warn{border-left-color:var(--warn)}
.msg{font-size:12.5px;color:var(--muted);min-height:18px;margin-top:8px;white-space:pre-wrap}
.empty{color:var(--muted);text-align:center;padding:34px 10px;font-size:13px}
.form-row{display:flex;align-items:center;justify-content:space-between;gap:14px;padding:10px 0;border-bottom:1px solid var(--border)}
.form-row:last-child{border-bottom:0}
.form-row .lbl{font-size:13.5px}
.form-row .hint{font-size:11.5px;color:var(--muted)}
.section-title{font-size:12px;color:var(--muted);font-weight:600;text-transform:uppercase;letter-spacing:.4px;margin:16px 0 4px}
/* 侧边栏折叠 */
.app.mini .sidebar{width:66px;flex-basis:66px;padding:10px 6px}
.app.mini .brand{flex-direction:column;gap:8px;padding:4px 0 12px}
.app.mini .brand-name,.app.mini .brand-sub,.app.mini .nav a span,.app.mini .foot-note{display:none}
.app.mini .brand-mark{width:38px}
.app.mini .nav a{justify-content:center;padding:11px 0}
.app.mini .rowline{display:none}
/* 骨架屏 */
.skl{height:64px;border-radius:10px;background:var(--chip);background-image:linear-gradient(100deg,transparent 30%,rgba(255,255,255,.35) 50%,transparent 70%);background-size:200% 100%;animation:skl 1.1s infinite}
html[data-theme="dark"] .skl{background-image:linear-gradient(100deg,transparent 30%,rgba(255,255,255,.07) 50%,transparent 70%)}
@keyframes skl{0%{background-position:180% 0}100%{background-position:-80% 0}}
@media (max-width:860px){
  .sidebar{width:64px;flex-basis:64px;padding:10px 6px}
  .brand-name,.brand-sub,.nav a span,.foot-note{display:none}
  .nav a{justify-content:center;padding:10px}
  .main{padding:16px}
  .grid.cols2{grid-template-columns:1fr}
}
</style>
</head>
<body>
<div class="app">
  <aside class="sidebar">
    <div class="brand">
      <div class="brand-mark">WB</div>
      <div><div class="brand-name">Trae2api</div><div class="brand-sub">WorkBuddy 账号池</div></div>
      <button class="btn sm" id="mini-btn" title="折叠/展开侧边栏" style="margin-left:auto">☰</button>
    </div>
    <nav class="nav" id="nav"></nav>
    <div class="sidebar-foot">
      <div class="rowline" style="padding:0 4px"><span class="k" style="font-size:12px">深色模式</span>
        <label class="switch"><input type="checkbox" id="theme-toggle" onchange="onThemeToggle(this.checked)"><i></i></label>
      </div>
      <div class="foot-note">UI 设计参考 workbuddy-switch (MIT)<br>wb-* 国内池 · wbi-* 国际池</div>
    </div>
  </aside>
  <main class="main" id="view"></main>
</div>
<div id="toasts"></div>
<div id="modal-root"></div>

<script>
/* ================= 基础 ================= */
var ICON = {
  user:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>',
  link:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>',
  chart:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>',
  sparkles:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3z"/></svg>',
  settings:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/></svg>',
  plus:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M5 12h14M12 5v14"/></svg>',
  download:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>',
  upload:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>',
  refresh:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/></svg>',
  trash:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>',
  power:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18.36 6.64a9 9 0 1 1-12.73 0"/><line x1="12" y1="2" x2="12" y2="12"/></svg>',
  calcheck:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/><path d="m9 16 2 2 4-4"/></svg>',
  info:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/></svg>',
  more:'<svg viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="5" r="1.6"/><circle cx="12" cy="12" r="1.6"/><circle cx="12" cy="19" r="1.6"/></svg>',
  zap:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>',
  clock:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>',
  chevR:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m9 18 6-6-6-6"/></svg>'
};

function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});}
function api(p,opt){
  return fetch(p,Object.assign({credentials:'same-origin',headers:{'Content-Type':'application/json'}},opt)).then(function(r){
    if(r.status===401){location.reload();throw new Error('需要重新登录');}
    return r.json();
  });
}
function toast(txt,type,ms){
  var t=document.createElement('div');t.className='toast '+(type||'');t.textContent=txt;
  document.getElementById('toasts').appendChild(t);
  setTimeout(function(){t.style.opacity='0';t.style.transition='opacity .3s';},ms||3200);
  setTimeout(function(){t.remove();},(ms||3200)+400);
}
function openModal(html){
  var root=document.getElementById('modal-root');
  root.innerHTML='<div class="overlay" onclick="if(event.target===this)closeModal()"><div class="dialog">'+html+'</div></div>';
}
function closeModal(){document.getElementById('modal-root').innerHTML='';}
function pad2(n){return String(n).padStart(2,'0');}
function fmtDate(ms){if(!ms)return '--';var d=new Date(Number(ms));return d.getFullYear()+'-'+pad2(d.getMonth()+1)+'-'+pad2(d.getDate());}
function fmtDT(ms){if(!ms)return '--';var d=new Date(Number(ms));return fmtDate(ms)+' '+pad2(d.getHours())+':'+pad2(d.getMinutes());}
function daysLeft(ms){if(!ms)return 0;return (Number(ms)-Date.now())/864e5;}
function fmtTokens(n){n=Number(n)||0;if(n>=1e9)return (n/1e9).toFixed(2)+'B';if(n>=1e6)return (n/1e6).toFixed(2)+'M';if(n>=1e3)return (n/1e3).toFixed(1)+'K';return String(n);}
function fmtCredits(n){n=Number(n)||0;var v=Math.round(n*100)/100;return (v%1===0)?String(v):v.toFixed(2);}
function daysText(ms){var v=daysLeft(ms);if(!ms)return '--';return v>=0?v.toFixed(1)+' 天':'已过期';}

/* ================= 主题 ================= */
function resolveTheme(mode){
  if(mode==='dark')return 'dark';
  if(mode==='light')return 'light';
  return (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches)?'dark':'light';
}
function applyTheme(mode){
  document.documentElement.setAttribute('data-theme',resolveTheme(mode));
  var cb=document.getElementById('theme-toggle');
  if(cb)cb.checked=(resolveTheme(mode)==='dark');
}
function onThemeToggle(dark){
  var cur=STATE.settings.theme||'system';
  var mode=dark?'dark':'light';
  if((cur==='system'&&dark===((window.matchMedia&&window.matchMedia('(prefers-color-scheme: dark)').matches)))||cur===mode){
    mode='system';
  }
  STATE.settings.theme=mode;applyTheme(mode);
  api('/api/wb-settings',{method:'POST',body:JSON.stringify({theme:mode})});
}
window.matchMedia('(prefers-color-scheme: dark)').addEventListener && window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change',function(){
  if((STATE.settings.theme||'system')==='system')applyTheme('system');
});

/* ================= 状态 & 路由 ================= */
var STATE={settings:{theme:'system',card_density:'comfortable',expiry_warn_days:7},accounts:[],filter:'all',poll:null,dlgState:null};
var MEM={};
function cached(key,path,ttl,cb){
  var hit=MEM[key];
  if(hit&&Date.now()-hit.ts<ttl){cb(hit.data,true);}
  api(path).then(function(d){MEM[key]={ts:Date.now(),data:d};cb(d,false);})
    .catch(function(e){if(!hit)cb(null,false,e);});
}
function invalidate(key){if(key)delete MEM[key];else MEM={};}
var NAVS=[
  {hash:'/',label:'账号管理',icon:ICON.user},
  {hash:'/sessions',label:'关联会话',icon:ICON.link},
  {hash:'/token-stats',label:'Token 统计',icon:ICON.chart},
  {hash:'/credit-stats',label:'积分统计',icon:ICON.sparkles},
  {hash:'/settings',label:'设置',icon:ICON.settings}
];
function route(){
  var h=location.hash||'#/';
  if(h.charAt(0)==='#')h=h.slice(1);
  if(!NAVS.some(function(n){return n.hash===h;}))h='/';
  var nav=document.getElementById('nav');
  nav.innerHTML=NAVS.map(function(n){
    return '<a href="#'+n.hash+'" class="'+(n.hash===h?'active':'')+'">'+n.icon+'<span>'+n.label+'</span></a>';
  }).join('');
  var view=document.getElementById('view');
  view.innerHTML='<div class="empty">加载中…</div>';
  if(STATE.poll){clearInterval(STATE.poll);STATE.poll=null;}
  if(h==='/')return renderAccounts();
  if(h==='/sessions')return renderSessions();
  if(h==='/token-stats')return renderTokenStats();
  if(h==='/credit-stats')return renderCreditStats();
  if(h==='/settings')return renderSettings();
}
window.addEventListener('hashchange',route);

/* ================= 页面：账号管理 ================= */
function variantBadge(v){return v==='ai'?'<span class="badge info">国际版</span>':'<span class="badge">国内版</span>';}

function renderAccounts(){
  var view=document.getElementById('view');
  view.innerHTML=
    '<div class="page-title">账号管理</div>'+
    '<div class="page-desc">wb-* 走国内池 · wbi-* 走国际池 · 与 Trae 账号池相互独立</div>'+
    '<div class="toolbar">'+
      '<button class="btn primary" id="btn-add">'+ICON.plus+'添加账号</button>'+
      '<button class="btn" id="btn-import">'+ICON.upload+'导入备份</button>'+
      '<button class="btn" id="btn-export">'+ICON.download+'导出备份</button>'+
      '<button class="btn" id="btn-refresh-all">'+ICON.refresh+'刷新积分并签到</button>'+
      '<span class="spacer"></span>'+
      '<div class="seg" id="seg-filter">'+
        '<button data-f="all" class="on">全部</button>'+
        '<button data-f="cn">国内版</button>'+
        '<button data-f="ai">国际版</button>'+
      '</div>'+
      '<div class="seg" id="seg-density">'+
        '<button data-d="comfortable" class="'+(STATE.settings.card_density!=='compact'?'on':'')+'">宽松</button>'+
        '<button data-d="compact" class="'+(STATE.settings.card_density==='compact'?'on':'')+'">紧凑</button>'+
      '</div>'+
    '</div>'+
    '<div id="acct-msg" class="msg"></div>'+
    '<div class="grid cols2" id="acct-grid"><div class="empty">加载中…</div></div>';

  document.getElementById('btn-add').onclick=function(){oauthDialog();};
  document.getElementById('btn-import').onclick=function(){importDialog();};
  document.getElementById('btn-export').onclick=function(){window.open('/api/wb-export?include_tokens=1');toast('备份已开始下载','ok');};
  document.getElementById('btn-refresh-all').onclick=function(){refreshAll(this);};
  document.getElementById('seg-filter').onclick=function(ev){
    var b=ev.target.closest('button');if(!b)return;
    STATE.filter=b.getAttribute('data-f');
    this.querySelectorAll('button').forEach(function(x){x.classList.toggle('on',x===b);});
    paintAccounts();
  };
  document.getElementById('seg-density').onclick=function(ev){
    var b=ev.target.closest('button');if(!b)return;
    var d=b.getAttribute('data-d');
    STATE.settings.card_density=d;
    this.querySelectorAll('button').forEach(function(x){x.classList.toggle('on',x===b);});
    paintAccounts();
    api('/api/wb-settings',{method:'POST',body:JSON.stringify({card_density:d})});
  };
  loadAccounts();
}
function loadAccounts(){
  cached('accounts','/api/wb-accounts',8000,function(d,stale,err){
    if(err){document.getElementById('acct-grid').innerHTML='<div class="empty">加载失败: '+esc(err.message)+'</div>';return;}
    STATE.accounts=d.accounts||[];paintAccounts();
  });
}
function visibleAccounts(){
  return STATE.accounts.filter(function(a){
    if(STATE.filter==='all')return true;
    return (a.variant||'cn')===STATE.filter;
  });
}
function paintAccounts(){
  var grid=document.getElementById('acct-grid');if(!grid)return;
  var list=visibleAccounts();
  var warn=Number(STATE.settings.expiry_warn_days||7);
  var eligible=STATE.accounts.filter(function(a){return a.model_enabled&&!a.needs_relogin;});
  var soonest=null;
  eligible.forEach(function(a){if(soonest===null||daysLeft(a.expires_at)<daysLeft(soonest.expires_at))soonest=a;});
  if(!list.length){
    grid.innerHTML='<div class="empty">暂无账号。点击上方「添加账号」用 OAuth 登录接入；也可「导入备份」恢复。</div>';
    return;
  }
  grid.innerHTML=list.map(function(a){
    var v=a.variant||'cn';
    var dl=daysLeft(a.expires_at);
    var barCls=dl<warn?'bad':(dl<14?'warn':'ok');
    var barPct=Math.max(2,Math.min(100,dl/28*100));
    var ck=(a.quota_cache&&a.quota_cache.checkin)||{};
    var st=a.needs_relogin?'<span class="badge bad">需重新登录</span>':(a.model_enabled?'<span class="badge ok">启用</span>':'<span class="badge">已停用</span>');
    var chips='';
    if(soonest&&a.uid===soonest.uid&&eligible.length>1)chips+='<span class="badge warn">'+ICON.zap+'建议优先</span>';
    var ckTxt=(ck.today_checked_in===undefined&&ck.active===undefined)?'--':
      (ck.today_checked_in?'<span class="badge ok">'+ICON.calcheck+'今日已签'+(ck.streak_days?' · 连签 '+ck.streak_days:'')+'</span>':'<span class="badge">今日未签</span>');
    var err=a.last_error?'<span class="badge bad">'+esc(String(a.last_error).slice(0,26))+'</span>':'';
    var bar='';
    var qc=a.quota_cache;
    if(qc&&qc.remaining!=null){
      var rem=Number(qc.remaining)||0,tot=Number(qc.total)||0;
      var pct=tot>0?Math.max(2,Math.min(100,rem/tot*100)):100;
      var bcls=rem<=0?'bad':(tot>0&&rem/tot<0.15?'warn':'ok');
      bar='<div class="rowline"><span class="k">积分余额'+(qc.package_count?('（'+qc.package_count+' 个资源包）'):(qc.packages&&qc.packages.length?('（'+qc.packages.length+' 个资源包）'):''))+'</span><b>'+fmtCredits(rem)+(tot?(' / '+fmtCredits(tot)):'')+'</b></div>'+
          '<div class="bar"><i class="'+bcls+'" style="width:'+pct+'%"></i></div>'+
          (qc.expire_at?('<div class="rowline"><span class="k">最早到期</span><span>'+esc(qc.expire_at)+'</span></div>'):'');
    }else{
      bar='<div class="rowline"><span class="k">签到积分</span><span>'+(ck.daily_credit?('每日 +'+esc(ck.daily_credit)):'--')+
          (ck.active===false?' · <span class="badge warn">活动未开启</span>':'')+'</span></div>';
    }
    return '<div class="card acct '+(STATE.settings.card_density==='compact'?'compact':'')+'">'+
      '<div class="acct-head">'+
        '<div class="avatar">'+esc(String(a.nickname_plain||'?').trim().charAt(0)||'?')+'</div>'+
        '<div style="flex:1;min-width:0"><div class="acct-name">'+esc(a.nickname_plain)+st+variantBadge(v)+chips+'</div>'+
        '<div class="acct-meta">'+esc(String(a.uid).slice(0,13))+'… · '+esc(a.domain||'')+'</div></div>'+
        '<div class="dropdown" data-uid="'+esc(a.uid)+'">'+
          '<button class="btn sm" data-dd>'+ICON.more+'</button>'+
          '<div class="dropdown-menu">'+
            '<button data-act="detail">详情</button>'+
            '<button data-act="checkin">立即签到</button>'+
            '<button data-act="toggle">'+(a.model_enabled?'停用':'启用')+'</button>'+
            '<button data-act="del" class="danger">删除账号</button>'+
          '</div>'+
        '</div>'+
      '</div>'+
      '<div class="rowline"><span class="k">Token 有效期</span><span>至 '+fmtDate(a.expires_at)+' · '+daysText(a.expires_at)+'</span></div>'+
      '<div class="bar"><i class="'+barCls+'" style="width:'+barPct+'%"></i></div>'+
      bar+
      '<div class="rowline"><span class="k">签到状态</span>'+ckTxt+err+'</div>'+
      '<div class="acct-actions">'+
        '<button class="btn sm '+(a.model_enabled?'':'primary')+'" data-quick="toggle">'+(a.model_enabled?'停用':'启用')+'</button>'+
        '<button class="btn sm" data-quick="checkin">'+ICON.calcheck+'立即签到</button>'+
      '</div>'+
    '</div>';
  }).join('');

  grid.onclick=function(ev){
    var dd=ev.target.closest('[data-dd]');
    if(dd){var w=dd.parentElement;var was=w.classList.contains('open');
      grid.querySelectorAll('.dropdown.open').forEach(function(x){x.classList.remove('open');});
      if(!was)w.classList.add('open');return;}
    var act=ev.target.closest('[data-act]');
    var quick=ev.target.closest('[data-quick]');
    var card=ev.target.closest('.card.acct');
    if(!card)return;
    var uid=card.querySelector('.dropdown').getAttribute('data-uid');
    var acct=STATE.accounts.find(function(x){return String(x.uid)===String(uid);});
    if(!acct)return;
    var op=act?act.getAttribute('data-act'):(quick?quick.getAttribute('data-quick'):null);
    if(op==='toggle')toggleAcc(uid,!acct.model_enabled);
    else if(op==='del')delAcc(uid,acct.nickname_plain);
    else if(op==='checkin')checkinAcc(uid);
    else if(op==='detail')detailDialog(acct);
  };
}
function toggleAcc(uid,on){
  api('/api/wb-accounts/'+encodeURIComponent(uid)+'/'+(on?'enable':'disable'),{method:'POST'})
    .then(function(){toast(on?'已启用':'已停用','ok');loadAccounts();});
}
function delAcc(uid,nick){
  if(!confirm('确定删除账号「'+nick+'」？其 token 将从池中移除。'))return;
  api('/api/wb-accounts/'+encodeURIComponent(uid),{method:'DELETE'})
    .then(function(){toast('账号已删除','ok');loadAccounts();});
}
function checkinAcc(uid){
  toast('正在签到…');
  api('/api/wb-checkin',{method:'POST',body:JSON.stringify({uid:uid})}).then(function(d){
    var r=(d.results||[])[0]||{};
    if(r.ok)toast((r.already?'今日已签到':('签到成功'+(r.credit!=null?' +'+r.credit:''))),'ok');
    else toast('签到失败: '+(r.msg||'未知'),'bad');
    invalidate('accounts');invalidate('cstats');loadAccounts();
  }).catch(function(e){toast('签到失败: '+e.message,'bad');});
}
function refreshAll(btn){
  btn.disabled=true;var el=document.getElementById('acct-msg');el.textContent='正在刷新积分并签到…';
  api('/api/wb-credits/refresh',{method:'POST'}).then(function(){
    return api('/api/wb-checkin',{method:'POST',body:JSON.stringify({})});
  }).then(function(d){
    var ok=0,already=0,bad=0;(d.results||[]).forEach(function(r){if(r.ok){r.already?already++:ok++;}else bad++;});
    el.textContent='';
    toast('签到完成：成功 '+ok+'，已签 '+already+'，失败 '+bad,'ok');
    invalidate('accounts');invalidate('cstats');loadAccounts();
  }).catch(function(e){el.textContent='失败: '+e.message;toast('操作失败','bad');})
  .finally(function(){btn.disabled=false;});
}
function detailDialog(a){
  var ck=(a.quota_cache&&a.quota_cache.checkin)||{};
  var pk=(a.quota_cache&&a.quota_cache.packages)||[];
  var pkHtml=pk.length?
    '<div class="section-title" style="margin-top:12px">资源包明细</div><table><thead><tr><th>名称</th><th class="num">剩余</th><th class="num">总量</th><th>到期</th></tr></thead><tbody>'+
    pk.map(function(p){return '<tr><td>'+esc(p.name)+(p.daily?' <span class="badge">按日</span>':'')+'</td><td class="num">'+esc(p.remain_precise!=null?fmtCredits(p.remain_precise):p.remain)+'</td><td class="num">'+esc(p.size)+'</td><td>'+esc(p.expire||'--')+'</td></tr>';}).join('')+'</tbody></table>':'';
  openModal('<h3>账号详情<button class="x" onclick="closeModal()">✕</button></h3>'+
    '<div class="rowline"><span class="k">昵称</span><b>'+esc(a.nickname_plain)+'</b></div>'+
    '<div class="rowline"><span class="k">UID</span><span>'+esc(a.uid)+'</span></div>'+
    '<div class="rowline"><span class="k">版本</span><span>'+(a.variant==='ai'?'国际版 (ai)':'国内版 (cn)')+'</span></div>'+
    '<div class="rowline"><span class="k">域名</span><span>'+esc(a.domain||'')+'</span></div>'+
    '<div class="rowline"><span class="k">套件</span><span>'+esc(a.edition_type||'-')+'</span></div>'+
    '<div class="rowline"><span class="k">Access 有效期至</span><span>'+fmtDT(a.expires_at)+'（'+daysText(a.expires_at)+'）</span></div>'+
    '<div class="rowline"><span class="k">Refresh 有效期至</span><span>'+fmtDT(a.refresh_expires_at)+'</span></div>'+
    '<div class="rowline"><span class="k">Access Token</span><span style="font-family:monospace;font-size:11px">'+esc(a.access_token||'-')+'</span></div>'+
    '<div class="rowline"><span class="k">连签天数</span><span>'+esc(ck.streak_days??'-')+'</span></div>'+
    '<div class="rowline"><span class="k">每日积分</span><span>'+(ck.daily_credit?('+'+esc(ck.daily_credit)):'-')+'</span></div>'+
    '<div class="rowline"><span class="k">最近错误</span><span>'+esc(a.last_error||'-')+'</span></div>'+
    pkHtml+
    '<div class="dlg-foot"><button class="btn" onclick="closeModal()">关闭</button></div>');
}
function oauthDialog(){
  openModal('<h3>添加账号<button class="x" onclick="closeModal()">✕</button></h3>'+
    '<div class="seg" id="seg-variant" style="width:100%">'+
      '<button data-v="cn" class="on" style="flex:1">国内版 · 扫码登录</button>'+
      '<button data-v="ai" style="flex:1">国际版 · Web 登录</button>'+
    '</div>'+
    '<div id="oauth-body" style="margin-top:12px">'+
      '<p style="font-size:13px;color:var(--muted)">选择版本后点击开始，将在浏览器打开登录页；完成后本窗口自动检测并导入。</p>'+
    '</div>'+
    '<div class="dlg-foot"><button class="btn" onclick="closeModal()">取消</button>'+
    '<button class="btn primary" id="oauth-go">开始登录</button></div>');
  var variant='cn';
  document.getElementById('seg-variant').onclick=function(ev){
    var b=ev.target.closest('button');if(!b)return;
    variant=b.getAttribute('data-v');
    this.querySelectorAll('button').forEach(function(x){x.classList.toggle('on',x===b);});
  };
  document.getElementById('oauth-go').onclick=function(){
    var btn=this;btn.disabled=true;
    api('/api/wb-auth/login-start',{method:'POST',body:JSON.stringify({variant:variant})}).then(function(d){
      if(!d.success){toast('发起登录失败','bad');btn.disabled=false;return;}
      STATE.dlgState=d.state;
      var isAI=d.variant==='ai';
      document.getElementById('oauth-body').innerHTML=
        '<div class="linkbox"><b>'+(isAI?'国际版 Web 登录':'国内版扫码登录')+'</b><br>'+
        '1. 点击链接完成登录：<a href="'+esc(d.auth_url)+'" target="_blank" rel="noopener">'+esc(d.auth_url)+'</a><br>'+
        '2. 登录成功后停留几秒，本窗口自动检测（10 分钟内有效）<br>'+
        '<span class="mut"><span class="spin"></span>等待授权中…</span></div>';
      window.open(d.auth_url,'_blank');
      var tries=0;
      STATE.poll=setInterval(function(){
        tries++;
        if(tries>200){clearInterval(STATE.poll);STATE.poll=null;toast('等待超时，请重试','bad');return;}
        api('/api/wb-auth/login-poll?state='+encodeURIComponent(STATE.dlgState)).then(function(r){
          if(r.status==='ok'){
            clearInterval(STATE.poll);STATE.poll=null;
            if(r.imported){toast('✅ 账号「'+(r.nickname||r.uid)+'」已加入账号池','ok');closeModal();loadAccounts();}
            else toast('登录成功但导入失败：'+(r.import_error||'未知'),'bad');
          }else if(r.status==='error'){
            clearInterval(STATE.poll);STATE.poll=null;
            toast('登录失败：['+(r.code||'')+'] '+(r.msg||''),'bad');
          }
        }).catch(function(){});
      },3000);
    }).catch(function(e){btn.disabled=false;toast('发起登录失败: '+e.message,'bad');});
  };
}
function importDialog(){
  openModal('<h3>从备份导入<button class="x" onclick="closeModal()">✕</button></h3>'+
    '<p style="font-size:13px;color:var(--muted)">选择此前导出的 JSON 备份文件，或直接粘贴内容。同 uid 账号将被覆盖更新。</p>'+
    '<p style="margin:10px 0"><input type="file" id="imp-file" accept=".json" class="input"></p>'+
    '<textarea class="input" id="imp-text" placeholder="粘贴导出的备份 JSON 内容（含 accounts 数组）"></textarea>'+
    '<div class="dlg-foot"><button class="btn" onclick="closeModal()">取消</button>'+
    '<button class="btn primary" id="imp-go">开始导入</button></div>');
  document.getElementById('imp-file').onchange=function(){
    var f=this.files&&this.files[0];if(!f)return;
    var fr=new FileReader();fr.onload=function(){document.getElementById('imp-text').value=String(fr.result);};fr.readAsText(f);
  };
  document.getElementById('imp-go').onclick=function(){
    var txt=document.getElementById('imp-text').value.trim();
    if(!txt){toast('请先选择或粘贴备份内容','warn');return;}
    var payload;
    try{payload=JSON.parse(txt);}catch(e){toast('JSON 解析失败','bad');return;}
    api('/api/wb-import',{method:'POST',body:JSON.stringify(payload)}).then(function(d){
      toast('导入完成：新增 '+d.added+'，更新 '+d.updated+'，跳过 '+d.skipped,'ok');
      closeModal();loadAccounts();
    }).catch(function(e){toast('导入失败: '+e.message,'bad');});
  };
}

/* ================= 页面：调用会话 ================= */
/* ================= 页面：关联会话 ================= */
function openGroupDetail(g){
  var toks=(g.prompt_tokens||0)+(g.completion_tokens||0);
  var rows=(g.records||[]).map(function(r){
    return '<tr><td>'+fmtDT(r.ts)+'</td><td>'+esc(r.model||'')+'</td>'+
      '<td class="num">'+fmtTokens(r.prompt_tokens)+'</td><td class="num">'+fmtTokens(r.completion_tokens)+'</td>'+
      '<td>'+(r.status==='ok'?'<span class="badge ok">ok</span>':'<span class="badge bad">'+esc(r.status||'err')+'</span>')+'</td></tr>';
  }).join('');
  openModal('<h3>会话详情</h3>'+
    '<div class="rowline"><span class="k">账号</span><span>'+esc(g.account)+variantBadge(g.variant)+'</span></div>'+
    '<div class="rowline"><span class="k">模型</span><span>'+esc(g.model)+'</span></div>'+
    '<div class="rowline"><span class="k">调用次数</span><b>'+g.calls+(g.errors>0?(' · <span class="badge bad">'+g.errors+' 异常</span>'):'')+'</b></div>'+
    '<div class="rowline"><span class="k">消耗 Token</span><b>'+fmtTokens(toks)+'</b></div>'+
    '<div class="rowline"><span class="k">时间范围</span><span>'+fmtDT(g.first_ts)+' ~ '+fmtDT(g.last_ts)+'</span></div>'+
    '<div class="table-wrap" style="max-height:280px;overflow:auto;margin-top:10px"><table><thead><tr><th>时间</th><th>模型</th><th class="num">输入</th><th class="num">输出</th><th>状态</th></tr></thead><tbody>'+
    (rows||'<tr><td colspan="5">无明细</td></tr>')+'</tbody></table></div>'+
    '<div style="display:flex;justify-content:flex-end;margin-top:12px"><button class="btn" onclick="closeModal()">关闭</button></div>');
}
function renderSessions(){
  var view=document.getElementById('view');
  view.innerHTML='<div class="page-title">关联会话</div>'+
    '<div class="page-desc">按「账号 + 模型」且间隔超 30 分钟切分为会话组（原版关联桌面端本地会话库，服务端以真实调用分组呈现）</div>'+
    '<div class="toolbar">'+
      '<div class="seg" id="sg-variant"><button data-v="all" class="on">全部</button><button data-v="cn">国内版</button><button data-v="ai">国际版</button></div>'+
      '<div class="seg" id="sg-status"><button data-s="all" class="on">全部</button><button data-s="ok">正常</button><button data-s="err">有异常</button></div>'+
    '</div>'+
    '<div id="sg-list" class="grid cols2"><div class="skl"></div><div class="skl"></div><div class="skl"></div><div class="skl"></div></div>'+
    '<div id="sg-page" style="display:flex;justify-content:center;margin-top:12px"></div>';
  var S={groups:[],variant:'all',status:'all',page:1};
  function paint(){
    var list=S.groups.filter(function(g){
      if(S.variant!=='all'&&(g.variant||'cn')!==S.variant)return false;
      if(S.status==='ok'&&g.errors>0)return false;
      if(S.status==='err'&&!(g.errors>0))return false;
      return true;
    });
    var PS=8,HIDE=4,pages=Math.max(1,Math.ceil(list.length/PS));
    if(S.page>pages)S.page=pages;
    var slice=list.slice((S.page-1)*PS,S.page*PS);
    var el=document.getElementById('sg-list');if(!el)return;
    if(!slice.length){
      el.innerHTML='<div class="empty">暂无会话——用 wb-* 模型发一条消息后，这里会按会话分组展示。</div>';
    }else{
      el.innerHTML=slice.map(function(g){
        var toks=(g.prompt_tokens||0)+(g.completion_tokens||0);
        return '<div class="card acct sg-card" data-id="'+esc(g.id)+'" style="cursor:pointer">'+
          '<div class="acct-head"><div class="avatar">'+esc(String(g.account||'?').trim().charAt(0)||'?')+'</div>'+
          '<div style="flex:1;min-width:0"><div class="acct-name">'+esc(g.account)+variantBadge(g.variant)+
          (g.errors>0?'<span class="badge bad">'+g.errors+' 异常</span>':'<span class="badge ok">正常</span>')+'</div>'+
          '<div class="acct-meta">'+esc(g.model)+'</div></div><span style="color:var(--muted)">'+ICON.chevR+'</span></div>'+
          '<div class="rowline"><span class="k">调用次数</span><b>'+g.calls+'</b></div>'+
          '<div class="rowline"><span class="k">消耗 Token</span><b>'+fmtTokens(toks)+'</b></div>'+
          '<div class="rowline"><span class="k">最近活跃</span><span>'+fmtDT(g.last_ts)+'</span></div>'+
        '</div>';
      }).join('');
    }
    var pg=document.getElementById('sg-page');
    if(list.length>HIDE&&pages>1){
      pg.style.display='flex';
      pg.innerHTML='<div class="seg"><button data-p="prev"'+(S.page<=1?' disabled':'')+'>上一页</button>'+
        '<button disabled style="border:0;background:none;cursor:default">'+S.page+' / '+pages+'</button>'+
        '<button data-p="next"'+(S.page>=pages?' disabled':'')+'>下一页</button></div>';
    }else{pg.style.display='none';pg.innerHTML='';}
    el.onclick=function(ev){
      var pb=ev.target.closest('[data-p]');
      if(pb){S.page+=(pb.getAttribute('data-p')==='next')?1:-1;paint();return;}
      var c=ev.target.closest('.sg-card');if(!c)return;
      var g=S.groups.find(function(x){return x.id===c.getAttribute('data-id');});
      if(g)openGroupDetail(g);
    };
  }
  document.getElementById('sg-variant').onclick=function(ev){
    var b=ev.target.closest('button');if(!b)return;
    this.querySelectorAll('button').forEach(function(x){x.classList.toggle('on',x===b);});
    S.variant=b.getAttribute('data-v');S.page=1;paint();
  };
  document.getElementById('sg-status').onclick=function(ev){
    var b=ev.target.closest('button');if(!b)return;
    this.querySelectorAll('button').forEach(function(x){x.classList.toggle('on',x===b);});
    S.status=b.getAttribute('data-s');S.page=1;paint();
  };
  cached('sessions','/api/wb-sessions/groups',5000,function(d,stale,err){
    if(err){document.getElementById('sg-list').innerHTML='<div class="empty">加载失败: '+esc(err.message)+'</div>';return;}
    S.groups=d.groups||[];paint();
  });
}

/* ================= 页面：Token 统计 ================= */
function barChart(byDay){
  if(!byDay.length)return '<div class="empty">暂无数据</div>';
  var W=820,H=170,pad=26,bw=Math.max(10,Math.min(40,(W-pad*2)/byDay.length-6));
  var maxV=1;
  byDay.forEach(function(d){maxV=Math.max(maxV,d.prompt+d.completion);});
  var svg='<svg class="chart" viewBox="0 0 '+W+' '+H+'" preserveAspectRatio="xMidYMid meet">';
  byDay.forEach(function(d,i){
    var x=pad+i*((W-pad*2)/byDay.length)+2;
    var hp=(d.prompt/maxV)*(H-46),hc=(d.completion/maxV)*(H-46);
    var y1=H-24-hp-hc;
    svg+='<rect class="bar1" x="'+x+'" y="'+(H-24-hp)+'" width="'+bw+'" height="'+Math.max(hp,0.5)+'" rx="2"><title>输入 '+fmtTokens(d.prompt)+'</title></rect>';
    if(hc>0.5)svg+='<rect class="bar2" x="'+x+'" y="'+y1+'" width="'+bw+'" height="'+hc+'" rx="2"><title>输出 '+fmtTokens(d.completion)+'</title></rect>';
    if(byDay.length<=16||i%Math.ceil(byDay.length/12)===0)
      svg+='<text x="'+(x+bw/2)+'" y="'+(H-8)+'" text-anchor="middle">'+d.date.slice(5)+'</text>';
  });
  svg+='</svg>';
  return svg;
}
function renderTokenStats(){
  var view=document.getElementById('view');
  view.innerHTML='<div class="page-title">Token 统计</div>'+
    '<div class="page-desc">wb 池的输入/输出 token 与请求量（保留 '+esc(String(STATE.settings.log_retention||5000))+' 条记录）</div>'+
    '<div class="grid cols4" id="tk-cards"><div class="empty">加载中…</div></div>'+
    '<div class="card"><h3>近 14 天用量</h3><div id="tk-chart"></div>'+
      '<div class="legend"><span><i style="background:var(--primary)"></i>输入</span><span><i style="background:var(--ok)"></i>输出</span></div></div>'+
    '<div class="card"><h3>按模型</h3><div class="table-wrap" id="tk-models"></div></div>';
  cached('tstats','/api/wb-stats/token?days=14',10000,function(d,stale,err){
    if(err){document.getElementById('tk-cards').innerHTML='<div class="empty">'+esc(err.message)+'</div>';return;}
    document.getElementById('tk-cards').innerHTML=
      '<div class="stat"><div class="k">累计输入</div><div class="v">'+fmtTokens(d.total.prompt)+'</div><div class="s">近 '+d.days+' 天</div></div>'+
      '<div class="stat"><div class="k">累计输出</div><div class="v">'+fmtTokens(d.total.completion)+'</div><div class="s">近 '+d.days+' 天</div></div>'+
      '<div class="stat"><div class="k">请求数</div><div class="v">'+d.total.requests+'</div><div class="s">错误 '+d.total.errors+'</div></div>'+
      '<div class="stat"><div class="k">今日</div><div class="v">'+fmtTokens(d.today.prompt+d.today.completion)+'</div><div class="s">'+d.today.requests+' 次请求</div></div>';
    document.getElementById('tk-chart').innerHTML=barChart(d.by_day);
    var ms=d.by_model||[];
    document.getElementById('tk-models').innerHTML=ms.length?
      '<table><thead><tr><th>模型</th><th class="num">输入</th><th class="num">输出</th><th class="num">请求</th></tr></thead><tbody>'+
      ms.map(function(m){return '<tr><td>'+esc(m.model)+'</td><td class="num">'+fmtTokens(m.prompt)+'</td><td class="num">'+fmtTokens(m.completion)+'</td><td class="num">'+m.requests+'</td></tr>';}).join('')+'</tbody></table>'
      :'<div class="empty">暂无数据</div>';
  });
}

/* ================= 页面：积分统计 ================= */
function consumeChart(daily){
  if(!daily.length)return '';
  var W=820,H=180,pad=26,bw=Math.max(10,Math.min(40,(W-pad*2)/daily.length-6));
  var maxV=1;daily.forEach(function(d){maxV=Math.max(maxV,d.consume);});
  var svg='<svg class="chart" viewBox="0 0 '+W+' '+H+'" preserveAspectRatio="xMidYMid meet">';
  daily.forEach(function(d,i){
    var x=pad+i*((W-pad*2)/daily.length)+2;
    var h=Math.max((d.consume/maxV)*(H-46),0.5);
    svg+='<rect class="bar1" x="'+x+'" y="'+(H-24-h)+'" width="'+bw+'" height="'+h+'" rx="2"><title>'+d.date+' · 消耗 '+d.consume+'</title></rect>';
    if(daily.length<=16||i%Math.ceil(daily.length/12)===0)
      svg+='<text x="'+(x+bw/2)+'" y="'+(H-8)+'" text-anchor="middle">'+d.date.slice(5)+'</text>';
  });
  svg+='</svg>';
  return svg;
}
function renderCreditStats(){
  var view=document.getElementById('view');
  view.innerHTML='<div class="page-title">积分统计</div>'+
    '<div class="toolbar"><div class="seg" id="cr-range">'+
      '<button data-r="7" class="on">近 7 天</button><button data-r="30">近 30 天</button><button data-r="0">全部</button></div>'+
      '<span class="spacer"></span><button class="btn" id="cr-refresh">'+ICON.refresh+'刷新统计</button></div>'+
    '<div class="grid cols3" id="cr-cards"><div class="skl"></div><div class="skl"></div><div class="skl"></div></div>'+
    '<div class="card"><h3>积分消耗趋势</h3><div id="cr-chart"></div><div class="hint" id="cr-note" style="margin-top:6px"></div></div>'+
    '<div class="card"><h3>模型构成（按 Token 占比 · 近 30 天）</h3><div id="cr-models"></div></div>'+
    '<div class="card"><h3>调用明细</h3><div class="table-wrap" id="cr-detail"></div><div id="cr-dpage" style="display:flex;justify-content:center;margin-top:10px"></div></div>';
  var S={range:7,daily:[],series:{},accounts:[],latest:null,dsort:{key:'ts',dir:-1},dpage:1};
  function paintStats(){
    var el=document.getElementById('cr-cards');if(!el)return;
    var rem=0;S.accounts.forEach(function(a){if(a.remaining!=null)rem+=Number(a.remaining)||0;});
    var cut=S.range>0?Date.now()-S.range*864e5:0;
    var daily=S.daily.filter(function(d){return !cut||new Date(d.date+'T00:00:00').getTime()>=cut;});
    var used=0;daily.forEach(function(d){used+=d.consume;});
    var pts=0,earliest=null;
    Object.keys(S.series).forEach(function(k){
      pts+=S.series[k].length;
      var p=S.series[k][0];
      if(p&&(!earliest||p.ts<earliest))earliest=p.ts;
    });
    el.innerHTML=
      '<div class="stat"><div class="k">当前余额</div><div class="v">'+fmtCredits(rem)+'</div><div class="s">'+S.accounts.length+' 个账号</div></div>'+
      '<div class="stat"><div class="k">区间消耗</div><div class="v">'+fmtCredits(used)+'</div><div class="s">'+(S.range>0?('近 '+S.range+' 天'):'全部时间')+'</div></div>'+
      '<div class="stat"><div class="k">采集进度</div><div class="v">'+pts+'</div><div class="s">'+(earliest?('最早快照 '+fmtDate(earliest)):'尚未开始采集')+'</div></div>';
    var chart=document.getElementById('cr-chart');
    if(!pts){chart.innerHTML='<div class="empty">尚无积分快照。点右上「刷新统计」立即采集一次，此后每次轮询自动累计。</div>';}
    else if(!daily.length){chart.innerHTML='<div class="empty">已采集快照，暂未观察到余额下降。</div>';}
    else chart.innerHTML=consumeChart(daily);
    document.getElementById('cr-note').textContent='口径与 wb-switch 相同：余额在连续快照间的正差值计为消耗（签到增加不计入）。'+(S.latest?('最近采集 '+fmtDT(S.latest)):'');
  }
  function paintModels(){
    var el=document.getElementById('cr-models');if(!el)return;
    var ms=(STATE.mshare&&STATE.mshare.by_model)||[];
    if(!ms.length){el.innerHTML='<div class="empty">暂无调用数据</div>';return;}
    var tot=0;ms.forEach(function(m){tot+=m.prompt+m.completion;});
    var maxV=1;ms.forEach(function(m){maxV=Math.max(maxV,m.prompt+m.completion);});
    el.innerHTML=ms.map(function(m){
      var v=m.prompt+m.completion;
      var pct=tot>0?Math.round(v/tot*100):0;
      var w=Math.round(v/maxV*100);
      return '<div class="rowline" style="margin:6px 0"><span class="k" style="min-width:180px">'+esc(m.model)+'</span>'+
        '<div class="bar" style="flex:1"><i style="width:'+Math.max(w,2)+'%"></i></div>'+
        '<b style="min-width:140px;text-align:right">'+fmtTokens(v)+' · '+pct+'%</b></div>';
    }).join('');
  }
  function paintDetail(){
    var el=document.getElementById('cr-detail');if(!el)return;
    var recs=(STATE.cdetail&&STATE.cdetail.records)||[];
    if(!recs.length){el.innerHTML='<div class="empty">暂无调用记录</div>';document.getElementById('cr-dpage').style.display='none';return;}
    var k=S.dsort.key,dir=S.dsort.dir;
    recs=recs.slice().sort(function(a,b){
      var va=k==='model'?(a.model||''):(Number(a.ts)||0);
      var vb=k==='model'?(b.model||''):(Number(b.ts)||0);
      return (va>vb?1:va<vb?-1:0)*dir;
    });
    var PS=20,pages=Math.max(1,Math.ceil(recs.length/PS));
    if(S.dpage>pages)S.dpage=pages;
    var slice=recs.slice((S.dpage-1)*PS,S.dpage*PS);
    el.innerHTML='<table><thead><tr>'+
      '<th class="sortable" data-k="ts">请求时间'+(k==='ts'?(dir<0?' ↓':' ↑'):'')+'</th>'+
      '<th class="sortable" data-k="model">模型'+(k==='model'?(dir<0?' ↓':' ↑'):'')+'</th>'+
      '<th>账号</th><th class="num">输入</th><th class="num">输出</th><th>状态</th></tr></thead><tbody>'+
      slice.map(function(r){
        return '<tr><td>'+fmtDT(r.ts)+'</td><td>'+esc(r.model)+'</td><td>'+esc(r.account)+'</td>'+
          '<td class="num">'+fmtTokens(r.prompt_tokens)+'</td><td class="num">'+fmtTokens(r.completion_tokens)+'</td>'+
          '<td>'+(r.status==='ok'?'<span class="badge ok">ok</span>':'<span class="badge bad">'+esc(r.status||'err')+'</span>')+'</td></tr>';
      }).join('')+'</tbody></table>';
    var pg=document.getElementById('cr-dpage');
    if(pages>1){
      pg.style.display='flex';
      pg.innerHTML='<div class="seg"><button data-p="prev"'+(S.dpage<=1?' disabled':'')+'>上一页</button>'+
        '<button disabled style="border:0;background:none;cursor:default">'+S.dpage+' / '+pages+'</button>'+
        '<button data-p="next"'+(S.dpage>=pages?' disabled':'')+'>下一页</button></div>';
    }else{pg.style.display='none';pg.innerHTML='';}
    el.onclick=function(ev){
      var pb=ev.target.closest('[data-p]');
      if(pb){S.dpage+=(pb.getAttribute('data-p')==='next')?1:-1;paintDetail();return;}
      var th=ev.target.closest('.sortable');if(!th)return;
      var nk=th.getAttribute('data-k');
      if(S.dsort.key===nk)S.dsort.dir*=-1;else{S.dsort.key=nk;S.dsort.dir=-1;}
      S.dpage=1;paintDetail();
    };
  }
  document.getElementById('cr-range').onclick=function(ev){
    var b=ev.target.closest('button');if(!b)return;
    this.querySelectorAll('button').forEach(function(x){x.classList.toggle('on',x===b);});
    S.range=Number(b.getAttribute('data-r'))||0;paintStats();
  };
  document.getElementById('cr-refresh').onclick=function(){
    var btn=this;btn.disabled=true;
    toast('正在采集账号积分…');
    api('/api/wb-credits/refresh',{method:'POST'}).then(function(){
      invalidate('cstats');invalidate('mshare');invalidate('cdetail');
      loadCreditData();toast('已采集并刷新统计','ok');
    }).catch(function(e){toast('采集失败: '+e.message,'bad');})
    .finally(function(){btn.disabled=false;});
  };
  function loadCreditData(){
    cached('cstats','/api/wb-stats/credit',10000,function(d,stale,err){
      if(err){document.getElementById('cr-cards').innerHTML='<div class="empty">加载失败: '+esc(err.message)+'</div>';return;}
      S.daily=d.daily||[];S.series=d.series||{};S.accounts=d.accounts||[];S.latest=d.latest_collect_at||null;
      paintStats();
    });
    cached('mshare','/api/wb-stats/token?days=30',15000,function(d){if(d){STATE.mshare=d;paintModels();}});
    cached('cdetail','/api/wb-sessions?limit=300',8000,function(d){if(d){STATE.cdetail=d;paintDetail();}});
  }
  loadCreditData();
}

/* ================= 页面：设置 ================= */
function renderSettings(){
  var view=document.getElementById('view');
  view.innerHTML='<div class="page-title">设置</div>'+
    '<div class="page-desc">配置保存在服务端 data/wb_settings.json，对所有访问者生效</div>'+
    '<div class="card"><h3>外观</h3><div id="set-look"></div></div>'+
    '<div class="card"><h3>轮询与保活</h3><div id="set-poll"></div></div>'+
    '<div class="card"><h3>自动签到</h3><div id="set-checkin"></div><div id="set-accts" style="margin-top:8px"></div></div>'+
    '<div class="card"><h3>记录</h3><div id="set-log"></div></div>'+
    '<div style="display:flex;justify-content:flex-end"><button class="btn primary" id="set-save">保存设置</button></div>'+
    '<div class="msg" id="set-msg"></div>';
  api('/api/wb-settings').then(function(d){
    var s=d.settings||{};STATE.acctFlags=d.accounts||[];
    var row=function(label,hint,ctrl){return '<div class="form-row"><div><div class="lbl">'+label+'</div>'+(hint?'<div class="hint">'+hint+'</div>':'')+'</div>'+ctrl+'</div>';};
    var sw=function(id,on){return '<label class="switch"><input type="checkbox" id="'+id+'"'+(on?' checked':'')+'><i></i></label>';};
    document.getElementById('set-look').innerHTML=
      row('主题','跟随系统 / 浅色 / 深色','<select class="select" id="s-theme">'+
        '<option value="system"'+(s.theme==='system'?' selected':'')+'>跟随系统</option>'+
        '<option value="light"'+(s.theme==='light'?' selected':'')+'>浅色</option>'+
        '<option value="dark"'+(s.theme==='dark'?' selected':'')+'>深色</option></select>')+
      row('卡片密度','账号卡片的显示密度','<select class="select" id="s-density">'+
        '<option value="comfortable"'+(s.card_density!=='compact'?' selected':'')+'>宽松</option>'+
        '<option value="compact"'+(s.card_density==='compact'?' selected':'')+'>紧凑</option></select>');
    document.getElementById('set-poll').innerHTML=
      row('轮询模式','credit-priority 按剩余积分优先；round-robin 轮转','<select class="select" id="s-pollmode">'+
        '<option value="credit-priority"'+(s.poll_mode!=='round-robin'?' selected':'')+'>积分优先</option>'+
        '<option value="round-robin"'+(s.poll_mode==='round-robin'?' selected':'')+'>轮转</option></select>')+
      row('启用轮询','关闭后 wb 池不参与自动选号','<label class="switch"><input type="checkbox" id="s-pollen"'+(s.poll_enabled?' checked':'')+'><i></i></label>')+
      row('保活阈值（天）','access token 剩余不足 N 天时自动刷新','<input class="input" type="number" min="1" max="27" id="s-keepalive" value="'+esc(s.keepalive_days??2)+'" style="width:90px">')+
      row('到期警示阈值（天）','账号卡片 token 剩余低于 N 天标红','<input class="input" type="number" min="1" max="27" id="s-warn" value="'+esc(s.expiry_warn_days??7)+'" style="width:90px">');
    document.getElementById('set-checkin').innerHTML=
      row('启用自动签到','每日到达设定时间后自动为合格账号签到','<label class="switch"><input type="checkbox" id="s-cken"'+(s.auto_checkin?' checked':'')+'><i></i></label>')+
      row('签到时间','HH:MM，24 小时制','<input class="input" type="time" id="s-ctime" value="'+esc(s.auto_checkin_time||'09:00')+'">')+
      row('随机抖动（分钟）','在设定时间后 0~N 分钟内随机执行，降低风控特征','<input class="input" type="number" min="0" max="120" id="s-cjitter" value="'+esc(s.auto_checkin_jitter_min??30)+'" style="width:90px">');
    document.getElementById('set-accts').innerHTML=(d.accounts||[]).map(function(a){
      return row('账号：'+esc(a.nickname),'关闭后不参与自动签到（可在账号卡片手动签到）',
        '<label class="switch"><input type="checkbox" class="s-acct" data-uid="'+esc(a.uid)+'"'+(a.auto_checkin?' checked':'')+'><i></i></label>');
    }).join('')||'<div class="hint" style="padding:8px 0">暂无账号</div>';
    document.getElementById('set-log').innerHTML=
      row('记录保留条数','调用会话 / Token 统计的数据来源','<input class="input" type="number" min="100" max="50000" id="s-log" value="'+esc(s.log_retention??5000)+'" style="width:110px">');
    document.getElementById('set-save').onclick=function(){
      var body={
        theme:document.getElementById('s-theme').value,
        card_density:document.getElementById('s-density').value,
        poll_mode:document.getElementById('s-pollmode').value,
        poll_enabled:document.getElementById('s-pollen').checked,
        keepalive_days:Number(document.getElementById('s-keepalive').value)||2,
        expiry_warn_days:Number(document.getElementById('s-warn').value)||7,
        auto_checkin:document.getElementById('s-cken').checked,
        auto_checkin_time:document.getElementById('s-ctime').value||'09:00',
        auto_checkin_jitter_min:Number(document.getElementById('s-cjitter').value)||0,
        log_retention:Number(document.getElementById('s-log').value)||5000
      };
      api('/api/wb-settings',{method:'POST',body:JSON.stringify(body)}).then(function(r){
        STATE.settings=r.settings||body;applyTheme(STATE.settings.theme);
        toast('设置已保存','ok');
      }).catch(function(e){toast('保存失败: '+e.message,'bad');});
    };
    document.getElementById('set-accts').onchange=function(ev){
      var t=ev.target.closest('.s-acct');if(!t)return;
      api('/api/wb-settings',{method:'POST',body:JSON.stringify({uid:t.getAttribute('data-uid'),auto_checkin:t.checked})})
        .then(function(){toast('已更新该账号的自动签到开关','ok');});
    };
  }).catch(function(e){document.getElementById('view').innerHTML='<div class="empty">'+esc(e.message)+'</div>';});
}

/* ================= 启动 ================= */
(function(){
  try{if(localStorage.getItem('wb-mini')==='1')document.querySelector('.app').classList.add('mini');}catch(e){}
  var mb=document.getElementById('mini-btn');
  if(mb)mb.onclick=function(){
    var app=document.querySelector('.app');
    app.classList.toggle('mini');
    try{localStorage.setItem('wb-mini',app.classList.contains('mini')?'1':'0');}catch(e){}
  };
  api('/api/wb-settings').then(function(d){
    STATE.settings=Object.assign(STATE.settings,d.settings||{});
    applyTheme(STATE.settings.theme||'system');
    route();
  }).catch(function(){applyTheme('system');route();});
})();
</script>
</body>
</html>
"""
