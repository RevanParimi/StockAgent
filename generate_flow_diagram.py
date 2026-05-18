import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import matplotlib.patheffects as pe
import numpy as np

fig, ax = plt.subplots(figsize=(28, 40))
ax.set_xlim(0, 28)
ax.set_ylim(0, 40)
ax.axis('off')
fig.patch.set_facecolor('#0d1117')
ax.set_facecolor('#0d1117')

# ── helpers ──────────────────────────────────────────────────────────────────

def box(ax, x, y, w, h, label, sublabel=None,
        fc='#161b22', ec='#30363d', tc='#e6edf3', stc='#8b949e',
        radius=0.25, fontsize=11, subfontsize=8.5, bold=False):
    patch = FancyBboxPatch((x - w/2, y - h/2), w, h,
                            boxstyle=f"round,pad=0.05,rounding_size={radius}",
                            facecolor=fc, edgecolor=ec, linewidth=1.8, zorder=3)
    ax.add_patch(patch)
    weight = 'bold' if bold else 'normal'
    ty = y if sublabel is None else y + h*0.13
    ax.text(x, ty, label, ha='center', va='center', fontsize=fontsize,
            color=tc, fontweight=weight, zorder=4,
            fontfamily='monospace')
    if sublabel:
        ax.text(x, y - h*0.22, sublabel, ha='center', va='center',
                fontsize=subfontsize, color=stc, zorder=4, fontfamily='monospace')

def arrow(ax, x1, y1, x2, y2, color='#58a6ff', lw=1.8, style='->', head=12):
    ax.annotate('', xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle=f'->', color=color,
                                lw=lw, mutation_scale=head),
                zorder=5)

def label_arrow(ax, x, y, text, color='#8b949e', fs=8):
    ax.text(x, y, text, ha='center', va='center', fontsize=fs,
            color=color, zorder=6, fontfamily='monospace',
            bbox=dict(boxstyle='round,pad=0.2', fc='#0d1117', ec='none'))

def section_bg(ax, x, y, w, h, color, alpha=0.06, label=None, lc='#30363d'):
    rect = FancyBboxPatch((x, y), w, h,
                           boxstyle="round,pad=0.1,rounding_size=0.3",
                           facecolor=color, edgecolor=lc,
                           linewidth=1.2, alpha=alpha, zorder=1)
    ax.add_patch(rect)
    if label:
        ax.text(x + w/2, y + h - 0.18, label, ha='center', va='top',
                fontsize=8, color=color, alpha=0.7, zorder=2,
                fontfamily='monospace', fontstyle='italic')

# ══════════════════════════════════════════════════════════════════════════════
#  TITLE
# ══════════════════════════════════════════════════════════════════════════════
ax.text(14, 39.4, 'StockAgent — End-to-End System Flow',
        ha='center', va='center', fontsize=20, color='#e6edf3',
        fontweight='bold', fontfamily='monospace', zorder=10)
ax.text(14, 38.85, 'Multi-Agent AI System for Indian NSE/BSE Stock Analysis',
        ha='center', va='center', fontsize=11, color='#8b949e',
        fontfamily='monospace', zorder=10)

# ══════════════════════════════════════════════════════════════════════════════
#  LAYER 1 — ENTRY POINTS  (y ~ 37.5)
# ══════════════════════════════════════════════════════════════════════════════
section_bg(ax, 0.5, 36.2, 27, 2.1, '#58a6ff', label='[1] ENTRY POINTS')

entries = [
    (3.2, 'CLI\npython main.py MARUTI', '#58a6ff'),
    (7.5, 'FastAPI\nPOST :8001/analyse', '#3fb950'),
    (12.0, 'TypeScript Gateway\nPOST :3000/api/analyse', '#d29922'),
    (16.8, 'C# Scheduler\n8:30 am IST weekdays', '#f78166'),
    (21.5, 'LangGraph\ngraph.invoke()', '#a5d6ff'),
    (25.5, 'React UI\nport 5173', '#bc8cff'),
]
for ex, elabel, ec in entries:
    box(ax, ex, 37.2, 4.2, 0.85, elabel,
        fc='#161b22', ec=ec, tc=ec, fontsize=8.5)

