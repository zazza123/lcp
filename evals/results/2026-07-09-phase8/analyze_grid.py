"""Phase 8 grid analysis — per-(model,arm) and per-class metrics with CIs."""
import json, glob, sys, collections
sys.path.insert(0, "evals")
from harness.stats import bootstrap_ci

ROOT = "evals/results/2026-07-09-phase8"
ARMS = ["baseline", "lcp-skill", "sitepkg", "lcp", "registry", "context7"]
# library -> class
NICHE = {"cyhole","hamana","pocket-coffea","narwhals","griffe","cyclopts","pixeltable"}
CHURNED = {"fastmcp","polars"}
CONTROL = {"requests","flask"}
def lib_of(cid):
    # case id is <library>-<slug>; library may contain a dash (pocket-coffea)
    for L in list(NICHE|CHURNED|CONTROL):
        if cid == L or cid.startswith(L+"-"):
            return L
    return cid.split("-")[0]
def cls_of(cid):
    L = lib_of(cid)
    return "niche" if L in NICHE else "churned" if L in CHURNED else "control"

def load(model):
    runs = [json.load(open(f)) for f in glob.glob(f"{ROOT}/pub-{model}/runs/*.json")]
    return runs

def engaged(r):
    pre = "mcp__context7__" if r["arm"]=="context7" else "mcp__lcp__"
    return any(d.get("name","").startswith(pre) for d in r.get("tool_call_details",[]))

def cell(runs):
    n=len(runs)
    if not n: return None
    passes=[1 if r["verification"]["passed"] else 0 for r in runs]
    misuse=[r["verification"]["misuse_count"] for r in runs]
    toks=[r["metrics"]["input_tokens"]+r["metrics"]["output_tokens"] for r in runs]
    eng=[1 if engaged(r) else 0 for r in runs]
    cost=[r["metrics"].get("cost_usd",0) for r in runs]
    plo,phi=bootstrap_ci(passes)
    mlo,mhi=bootstrap_ci(misuse)
    return dict(n=n, pass_rate=sum(passes)/n, pass_ci=(plo,phi),
                misuse=sum(misuse)/n, misuse_ci=(mlo,mhi),
                tokens=sum(toks)/n, engagement=sum(eng)/n, cost=sum(cost)/n)

for model in ["haiku","sonnet"]:
    runs=load(model)
    print(f"\n{'='*70}\nMODEL: {model}  ({len(runs)} runs)\n{'='*70}")
    by_arm=collections.defaultdict(list)
    for r in runs: by_arm[r["arm"]].append(r)
    print(f"{'arm':10s} {'n':>4s} {'pass%':>6s} {'[CI]':>13s} {'mis/run':>7s} {'tok':>6s} {'eng%':>5s} {'$':>7s}")
    for arm in ARMS:
        c=cell(by_arm[arm])
        if not c: continue
        print(f"{arm:10s} {c['n']:4d} {c['pass_rate']*100:5.1f}% "
              f"[{c['pass_ci'][0]*100:4.0f}-{c['pass_ci'][1]*100:4.0f}] "
              f"{c['misuse']:7.2f} {c['tokens']:6.0f} {c['engagement']*100:4.0f}% {c['cost']:7.4f}")
    # per class x arm pass rate
    print("\n  pass% by class x arm:")
    print(f"  {'class':8s} " + " ".join(f"{a[:9]:>9s}" for a in ARMS))
    for cl in ["niche","churned","control"]:
        row=[]
        for arm in ARMS:
            sub=[r for r in by_arm[arm] if cls_of(r["case_id"])==cl]
            row.append(f"{sum(r['verification']['passed'] for r in sub)/len(sub)*100:8.1f}%" if sub else "     -   ")
        print(f"  {cl:8s} " + " ".join(row))
    # cost-overhead-when-unused: tool arms with 0 mcp calls vs baseline mean cost
    base_cost=sum(r["metrics"].get("cost_usd",0) for r in by_arm["baseline"])/len(by_arm["baseline"])
    print(f"\n  baseline mean cost ${base_cost:.4f}")
    for arm in ["lcp","lcp-skill"]:
        unused=[r for r in by_arm[arm] if not engaged(r)]
        if unused:
            uc=sum(r["metrics"].get("cost_usd",0) for r in unused)/len(unused)
            print(f"  {arm} unused-run cost ${uc:.4f} ({len(unused)} runs, overhead {(uc/base_cost-1)*100:+.0f}%)")
