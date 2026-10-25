# -*- coding: utf-8 -*-
"""读取 model_plane.csv（相对基准尺度），生成自包含可交互二维散点图"""
import csv, json, os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "out")
rows = list(csv.DictReader(open(os.path.join(OUT, "model_plane.csv"), encoding="utf-8-sig")))

def num(r, k):
    v = r.get(k, "")
    return None if v in ("", "-1", "-1.0") else float(v)

data = []
for r in rows:
    data.append({
        "name": r["model_id"], "key": r.get("model_key", r["model_id"]),
        "P": float(r["P"]), "X": float(r["X"]),
        "tier": r["tier"], "cov": float(r["X_coverage"]), "src": r["sources"],
        "only": r.get("axis_only", ""),
        "x2": num(r, "X2"), "code": num(r, "r_code_v3"), "shi": num(r, "r_shishan"),
        "vibe": num(r, "r_vibe_code"), "mig": num(r, "r_code_migration_v1_1"),
        "tb4": num(r, "r_terminal_bench_4"), "logic": num(r, "r_logic"),
        "proof": num(r, "r_proof_bench"), "myst": num(r, "r_mysterymechanism"),
        "ioi": num(r, "r_ioi"),
    })

ev = list(csv.DictReader(open(os.path.join(OUT, "model_evidence.csv"), encoding="utf-8-sig")))
METRICS = {}
_mp = os.path.join(OUT, "metrics.json")
if os.path.exists(_mp):
    METRICS = json.load(open(_mp, encoding="utf-8"))
dates = {}
for e in ev:
    d0 = (e.get("date") or "").strip()
    if d0:
        k = (e.get("model_key", e["model_id"]), e["axis"])
        if k not in dates or d0 > dates[k]: dates[k] = d0
for d in data:
    d["pdate"] = dates.get((d["key"], "P"), "")
    d["xdate"] = dates.get((d["key"], "X"), "")
meta = {"plotted": len(data), "dual": sum(1 for d in data if not d["only"]),
        "pOnly": sum(1 for d in data if d["only"] == "P"),
        "xOnly": sum(1 for d in data if d["only"] == "X"),
        "p": len({e.get("model_key", e["model_id"]) for e in ev if e["axis"] == "P"}),
        "x": len({e.get("model_key", e["model_id"]) for e in ev if e["axis"] == "X"})}