# ══════════════════════════════════════════════════════════════════════════════
#  ARROW down to ORCHESTRATOR
# ══════════════════════════════════════════════════════════════════════════════
arrow(ax, 14, 36.2, 14, 35.45, color='#58a6ff', lw=2.5, head=14)
label_arrow(ax, 15.6, 35.82, 'ticker / company name')

# ══════════════════════════════════════════════════════════════════════════════
#  LAYER 2 — ORCHESTRATOR (y ~ 35)
# ══════════════════════════════════════════════════════════════════════════════
section_bg(ax, 2, 33.5, 24, 1.8, '#3fb950', label='[2] ORCHESTRATOR')
box(ax, 14, 34.4, 16, 0.9,
    'AutomobileAgentOrchestrator  ·  analyse() / analyse_async()',
    fc='#0a3622', ec='#3fb950', tc='#3fb950', fontsize=10, bold=True)

# ══════════════════════════════════════════════════════════════════════════════
#  ARROW → TICKER RESOLUTION
# ══════════════════════════════════════════════════════════════════════════════
arrow(ax, 14, 33.5, 14, 32.85)

# ══════════════════════════════════════════════════════════════════════════════
#  LAYER 3 — TICKER RESOLUTION (y ~ 32.5)
# ══════════════════════════════════════════════════════════════════════════════
section_bg(ax, 3.5, 31.7, 21, 1.55, '#d29922', label='[3] TICKER RESOLUTION')
box(ax, 10, 32.5, 7.5, 0.75, 'LLM Ticker Resolver\n(Qwen 235B, temp=0.0)',
    fc='#2d1f00', ec='#d29922', tc='#d29922', fontsize=9)
box(ax, 18.5, 32.5, 7, 0.75, 'yfinance Verification\n(NeMo input_rail)',
    fc='#2d1f00', ec='#d29922', tc='#e6b84d', fontsize=9)
arrow(ax, 13.75, 32.5, 15, 32.5, color='#d29922')
ax.text(14.38, 32.65, 'StockQuery', fontsize=7.5, color='#8b949e',
        fontfamily='monospace', zorder=6, ha='center')

# ══════════════════════════════════════════════════════════════════════════════
#  ARROW → LANGGRAPH FAN-OUT
# ══════════════════════════════════════════════════════════════════════════════
arrow(ax, 14, 31.7, 14, 31.05, color='#bc8cff', lw=2.5, head=14)
label_arrow(ax, 16.4, 31.38, 'LangGraph Send() fan-out × 9')

# ══════════════════════════════════════════════════════════════════════════════
#  LAYER 4 — 9-AGENT SWARM  (y ~ 25.5 – 31)
# ══════════════════════════════════════════════════════════════════════════════
section_bg(ax, 0.4, 23.3, 27.2, 7.65, '#bc8cff',
           label='[4] 9-AGENT PARALLEL SWARM  (ThreadPoolExecutor / asyncio, max_workers=8)')

agents = [
    ('SalesDemandAgent',      '18%', '#58a6ff', 'FADA/SIAM · EV Vahan\nDealer inventory · DGFT exports'),
    ('FundamentalsAgent',     '18%', '#3fb950', 'Revenue/EBITDA · Margins\nOrder book · FII/DII flow'),
    ('PatternAnalysisAgent',  '11%', '#d29922', 'RSI · MACD · Bollinger\nSupport/Resistance · Nifty corr.'),
    ('RiskMacroAgent',        '13%', '#f78166', 'INR/USD · Crude · RBI rate\nEmission risk · China supply'),
    ('ValuationCatalystAgent','12%', '#bc8cff', 'PE discount · Mean reversion\nSupport zone · Catalyst signals'),
    ('RawMaterialsAgent',      '9%', '#a5d6ff', 'Steel · Aluminium · Crude\nPolymers · Power tariff'),
    ('PolicyRegulatoryAgent',  '9%', '#ffa657', 'FAME EV subsidy · PLI\nEmission norms · Budget duties'),
    ('CompetitiveIntelAgent',  '9%', '#79c0ff', 'EV market share · New models\nJVs · ADAS/safety ratings'),
    ('SentimentAgent',         '4%', '#56d364', 'News NLP · Earnings tone\nTwitter/Reddit · YT spikes'),
]

cols = 3
rows = 3
xs = [4.4, 14.0, 23.6]
ys = [29.9, 27.3, 24.8]
agent_centers = []

for i, (name, wt, color, desc) in enumerate(agents):
    r, c = divmod(i, cols)
    cx, cy = xs[c], ys[r]
    agent_centers.append((cx, cy))

    # agent box
    bg = FancyBboxPatch((cx - 4.5, cy - 1.05), 9, 2.1,
                         boxstyle="round,pad=0.08,rounding_size=0.2",
                         facecolor='#161b22', edgecolor=color,
                         linewidth=1.6, zorder=3)
    ax.add_patch(bg)

    # weight badge
    badge = FancyBboxPatch((cx + 2.6, cy + 0.6), 1.5, 0.48,
                            boxstyle="round,pad=0.05,rounding_size=0.1",
                            facecolor=color, edgecolor='none',
                            alpha=0.25, zorder=4)
    ax.add_patch(badge)
    ax.text(cx + 3.35, cy + 0.845, wt, ha='center', va='center',
            fontsize=8, color=color, fontweight='bold', zorder=5,
            fontfamily='monospace')

    ax.text(cx, cy + 0.56, name, ha='center', va='center',
            fontsize=9, color=color, fontweight='bold',
            fontfamily='monospace', zorder=4)
    ax.text(cx, cy - 0.22, desc, ha='center', va='center',
            fontsize=7.5, color='#8b949e',
            fontfamily='monospace', zorder=4)

    # fan-out arrow from top
    arrow(ax, 14, 31.05, cx, cy + 1.05, color='#bc8cff', lw=1.2, head=9)

# ══════════════════════════════════════════════════════════════════════════════
#  LAYER 5 — CONTEXT / DATA FETCHERS  (sidebar left)
# ══════════════════════════════════════════════════════════════════════════════
section_bg(ax, 0.3, 13.5, 6.5, 9.6, '#58a6ff', label='[5] CONTEXT BUILDER')

fetchers = [
    ('yfinance\nOHLCV · P&L · PE', '#58a6ff', 22.3),
    ('Serper / NewsAPI\nNews search · NLP', '#3fb950', 21.2),
    ('Tavily\nFull-page policy', '#d29922', 20.1),
    ('C++ Indicators\nRSI · MACD · BB', '#f78166', 19.0),
    ('RAG / ChromaDB\n(if RAG_ENABLED)', '#bc8cff', 17.9),
    ('Stub fallback\nneutral 0.5', '#8b949e', 16.8),
]

for (flabel, fc, fy) in fetchers:
    box(ax, 3.55, fy, 5.8, 0.75, flabel, fc='#161b22', ec=fc, tc=fc, fontsize=8.5)

# arrows from each fetcher group to agent column 1 (approx)
for _, fc2, fy in fetchers:
    ax.annotate('', xy=(6.3, fy), xytext=(5.8, fy) if fy > 20 else (6.4, fy),
                arrowprops=dict(arrowstyle='->', color='#30363d', lw=1.1), zorder=5)

ax.text(3.55, 14.15, 'Per-agent context\nassembled at runtime',
        ha='center', va='bottom', fontsize=7.5, color='#8b949e',
        fontfamily='monospace', zorder=6)

# ── dashed connector label
ax.annotate('', xy=(6.3, 24.8), xytext=(6.3, 19.5),
            arrowprops=dict(arrowstyle='->', color='#8b949e', lw=1.2,
                            linestyle='dashed'), zorder=5)

# ══════════════════════════════════════════════════════════════════════════════
#  LAYER 5b — LLM (right sidebar)
# ══════════════════════════════════════════════════════════════════════════════
section_bg(ax, 21.2, 15.5, 6.5, 7.5, '#d29922', label='[6] LLM ENGINE')

box(ax, 24.45, 21.8, 5.8, 0.75, 'OpenRouter API\nhttps://openrouter.ai',
    fc='#2d1f00', ec='#d29922', tc='#d29922', fontsize=8.5)
box(ax, 24.45, 20.7, 5.8, 0.75, 'Qwen3-235B-A22B\ntemp=0.2 · json_object',
    fc='#2d1f00', ec='#e6b84d', tc='#e6b84d', fontsize=8.5)
box(ax, 24.45, 19.6, 5.8, 0.75, 'Retry: 3× exp back-off\n2s → 4s → 8s',
    fc='#2d1f00', ec='#ffa657', tc='#ffa657', fontsize=8.5)
box(ax, 24.45, 18.5, 5.8, 0.75, 'Cost logging\nlogs/agent_calls.jsonl',
    fc='#2d1f00', ec='#8b949e', tc='#8b949e', fontsize=8.5)