HTML = r"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>LLM Benchmark Plane · 规划 P × 执行 X</title>
<style>
:root{--bg:#fbfbfd;--ink:#16181d;--mut:#6b7280;--line:#e5e7eb;
--m0:#b8860b;--m1:#2563eb;--m2:#0d9488;--m3:#64748b}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
font:14px/1.5 -apple-system,"Segoe UI","Noto Sans SC",system-ui,sans-serif}
.wrap{max-width:1300px;margin:0 auto;padding:28px 24px 60px}
h1{font-size:19px;margin:0 0 4px;letter-spacing:.2px}
.sub{color:var(--mut);font-size:12.5px;margin-bottom:6px}
.bar{display:flex;gap:14px;align-items:center;flex-wrap:wrap;margin:14px 0 10px}
input[type=search]{border:1px solid var(--line);border-radius:8px;padding:7px 11px;
font-size:12.5px;width:190px;outline:none;background:#fff}
input[type=search]:focus{border-color:#94a3b8}
.legend{display:flex;gap:16px;flex-wrap:wrap;font-size:12px;color:var(--mut);margin:2px 0 10px}
.legend i{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:6px;vertical-align:middle}
svg{width:100%;height:auto;display:block;background:#fff;border:1px solid var(--line);border-radius:12px}
.tick{font-size:11px;fill:#9aa1ac}
.axis{font-size:12px;fill:#4b5563}
.grid{stroke:#eef0f3;stroke-width:1}
.zone-l{font-size:11px;fill:#b6bcc6;letter-spacing:1px}
.pt{cursor:pointer}
.pt text{font-size:10.5px;fill:#3f4650;paint-order:stroke;stroke:#fff;stroke-width:2.6px;stroke-linejoin:round}
.pt.dim{opacity:.12}
.conn{stroke-width:.8;opacity:.45}
.pt.hl .conn{opacity:1;stroke-width:1.5}
.pt.hl .mk{stroke:#111;stroke-width:2.2}
.pt.hl text{font-weight:700}
.tip{position:fixed;pointer-events:none;background:#16181d;color:#fff;padding:9px 12px;
border-radius:9px;font-size:12px;line-height:1.55;opacity:0;transition:opacity .1s;z-index:9;
box-shadow:0 6px 24px rgba(0,0,0,.22);max-width:310px}
.tip b{font-weight:600;font-size:12.5px}
.tip .k{color:#9aa1ac}
table{border-collapse:collapse;width:100%;font-size:12.5px;margin-top:6px}
th,td{padding:6px 9px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}
th:first-child,td:first-child{text-align:left}
th{color:var(--mut);font-weight:500;font-size:11.5px}
details{margin-top:22px}summary{cursor:pointer;color:var(--mut);font-size:12.5px}
.note{color:var(--mut);font-size:11.5px;margin-top:14px;line-height:1.75}
</style></head><body><div class="wrap">
<h1>大模型基准平面 · 规划 P × 执行 X</h1>
<div class="sub">相对尺度：DeepSeek V4.1 Flash 1017 = 1.0 · 每个来源先除以基准模型在该来源的分数，再按权重合成</div>
<div class="sub" id="meta"></div>
<div class="bar">
  <input type="search" id="q" placeholder="搜索模型…">
  <span class="sub" style="margin:0" id="count"></span>
</div>
<div class="legend">
  <span><i style="background:var(--m0)"></i>M0（任一轴 ≥1.25）</span>
  <span><i style="background:var(--m1)"></i>M1（任一轴 ≥1.00）</span>
  <span><i style="background:var(--m2)"></i>M2（任一轴 ≥0.70）</span>
  <span><i style="background:var(--m3)"></i>M3</span>
  <span>● 双轴已测　○ 仅 P（按 P=X 落点）　◇ 仅 X（按 P=X 落点）</span>
</div>
<svg id="chart" viewBox="0 0 1240 820" role="img"></svg>
<div class="tip" id="tip"></div>
<details><summary>展开数据表</summary><div id="tbl"></div></details>
<div class="note">
坐标是「相对基准模型的能力倍数」，1.0 = DeepSeek V4.1 Flash 1017。<br>
每个来源只取该模型<b>最新一次</b>测量值，不跨月取中位——模型和题库都在迭代，跨版本数值不可比。<br>
严格版本内比较：致知按<b>月榜</b>切版本，版本内必须含基准 DeepSeek V4.1 Flash 1017，否则整版丢弃；屎山是“难度向上加题、模型从低到高逐级通过”的阶梯赛，整块算一个版本。<br>
缺 1017 的榜（ProofBench / MysteryMechanism / IOI）用 <b>DeepSeek V4.1 Flash 作链式锚点</b>：先在其他榜测出它相对 1017 的能力（P __SECP__ / X __SECX__），再以它为 1.0 折算该榜其余模型。<br>
P = 致知 logic（0.50）+ ProofBench（0.30）+ MysteryMechanism（0.20）。X = 屎山（0.32）+ code_v3（0.28）+ Vibe Code（0.14）+ Code Migration（0.09）+ TB4（0.04）+ IOI（0.01）。<br>
档位：取两轴中较高者，M0 ≥1.25、M1 ≥1.00、M2 ≥0.70，其余 M3。<br>
只有一个轴有证据的模型画在 P=X 对角线上：○ 表示仅 P 已测、◇ 表示仅 X 已测。它们的位置是假设值（未知轴按已知轴填充），档位只反映已测的那一轴，不能据此推断另一轴。公开题来源合计权重 0.05。ProgramBench 不在来源表中（分数区间 0–18.5 过窄，比值法失效）；SkillsBench 因等效基准 __SKILL__ 超过 100% 被守卫剔除。悬停看各源原始分。
</div>
</div>
<script>
const DATA = __DATA__;
const META = __META__;
document.getElementById("meta").textContent =
  `有 P 证据 ${META.p} 个模型 · 有 X 证据 ${META.x} 个 · 上图 ${META.plotted} 个（双轴 ${META.dual} · 仅 P ${META.pOnly} · 仅 X ${META.xOnly}）`;
const NS="http://www.w3.org/2000/svg";
const svg=document.getElementById("chart"), tip=document.getElementById("tip");
const W=1240,H=820,L=88,R=1164,T=56,B=744;
const MAX=1.8, MIN=0;
const px=v=>L+(v-MIN)/(MAX-MIN)*(R-L), py=v=>B-(v-MIN)/(MAX-MIN)*(B-T);
const COLOR={M0:"var(--m0)",M1:"var(--m1)",M2:"var(--m2)",M3:"var(--m3)"};
let pinned=null;

function el(n,a={},p){const e=document.createElementNS(NS,n);
  for(const k in a)e.setAttribute(k,a[k]); if(p)p.appendChild(e); return e;}
function f(v){return v==null?"—":(Math.round(v*100)/100).toFixed(2);}

function draw(){
  svg.innerHTML="";
  document.getElementById("count").textContent=DATA.length+" 个模型";

  // 档位参考线（单轴达标即可，所以只画线不画方块）
  [[1.25,"M0","#b8860b"],[1.00,"M1","#2563eb"],[0.70,"M2","#0d9488"]].forEach(([t,n,c])=>{
    el("line",{x1:px(t),y1:py(MIN),x2:px(t),y2:py(MAX),stroke:c,"stroke-width":1,
      "stroke-dasharray":"4 4",opacity:t===1?0.55:0.3},svg);
    el("line",{x1:px(MIN),y1:py(t),x2:px(MAX),y2:py(t),stroke:c,"stroke-width":1,
      "stroke-dasharray":"4 4",opacity:t===1?0.55:0.3},svg);
    el("text",{x:px(t)+6,y:py(MAX)+12,class:"tick",fill:c},svg).textContent=n+" "+t.toFixed(2);
    el("text",{x:px(MAX)-4,y:py(t)-5,class:"tick",fill:c,"text-anchor":"end"},svg).textContent=t.toFixed(2);
  });
  el("text",{x:px(1)+6,y:py(MIN)-6,class:"tick",fill:"#b45309"},svg).textContent="基准 1.0";

  el("text",{x:(L+R)/2,y:H-14,class:"axis","text-anchor":"middle"},svg)
    .textContent="执行 X（相对基准倍数）";
  el("text",{x:16,y:(T+B)/2,class:"axis","text-anchor":"middle",
    transform:`rotate(-90 16 ${(T+B)/2})`},svg).textContent="规划 P（相对基准倍数）";

  // 标签排布：点标记、参考线刻度都算障碍；先就近贪心，再对残余重叠做第二轮外扩
  const GAP=2.5, PADR=2;
  const boxes=[];
  DATA.forEach(d=>{ boxes.push({x:px(d.X)-7,y:py(d.P)-7,w:14,h:14}); });
  [[1.25,"M0"],[1.00,"M1"],[0.70,"M2"]].forEach(([t])=>{
    boxes.push({x:px(t)+3,y:T+1,w:52,h:14});
    boxes.push({x:R-42,y:py(t)-16,w:44,h:14});
  });
  boxes.push({x:px(1)+4,y:py(MIN)-18,w:52,h:14});

  const inPlot=b=>b.x>=L+PADR&&b.x+b.w<=R-PADR&&b.y>=T+PADR&&b.y+b.h<=B-PADR;
  const inter=(a,b)=>Math.max(0,Math.min(a.x+a.w,b.x+b.w)-Math.max(a.x,b.x))*
                      Math.max(0,Math.min(a.y+a.h,b.y+b.h)-Math.max(a.y,b.y));
  const DIRS=[];
  for(let a=0;a<360;a+=22.5){const r=a*Math.PI/180;DIRS.push([Math.cos(r),Math.sin(r)]);}
  const STEPS=[0,2,5,8,12,16,21,27,34,42,51,61,72,85,100,118,138,160,185,215,250,290,335,385];

  function spot(cx,cy,w,hgt,limit,strict){
    let best=null,bestCost=Infinity,bestOv=Infinity;
    for(const step of STEPS){
      if(step>limit) break;
      for(const [ux,uy] of DIRS){
        const len=Math.hypot(ux,uy), nx=ux/len, ny=uy/len;
        const dist=9+step+Math.abs(nx)*w/2+Math.abs(ny)*hgt/2;
        const box={x:cx+nx*dist-w/2,y:cy+ny*dist-hgt/2,w,h:hgt};
        if(!inPlot(box)) continue;
        const pad={x:box.x-GAP,y:box.y-GAP,w:box.w+2*GAP,h:box.h+2*GAP};
        let ov=0;
        for(const o of boxes) ov+=inter(pad,o);
        if(strict&&ov>0) continue;
        const cost=strict?step:ov*8+step;
        if(cost<bestCost){best=box;bestCost=cost;bestOv=ov;}
        if(bestCost===0) break;
      }
      if(bestCost===0) break;
    }
    return best?{box:best,ov:bestOv}:null;
  }
  function anchor(cx,cy,b){
    if(b.x>cx) return [b.x-1, Math.min(Math.max(cy,b.y+3),b.y+b.h-3)];
    if(b.x+b.w<cx) return [b.x+b.w+1, Math.min(Math.max(cy,b.y+3),b.y+b.h-3)];
    return [Math.min(Math.max(cx,b.x+3),b.x+b.w-3), b.y>cy?b.y-1:b.y+b.h+1];
  }

  const placed=[];
  const sorted=DATA.slice().sort((a,b)=>Math.max(b.P,b.X)-Math.max(a.P,a.X)||b.P-a.P);
  sorted.forEach(d=>{
    const g=el("g",{class:"pt","data-name":d.name},svg);
    const cx=px(d.X), cy=py(d.P);
    let mk;
    if(d.only==="P"){
      mk=el("circle",{cx,cy,r:5.4,fill:"none",stroke:COLOR[d.tier],"stroke-width":1.8,class:"mk"},g);
    }else if(d.only==="X"){
      mk=el("polygon",{points:`${cx},${cy-6.6} ${cx+6.6},${cy} ${cx},${cy+6.6} ${cx-6.6},${cy}`,
        fill:"none",stroke:COLOR[d.tier],"stroke-width":1.8,class:"mk"},g);
    }else{
      mk=el("circle",{cx,cy,r:5.6,fill:COLOR[d.tier],stroke:COLOR[d.tier],"stroke-width":1,class:"mk"},g);
    }
    const t=el("text",{},g); t.textContent=d.name; t.style.fill=COLOR[d.tier];
    const w=t.getComputedTextLength()+4, hgt=14;

    const sp=spot(cx,cy,w,hgt,120,false);
    const box=sp?sp.box:
      {x:Math.max(L+PADR,Math.min(R-PADR-w,cx+9)),
       y:Math.max(T+PADR,Math.min(B-PADR-hgt,cy-7)),w,h:hgt};
    const [ax2,ay2]=anchor(cx,cy,box);
    const ln=el("line",{x1:cx,y1:cy,x2:ax2,y2:ay2,class:"conn",stroke:COLOR[d.tier]},g);
    g.insertBefore(ln,mk);
    t.setAttribute("x",box.x+2); t.setAttribute("y",box.y+hgt-3.5);
    boxes.push(box);
    placed.push({cx,cy,w,hgt,t,ln,box});
    g.addEventListener("mouseenter",e=>{g.classList.add("hl");showTip(d,e);});
    g.addEventListener("mousemove",e=>moveTip(e));
    g.addEventListener("mouseleave",()=>{g.classList.remove("hl");if(pinned!==d)tip.style.opacity=0;});
    g.addEventListener("click",()=>{pinned=pinned===d?null:d;if(pinned)showTip(d);});
  });

  // 第二轮：把仍有重叠的标签往外挪，直到清空（最多 40 轮）
  for(let pass=0;pass<40;pass++){
    let moved=false;
    for(let i=0;i<placed.length;i++)for(let j=i+1;j<placed.length;j++){
      const A=placed[i].box, Bx=placed[j].box;
      if(A.x+A.w+GAP<Bx.x||Bx.x+Bx.w+GAP<A.x||A.y+A.h+GAP<Bx.y||Bx.y+Bx.h+GAP<A.y) continue;
      const p=placed[j];
      boxes.splice(boxes.indexOf(p.box),1);
      const sp2=spot(p.cx,p.cy,p.w,p.hgt,385,true);
      if(!sp2||sp2.ov>0){ boxes.push(p.box); continue; }
      const nb=sp2.box;
      p.box=nb;
      const [nx2,ny2]=anchor(p.cx,p.cy,nb);
      p.ln.setAttribute("x2",nx2); p.ln.setAttribute("y2",ny2);
      p.t.setAttribute("x",nb.x+2); p.t.setAttribute("y",nb.y+p.hgt-3.5);
      boxes.push(nb);
      moved=true;
    }
    if(!moved) break;
  }
}

function showTip(d,e){
  const raw=[["logic",d.logic],["proof",d.proof],["mystery",d.myst],["code_v3",d.code],
             ["屎山",d.shi],["vibe",d.vibe],["migration",d.mig],["tb4",d.tb4],["ioi",d.ioi]]
             .filter(x=>x[1]!=null).map(x=>`${x[0]} ${x[1].toFixed(1)}`).join(" · ");
  tip.innerHTML=`<b>${d.name}</b><br>
    <span class="k">P 规划</span> ${f(d.P)}×　<span class="k">X 执行</span> ${f(d.X)}×<br>
    <span class="k">档位</span> ${d.tier}　<span class="k">X 覆盖</span> ${(d.cov*100).toFixed(0)}%<br>
    ${d.only?`<span class="k">注意</span> 仅 ${d.only} 轴已测，位置按 P=X 假设放置<br>`:""}
    ${d.x2!=null?`<span class="k">X2 可恢复</span> ${d.x2.toFixed(1)}%<br>`:""}
    ${raw?`<span class="k">各源比值</span> ${raw}<br>`:""}
    <span class="k">来源</span> ${d.src}<br>
    <span class="k">数据日期</span> P ${d.pdate||"—"} · X ${d.xdate||"—"}`;
  tip.style.opacity=1; if(e)moveTip(e);
}
function moveTip(e){
  const pad=16; let x=e.clientX+pad,y=e.clientY+pad;
  const r=tip.getBoundingClientRect();
  if(x+r.width>innerWidth-8)x=e.clientX-r.width-pad;
  if(y+r.height>innerHeight-8)y=e.clientY-r.height-pad;
  tip.style.left=x+"px"; tip.style.top=y+"px";
}
const q=document.getElementById("q");
q.addEventListener("input",()=>{
  const s=q.value.trim().toLowerCase();
  document.querySelectorAll(".pt").forEach(g=>{
    g.classList.toggle("dim", s.length>0 && !g.dataset.name.toLowerCase().includes(s));
  });
});

const tbl=document.getElementById("tbl");
tbl.innerHTML="<table><thead><tr><th>模型</th><th>P</th><th>X</th><th>档位</th><th>轴</th><th>X 覆盖</th><th>来源</th></tr></thead><tbody>"+
 DATA.slice().sort((a,b)=>b.P-a.P).map(d=>`<tr><td>${d.name}</td>
 <td>${f(d.P)}</td><td>${f(d.X)}</td><td>${d.tier}</td><td>${d.only||"双轴"}</td>
 <td>${(d.cov*100).toFixed(0)}%</td><td style="text-align:left;color:#6b7280">${d.src}</td></tr>`).join("")+
 "</tbody></table>";

if(document.fonts&&document.fonts.ready){document.fonts.ready.then(draw);}else{draw();}
</script></body></html>
"""

html = HTML.replace("__DATA__", json.dumps(data, ensure_ascii=False))
html = html.replace("__META__", json.dumps(meta, ensure_ascii=False))
html = html.replace("__SECP__", f'{METRICS.get("sec", {}).get("P", 0):.3f}')
html = html.replace("__SECX__", f'{METRICS.get("sec", {}).get("X", 0):.3f}')
html = html.replace("__SKILL__", f'{METRICS.get("dropped", {}).get("skillsbench", 0):.2f}')
out = os.path.join(OUT, "model_plane.html")
open(out, "w", encoding="utf-8").write(html)
print("wrote", out, len(html), "bytes,", len(data), "points")