box(ax, 24.45, 17.4, 5.8, 0.75, 'AsyncOpenAI path\n(FastAPI/WebSocket)',
    fc='#2d1f00', ec='#58a6ff', tc='#58a6ff', fontsize=8.5)
box(ax, 24.45, 16.3, 5.8, 0.75, 'OpenAI SDK compat.\nno vendor lock-in',
    fc='#2d1f00', ec='#3fb950', tc='#3fb950', fontsize=8.5)

ax.annotate('', xy=(21.2, 26), xytext=(21.2, 23),
            arrowprops=dict(arrowstyle='<->', color='#d29922', lw=1.4,
                            linestyle='dashed'), zorder=5)
ax.text(21.55, 24.5, 'LLM\ncalls', ha='left', va='center', fontsize=7.5,
        color='#d29922', fontfamily='monospace', zorder=6)

# ══════════════════════════════════════════════════════════════════════════════
#  FAN-IN arrows from agents → aggregator
# ══════════════════════════════════════════════════════════════════════════════
for cx, cy in agent_centers:
    arrow(ax, cx, cy - 1.05, 14, 13.55, color='#bc8cff', lw=1.2, head=9)

# ══════════════════════════════════════════════════════════════════════════════
#  LAYER 6 — SIGNAL AGGREGATOR  (y ~ 12.5)
# ══════════════════════════════════════════════════════════════════════════════
section_bg(ax, 1.5, 10.2, 25, 3.35, '#f78166', label='[7] SIGNAL AGGREGATOR (Conflict-Aware Fusion)')

box(ax, 7.0, 12.55, 9, 0.75,
    'Step 1 · Weighted sum\nΣ(score × weight) / Σ(weights) = composite',
    fc='#2d0e00', ec='#f78166', tc='#f78166', fontsize=8.5)
box(ax, 17.5, 12.55, 8.5, 0.75,
    'Step 2 · Conflict detection\nif |score_A − score_B| ≥ 0.30 → flag',
    fc='#2d0e00', ec='#ffa657', tc='#ffa657', fontsize=8.5)
box(ax, 7.0, 11.5, 9, 0.75,
    'Step 3 · LLM conflict resolution\nQwen explains divergence + final thesis',
    fc='#2d0e00', ec='#f78166', tc='#f78166', fontsize=8.5)
box(ax, 17.5, 11.5, 8.5, 0.75,
    'Step 4 · FinalReport assembly\nverdict thresholds · conviction drivers',
    fc='#2d0e00', ec='#ffa657', tc='#ffa657', fontsize=8.5)

arrow(ax, 11.5, 12.55, 13.25, 12.55, color='#f78166')
arrow(ax, 17.5, 12.1, 17.5, 11.88, color='#f78166')
arrow(ax, 11.5, 11.5, 13.25, 11.5, color='#f78166')

# ══════════════════════════════════════════════════════════════════════════════
#  ARROW → FINAL REPORT
# ══════════════════════════════════════════════════════════════════════════════
arrow(ax, 14, 10.2, 14, 9.55, color='#3fb950', lw=2.5, head=14)

# ══════════════════════════════════════════════════════════════════════════════
#  LAYER 7 — FINAL REPORT  (y ~ 8.8)
# ══════════════════════════════════════════════════════════════════════════════
section_bg(ax, 1.5, 7.1, 25, 2.4, '#3fb950', label='[8] FINAL REPORT  (FinalReport Pydantic model)')

verdicts = [
    ('STRONG BUY\nscore ≥ 0.75', '#3fb950'),
    ('BUY\n0.60 – 0.75', '#56d364'),
    ('NEUTRAL\n0.40 – 0.60', '#d29922'),
    ('SELL\n0.25 – 0.40', '#ffa657'),
    ('STRONG SELL\nscore < 0.25', '#f78166'),
]
vxs = [3.8, 7.8, 14, 20.2, 24.2]
for (vl, vc), vx in zip(verdicts, vxs):
    box(ax, vx, 8.3, 3.8, 0.78, vl, fc='#0a3622' if 'BUY' in vl else '#161b22',
        ec=vc, tc=vc, fontsize=8.5)

box(ax, 14, 7.5, 18, 0.55,
    'final_score · verdict · weighted_agent_scores · conflicts_resolved · conviction_drivers · top_risks · investment_thesis · price_target',
    fc='#161b22', ec='#30363d', tc='#8b949e', fontsize=7.8)

# ══════════════════════════════════════════════════════════════════════════════
#  LAYER 8 — OUTPUT CHANNELS  (y ~ 6)
# ══════════════════════════════════════════════════════════════════════════════
arrow(ax, 14, 7.1, 14, 6.45, color='#58a6ff', lw=2)
section_bg(ax, 0.5, 4.6, 27, 1.8, '#58a6ff', label='[9] OUTPUT CHANNELS')

outputs = [
    ('CLI stdout\nJSON / Markdown', '#58a6ff'),
    ('FastAPI response\nPOST :8001/analyse', '#3fb950'),
    ('WebSocket events\n:8001/ws/stream', '#d29922'),
    ('React Dashboard\nport 5173', '#bc8cff'),
    ('SQLite ScoreStore\nhistory/{ticker}', '#f78166'),
    ('logs/ + outputs/\nJSONL audit trail', '#8b949e'),
    ('Alerts\nSlack/webhook', '#ffa657'),
]
ox_positions = [2.2, 6.0, 9.8, 14.0, 18.0, 22.0, 25.8]
for (ol, oc), ox in zip(outputs, ox_positions):
    box(ax, ox, 5.5, 3.6, 0.78, ol, fc='#161b22', ec=oc, tc=oc, fontsize=8)
    arrow(ax, 14, 6.45, ox, 6.0, color='#58a6ff', lw=1.1, head=8)

# ══════════════════════════════════════════════════════════════════════════════
#  LAYER 9 — OPTIONAL / FEEDBACK  (y ~ 3.5)
# ══════════════════════════════════════════════════════════════════════════════
section_bg(ax, 0.5, 1.2, 27, 3.2, '#a5d6ff', label='[10] OPTIONAL SYSTEMS & FEEDBACK LOOP')

opt_items = [
    ('RAG Pipeline\nChromaDB + sentence-\ntransformers embeddings', '#bc8cff', 3.0),
    ('RL Feedback Loop\nWeightAdapter adapts\nagent weights daily', '#3fb950', 8.0),
    ('Micro Search Loop\nPre-fetches macro news\n(background daemon)', '#d29922', 13.0),
    ('C++ Indicators\npybind11 extension\nRSI · MACD · BB', '#f78166', 18.0),
    ('APScheduler\nDaily RL review\nAsia/Kolkata TZ', '#58a6ff', 23.2),
]
for (ol, oc, ox) in opt_items:
    box(ax, ox, 2.3, 4.5, 1.6, ol, fc='#161b22', ec=oc, tc=oc, fontsize=8.5)

# RL feedback arrow looping back up
ax.annotate('', xy=(3.0, 7.3), xytext=(3.0, 3.1),
            arrowprops=dict(arrowstyle='->', color='#3fb950', lw=1.3,
                            connectionstyle='arc3,rad=-0.3'), zorder=5)
ax.text(1.1, 5.2, 'RL weight\nupdate', ha='center', va='center',
        fontsize=7, color='#3fb950', fontfamily='monospace', zorder=6)

# ══════════════════════════════════════════════════════════════════════════════
#  LEGEND
# ══════════════════════════════════════════════════════════════════════════════
legend_items = [
    ('#58a6ff', 'Entry / Output'),
    ('#3fb950', 'Core Python'),
    ('#d29922', 'Data Fetchers'),
    ('#f78166', 'Aggregation'),
    ('#bc8cff', 'LangGraph'),
    ('#a5d6ff', 'Optional Systems'),
]
lx = 0.7
for i, (lc, ll) in enumerate(legend_items):
    patch = FancyBboxPatch((lx + i*4.4, 0.25), 0.45, 0.35,
                            boxstyle="round,pad=0.05", facecolor=lc,
                            edgecolor='none', zorder=8)
    ax.add_patch(patch)
    ax.text(lx + i*4.4 + 0.6, 0.425, ll, va='center', fontsize=8,
            color='#8b949e', fontfamily='monospace', zorder=9)

plt.tight_layout(pad=0)
plt.savefig('StockAgent_FlowDiagram.png', dpi=130, bbox_inches='tight',
            facecolor='#0d1117', edgecolor='none')
print('Saved: StockAgent_FlowDiagram.png')
