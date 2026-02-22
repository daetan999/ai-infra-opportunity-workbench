# company_brief.py
# Phase B (Institutional Company Chain Coverage) — Quant-first, deterministic, UI-safe.
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


# -----------------------------
# Helpers
# -----------------------------
def _u(x: Any) -> str:
    """Clean to string (UI-safe)."""
    if x is None:
        return ""
    return str(x).strip()


def _clamp01(x: Any) -> float:
    try:
        v = float(x)
    except Exception:
        return 0.0
    if v < 0.0:
        return 0.0
    if v > 1.0:
        return 1.0
    return v


def _mean(values: List[float]) -> float:
    vals = [float(v) for v in values if v is not None]
    return sum(vals) / len(vals) if vals else 0.0


def _wavg(pairs: List[Tuple[float, float]]) -> float:
    """(value, weight) pairs."""
    num = 0.0
    den = 0.0
    for v, w in pairs:
        num += float(v) * float(w)
        den += float(w)
    return (num / den) if den else 0.0


def _flatten_risk(risk_struct: Dict[str, List[str]]) -> List[str]:
    out: List[str] = []
    for k in ["macro_risks", "industry_risks", "idiosyncratic_risks"]:
        for item in risk_struct.get(k, []) or []:
            if item:
                out.append(f"{k.replace('_',' ')}: {item}")
    return out


def _products_to_customers(p2c: Dict[str, List[str]]) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for product, custs in (p2c or {}).items():
        rows.append({"product": product, "customers": ", ".join(custs or [])})
    return rows


def _derived_quant(qp: Dict[str, Dict[str, float]]) -> Dict[str, float]:
    """
    Deterministic derived scores.
    - overall_risk: higher = more fragile (cycle + concentration + dependency + capex)
    - overall_quality: higher = more durable (moat / pricing / ecosystem / switching)
    """
    cycle = qp.get("cycle_exposure", {}) or {}
    supp = qp.get("supplier_dependency_risk", {}) or {}
    conc = qp.get("customer_concentration_risk", {}) or {}
    capx = qp.get("capital_intensity", {}) or {}
    moat = qp.get("moat_profile", {}) or {}

    risk_components = [
        _mean(list(cycle.values())),
        _mean(list(supp.values())),
        _mean(list(conc.values())),
        _mean(list(capx.values())),
    ]
    quality_components = [
        _mean(list(moat.values())),
    ]

    # Risk: emphasize concentration + capex a bit more
    overall_risk = _wavg([
        (risk_components[0], 0.25),  # cycle
        (risk_components[1], 0.20),  # supplier dependency
        (risk_components[2], 0.30),  # customer concentration
        (risk_components[3], 0.25),  # capital intensity
    ])

    # Quality: moat only for now (expand later with fundamentals)
    overall_quality = _wavg([
        (quality_components[0], 1.0),
    ])

    return {
        "overall_risk": _clamp01(overall_risk),
        "overall_quality": _clamp01(overall_quality),
    }


def _schema(
    ticker: str,
    business_model: List[str],
    revenue_mix: Dict[str, Any],
    pricing_power: str,
    suppliers: List[Dict[str, str]],
    customers: List[Dict[str, Any]],
    products_to_customers_map: Dict[str, List[str]],
    value_chain: List[str],
    competitive_landscape: List[str],
    risk_struct: Dict[str, List[str]],
    quant_profile: Dict[str, Dict[str, float]],
    narrative: Dict[str, Any],
    source_note: str = "",
) -> Dict[str, Any]:
    qp = {
        "cycle_exposure": {k: _clamp01(v) for k, v in (quant_profile.get("cycle_exposure", {}) or {}).items()},
        "supplier_dependency_risk": {k: _clamp01(v) for k, v in (quant_profile.get("supplier_dependency_risk", {}) or {}).items()},
        "customer_concentration_risk": {k: _clamp01(v) for k, v in (quant_profile.get("customer_concentration_risk", {}) or {}).items()},
        "capital_intensity": {k: _clamp01(v) for k, v in (quant_profile.get("capital_intensity", {}) or {}).items()},
        "moat_profile": {k: _clamp01(v) for k, v in (quant_profile.get("moat_profile", {}) or {}).items()},
    }
    qp["derived"] = _derived_quant(qp)

    risk_struct = risk_struct or {"macro_risks": [], "industry_risks": [], "idiosyncratic_risks": []}

    return {
        "ticker": ticker,
        "business_model": business_model or [],
        "revenue_mix": revenue_mix or {},
        "pricing_power": pricing_power or "",

        "suppliers": suppliers or [],
        "customers": customers or [],
        "products_to_customers": _products_to_customers(products_to_customers_map),
        "products_to_customers_map": products_to_customers_map or {},

        "value_chain": value_chain or [],
        "competitive_landscape": competitive_landscape or [],

        # UI expects list[str]; we also keep structured version for future logic / AI.
        "risk_layer": _flatten_risk(risk_struct),
        "risk_layer_struct": risk_struct,

        # Quant-first backbone (feeds confidence regime & future AI layer).
        "quant_profile": qp,

        # Narrative must be derived from quant + deterministic template (no live claims).
        "narrative": {
            "one_liner": _u(narrative.get("one_liner")),
            "bull_case": _u(narrative.get("bull_case")),
            "bear_case": _u(narrative.get("bear_case")),
            "watch_items": list(narrative.get("watch_items") or []),
        },

        "source_note": source_note or "",
    }


# -----------------------------
# Coverage universe (tradable tickers)
# -----------------------------
TIER1 = ["NVDA", "AMD", "AVGO", "INTC", "TSM", "ASML", "MU", "AMAT", "LRCX", "KLAC"]
TIER2 = [
    "TXN", "ADI", "NXPI", "MCHP", "QCOM", "MRVL", "ON", "SWKS", "WDC", "STM",
    "TER", "MPWR", "GFS", "ARM", "UMC", "QRVO", "COHR", "WOLF", "IPGP", "ACLS",
]
COVERAGE = TIER1 + TIER2


# -----------------------------
# Institutional templates
# -----------------------------
CHAIN: Dict[str, Dict[str, Any]] = {}

# ---- NVDA (Deep) ----
CHAIN["NVDA"] = _schema(
    ticker="NVDA",
    business_model=[
        "Designs GPUs + full accelerated computing platform (silicon + networking + software stack).",
        "Monetizes via data center GPUs/systems, networking (InfiniBand/Ethernet), and platform software ecosystem (CUDA + libraries).",
        "Primary demand driver: AI training/inference buildouts (hyperscaler + enterprise), with gaming as a secondary cycle."
    ],
    revenue_mix={
        "data_center": "dominant",
        "gaming": "meaningful",
        "auto": "smaller",
        "pro_viz_oem": "smaller",
        "notes": "Mix shifts with AI capex cycle; margins depend on supply (HBM/packaging) and product mix."
    },
    pricing_power="High when supply constrained and platform differentiation is strongest; moderates as capacity expands and alternatives mature.",
    suppliers=[
        {"name": "TSMC", "role": "Foundry (advanced nodes) — critical capacity / yield driver"},
        {"name": "Advanced packaging ecosystem", "role": "CoWoS/2.5D packaging capacity is a binding constraint in AI ramps"},
        {"name": "HBM memory vendors", "role": "HBM supply impacts system availability and platform throughput"},
        {"name": "Networking/optics partners", "role": "Interconnect components determine cluster scalability and cost"}
    ],
    customers=[
        {"group": "Hyperscalers / cloud AI", "examples": ["MSFT", "AMZN", "GOOGL", "META", "ORCL"]},
        {"group": "AI infrastructure OEMs", "examples": ["SMCI", "DELL", "HPE"]},
        {"group": "Enterprise / research labs", "examples": ["Large enterprises", "National labs", "Universities"]},
        {"group": "Gaming ecosystem", "examples": ["AIB partners", "Retail channel", "PC OEMs"]}
    ],
    products_to_customers_map={
        "Data center GPUs / platforms": ["Hyperscalers", "AI infrastructure OEMs", "Enterprise / research labs"],
        "Networking (InfiniBand/Ethernet)": ["Hyperscalers", "AI infrastructure OEMs"],
        "Gaming GPUs": ["Gaming ecosystem"],
    },
    value_chain=[
        "AI capex → GPU/cluster demand → packaging/HBM bottlenecks → system throughput/availability → software ecosystem lock-in",
        "Competitive dynamics depend on platform switching costs + time-to-train/infer efficiency and developer tooling."
    ],
    competitive_landscape=["AMD", "Custom accelerators at hyperscalers", "INTC (Gaudi)", "Broadcom (networking adjacency)"],
    risk_struct={
        "macro_risks": ["Risk-off / rates shock reduces capex appetite", "USD strength impacts global demand"],
        "industry_risks": ["AI capex digestion phase", "HBM/packaging supply normalization reduces scarcity pricing"],
        "idiosyncratic_risks": ["Platform concentration with hyperscalers", "Export controls / region restrictions", "Ecosystem backlash if TCO rises too quickly"],
    },
    quant_profile={
        "cycle_exposure": {
            "ai_capex_sensitivity": 0.85,
            "gaming_cycle_sensitivity": 0.55,
            "enterprise_it_cycle": 0.45,
        },
        "supplier_dependency_risk": {
            "foundry_dependence_tsmc": 0.70,
            "advanced_packaging_bottleneck": 0.85,
            "hbm_supply_constraint": 0.75,
        },
        "customer_concentration_risk": {
            "hyperscaler_revenue_weight": 0.80,
            "top_customer_bargaining_power": 0.70,
        },
        "capital_intensity": {
            "internal_capex_burden": 0.25,
            "ecosystem_rnd_intensity": 0.55,
        },
        "moat_profile": {
            "software_ecosystem_lock_in": 0.90,
            "developer_mindshare": 0.85,
            "performance_per_watt_lead": 0.70,
            "switching_costs": 0.80,
        },
    },
    narrative={
        "one_liner": "Platform leader in accelerated computing: strongest when AI capex is expanding and supply is constrained.",
        "bull_case": "AI capex stays durable; platform software lock-in maintains pricing power; networking attach grows; constraints keep scarcity premium.",
        "bear_case": "Capex digestion + normalization of supply compresses pricing; customer bargaining rises; alternatives mature enough to cap growth.",
        "watch_items": ["HBM/packaging capacity", "Hyperscaler capex tone", "Attach rate of networking", "Export controls risk"],
    },
    source_note="Deterministic institutional template (no live fundamentals)."
)

# ---- AMD (Deep) ----
CHAIN["AMD"] = _schema(
    ticker="AMD",
    business_model=[
        "Designs CPUs/GPUs for client, server, and data center acceleration; competes on perf/$ and system-level integration.",
        "Key growth lever: data center GPUs for AI plus server CPUs; client/embedded provide diversification but remain cyclical."
    ],
    revenue_mix={
        "data_center": "growing",
        "client": "cyclical",
        "gaming": "cyclical",
        "embedded": "diversifying",
        "notes": "Mix and margin depend on AI GPU ramp, server CPU competitiveness, and inventory cycles in client/embedded."
    },
    pricing_power="Moderate-to-high in server CPU share gains and AI GPU ramps; weaker in client cycles when supply/demand loosens.",
    suppliers=[
        {"name": "TSMC", "role": "Foundry dependence (advanced nodes)"},
        {"name": "Advanced packaging ecosystem", "role": "Critical for AI GPUs and chiplets"},
        {"name": "Memory/board ecosystem", "role": "HBM for AI GPUs; partner ecosystem for platforms"}
    ],
    customers=[
        {"group": "Hyperscalers / cloud", "examples": ["MSFT", "AMZN", "GOOGL", "META"]},
        {"group": "Enterprise server OEMs", "examples": ["DELL", "HPE", "Lenovo"]},
        {"group": "PC OEM/channel", "examples": ["HPQ", "DELL", "Lenovo", "Retail channel"]},
        {"group": "Console / gaming partners", "examples": ["Sony", "Microsoft"]},
    ],
    products_to_customers_map={
        "Server CPUs (EPYC)": ["Hyperscalers", "Enterprise server OEMs"],
        "Data center GPUs (AI)": ["Hyperscalers", "Enterprise server OEMs"],
        "Client CPUs/GPUs": ["PC OEM/channel"],
        "Semi-custom": ["Console / gaming partners"],
    },
    value_chain=[
        "Server platform competition → share shifts depend on performance, platform stability, and OEM qualification cycles.",
        "AI acceleration ramp depends on software stack maturity and ecosystem parity versus incumbent platforms."
    ],
    competitive_landscape=["NVDA", "INTC", "ARM ecosystem", "Custom accelerators"],
    risk_struct={
        "macro_risks": ["Enterprise IT spending slowdown", "Rates/risk-off reduces capex"],
        "industry_risks": ["Client PC inventory cycles", "AI GPU supply chain constraints (HBM/packaging)"],
        "idiosyncratic_risks": ["Software stack maturity for AI GPUs", "Foundry dependence", "Competitive response in server CPUs"],
    },
    quant_profile={
        "cycle_exposure": {
            "ai_capex_sensitivity": 0.75,
            "enterprise_it_cycle": 0.60,
            "pc_cycle_sensitivity": 0.70,
        },
        "supplier_dependency_risk": {
            "foundry_dependence_tsmc": 0.75,
            "advanced_packaging_bottleneck": 0.65,
            "hbm_supply_constraint": 0.65,
        },
        "customer_concentration_risk": {
            "hyperscaler_weight": 0.60,
            "oem_qualification_concentration": 0.55,
        },
        "capital_intensity": {
            "internal_capex_burden": 0.20,
            "rnd_intensity": 0.60,
        },
        "moat_profile": {
            "cpu_architecture_competitiveness": 0.70,
            "platform_execution": 0.65,
            "ai_stack_momentum": 0.55,
            "switching_costs": 0.55,
        },
    },
    narrative={
        "one_liner": "Challenger platform: upside when AI GPU + server share gains accelerate, but execution and ecosystem maturity matter.",
        "bull_case": "AI GPU ramp plus server CPU share gains; software ecosystem improves; diversified mix reduces volatility.",
        "bear_case": "AI stack adoption lags; client cycle drags; competition compresses margins; foundry constraints limit ramp.",
        "watch_items": ["AI GPU ecosystem/ROCm progress", "Server share trend", "PC inventory/refresh", "Supply chain (HBM/packaging)"],
    },
    source_note="Deterministic institutional template (no live fundamentals)."
)

# ---- AVGO (Deep) ----
CHAIN["AVGO"] = _schema(
    ticker="AVGO",
    business_model=[
        "Diversified semis + infrastructure software; semis anchored by networking, custom ASICs, storage connectivity, and RF components.",
        "Key sensitivity: hyperscaler capex for networking/custom silicon, plus enterprise cycles via software segment."
    ],
    revenue_mix={
        "semis_networking_custom_asic": "large",
        "storage_connectivity": "meaningful",
        "rf_wireless": "meaningful",
        "software": "large/steady",
        "notes": "Custom silicon + networking rides hyperscaler build cycles; software stabilizes but has enterprise renewal sensitivity."
    },
    pricing_power="High in specialized connectivity/custom silicon where switching costs and qualification are deep; moderate in commoditized components.",
    suppliers=[
        {"name": "Foundry partners", "role": "External manufacturing for advanced products"},
        {"name": "Substrate/packaging ecosystem", "role": "Important for high-end networking/custom silicon"},
        {"name": "OEM/channel ecosystem", "role": "Distribution and design-win driven for many components"},
    ],
    customers=[
        {"group": "Hyperscalers / cloud", "examples": ["MSFT", "AMZN", "GOOGL", "META"]},
        {"group": "Networking OEMs", "examples": ["CSCO", "Arista", "Juniper"]},
        {"group": "Storage/enterprise OEMs", "examples": ["DELL", "HPE", "NetApp"]},
        {"group": "Smartphone ecosystem", "examples": ["AAPL (RF/FBAR exposure)", "Android OEMs"]},
    ],
    products_to_customers_map={
        "Networking switching/optical connectivity": ["Hyperscalers", "Networking OEMs"],
        "Custom ASIC / accelerator adjacencies": ["Hyperscalers"],
        "Storage connectivity / controllers": ["Storage/enterprise OEMs"],
        "RF components": ["Smartphone ecosystem"],
        "Infrastructure software": ["Enterprise IT buyers"],
    },
    value_chain=[
        "Hyperscaler capex → networking bandwidth demand → switch/optics/ASIC content increases per rack.",
        "Design-wins are sticky: qualification cycles create inertia and pricing durability."
    ],
    competitive_landscape=["Marvell", "Nvidia (networking)", "Intel", "Qualcomm (RF adjacencies)"],
    risk_struct={
        "macro_risks": ["Enterprise IT slowdown impacts software renewals", "Capex pullback impacts networking spend"],
        "industry_risks": ["Customer concentration in large design-wins", "Inventory correction in connectivity cycles"],
        "idiosyncratic_risks": ["Large customer negotiation power", "Integration/execution risk across segments"],
    },
    quant_profile={
        "cycle_exposure": {
            "hyperscaler_networking_capex": 0.75,
            "enterprise_software_cycle": 0.55,
            "smartphone_cycle": 0.45,
        },
        "supplier_dependency_risk": {
            "foundry_dependence": 0.55,
            "packaging_substrate_constraints": 0.45,
        },
        "customer_concentration_risk": {
            "large_designwin_concentration": 0.70,
            "hyperscaler_mix": 0.65,
        },
        "capital_intensity": {
            "internal_capex_burden": 0.20,
            "rnd_intensity": 0.55,
            "mna_integration_complexity": 0.50,
        },
        "moat_profile": {
            "switching_costs_qualification": 0.80,
            "ip_portfolio_breadth": 0.75,
            "pricing_durability": 0.70,
        },
    },
    narrative={
        "one_liner": "Connectivity + custom silicon leader: strongest when cloud networking spend is expanding; concentration risk is the tradeoff.",
        "bull_case": "Hyperscaler networking + custom silicon demand stays elevated; sticky design-wins sustain margins; software stabilizes earnings.",
        "bear_case": "Capex digestion reduces networking spend; big customers pressure pricing; segment complexity blunts operating leverage.",
        "watch_items": ["Hyperscaler networking spend", "Large design-win renewals", "Enterprise software renewal tone"],
    },
    source_note="Deterministic institutional template (no live fundamentals)."
)




# ============================================================
# Batch 1 Deepening (Group 1): Foundry + WFE stack
# Ticketers: TSM, ASML, AMAT, LRCX, KLAC
# - Institutional ecosystem depth
# - Explicit supplier/customer mapping
# - Quant profiles tuned for foundry/WFE economics
# ============================================================

# ---- TSM (Deep) ----
CHAIN["TSM"] = _schema(
    ticker="TSM",
    business_model=[
        "Pure-play foundry: manufactures wafers for fabless designers (and some IDMs) across leading-edge and specialty/mature nodes.",
        "Economic engine is utilization + node mix (advanced-node share) + pricing discipline, with long lead-times and capex cycles.",
        "Strategic moat comes from process leadership, scale learning, customer trust, and ecosystem enablement (EDA/IP, packaging, CoWoS-class integration).",
    ],
    revenue_mix={
        "leading_edge_nodes": "dominant profit driver",
        "specialty_mature_nodes": "stabilizer + diversification",
        "advanced_packaging": "growing strategic value",
        "notes": (
            "Mix matters: advanced-node wafers carry premium economics but require heavy capex; "
            "specialty nodes add resiliency (auto/industrial/IoT) but face cyclicality and competition."
        ),
    },
    pricing_power=(
        "High at leading edge during tight capacity / critical ramps; more competitive in mature nodes. "
        "Pricing power is strongest when customers prioritize time-to-market, yield, and supply assurance over pure cost."
    ),
    suppliers=[
        {"name": "ASML", "role": "EUV lithography (critical path for leading-edge node progression)"},
        {"name": "Applied Materials / Lam / KLA", "role": "Core process + inspection tool ecosystem"},
        {"name": "Materials & chemicals ecosystem", "role": "Photoresists, specialty gases, CMP slurry, silicon wafers"},
        {"name": "Advanced packaging supply chain", "role": "Substrates, interposers, bumping, 2.5D/3D integration capacity"},
        {"name": "EDA/IP ecosystem", "role": "Design enablement and PDK support influences customer stickiness and tapeout velocity"},
    ],
    customers=[
        {"group": "AI/HPC fabless", "examples": ["NVDA", "AMD", "AVGO", "MRVL"]},
        {"group": "Mobile/consumer platform designers", "examples": ["AAPL-like platform customers", "QCOM", "MediaTek-like peers (industry context)"]},
        {"group": "Auto/industrial designers", "examples": ["NXPI", "STM", "Infineon-like peers (industry context)"]},
        {"group": "IDM / foundry customers", "examples": ["Select IDMs / partners (industry context)"]},
    ],
    products_to_customers_map={
        "Leading-edge wafers (advanced nodes)": ["AI/HPC fabless", "Mobile/consumer platform designers"],
        "Specialty/mature-node wafers": ["Auto/industrial designers", "Mobile/consumer platform designers"],
        "Advanced packaging + integration": ["AI/HPC fabless", "Mobile/consumer platform designers"],
    },
    value_chain=[
        "Customer design cycles → tapeouts → wafer starts → yield learning → utilization → gross margin.",
        "Node transitions (N→N+1) increase tool intensity and capex; early yields & time-to-volume are decisive for customer retention.",
        "Advanced packaging acts as a system-level differentiator when compute is bottlenecked by memory bandwidth and interconnect."
    ],
    competitive_landscape=["Samsung Foundry", "Intel Foundry Services (emerging)", "UMC/GFS (mature nodes)"],
    risk_struct={
        "macro_risks": [
            "Global downturn reduces electronics demand; customers cut wafer starts to work down inventory.",
            "Rates/risk-off can compress multiples and delay discretionary capex by customers."
        ],
        "industry_risks": [
            "Overbuild risk: capex decisions are made ahead of demand; downcycles can last multiple quarters.",
            "Export restrictions and regional policy constraints can reshape end-market access and mix."
        ],
        "idiosyncratic_risks": [
            "Geopolitical risk concentration in a single region.",
            "Tooling/chokepoint dependencies (EUV supply, advanced packaging substrates) can cap ramp speed.",
            "Customer concentration: large platforms can negotiate pricing/priority, especially when supply loosens."
        ],
    },
    quant_profile={
        "cycle_exposure": {
            "semiconductor_inventory_cycle": 0.70,
            "leading_edge_upgrade_cycle": 0.65,
            "ai_hpc_node_mix": 0.60,
        },
        "supplier_dependency_risk": {
            "euv_tool_dependency": 0.75,
            "advanced_packaging_substrate_constraint": 0.70,
            "materials_chokepoints": 0.55,
            "geo_operational_concentration": 0.85,
        },
        "customer_concentration_risk": {
            "platform_customer_weight": 0.75,
            "mix_sensitivity_to_mobile_platforms": 0.60,
        },
        "capital_intensity": {
            "fab_capex_burden": 0.95,
            "process_rnd_intensity": 0.75,
            "fixed_cost_operating_leverage": 0.85,
        },
        "moat_profile": {
            "process_lead": 0.85,
            "yield_learning_scale": 0.85,
            "customer_trust_execution": 0.80,
            "ecosystem_enablement": 0.75,
            "switching_costs_qualification": 0.80,
        },
    },
    narrative={
        "one_liner": "Foundry backbone: upside when utilization + advanced-node mix rise; downside when overcapacity meets inventory digestion.",
        "bull_case": "AI/HPC + leading-edge ramps keep utilization tight; packaging becomes strategic differentiator; pricing discipline holds.",
        "bear_case": "Demand pause creates underutilization; mix shifts to mature nodes; heavy capex + fixed costs pressure margins.",
        "watch_items": ["Utilization", "Advanced-node mix", "EUV deliveries", "Packaging capacity (2.5D/3D)", "Geopolitical headline risk"],
    },
    source_note="Deterministic institutional template (no live fundamentals)."
)

# ---- ASML (Deep) ----
CHAIN["ASML"] = _schema(
    ticker="ASML",
    business_model=[
        "Lithography tools supplier (EUV + DUV) — core choke-point enabling leading-edge node progression and high-volume manufacturing.",
        "Economic engine is systems shipments + service/installed base, driven by long-cycle foundry/IDM capex and technology roadmaps.",
        "Moat is reinforced by extreme complexity, ecosystem partnerships (optics/mechatronics), and multi-year qualification lock-in."
    ],
    revenue_mix={
        "euv_systems": "high-value, high-constraint",
        "duv_systems": "broad base across nodes",
        "service_installed_base": "stabilizer + margin support",
        "notes": "Backlog converts with manufacturing cadence; service provides resilience during shipment pauses."
    },
    pricing_power=(
        "Very high due to uniqueness and qualification barriers, moderated by customer capex timing and export/regulatory constraints."
    ),
    suppliers=[
        {"name": "ZEISS", "role": "Optics partner (critical concentration dependency)"},
        {"name": "High-precision mechatronics supply chain", "role": "Stages, actuators, sensors; long lead-times"},
        {"name": "Electronics/controls suppliers", "role": "Power, control systems, industrial computing"},
        {"name": "Logistics/field service network", "role": "Installation + uptime is part of customer value proposition"},
    ],
    customers=[
        {"group": "Leading-edge foundries", "examples": ["TSM", "Samsung Foundry", "INTC"]},
        {"group": "IDMs at scale", "examples": ["Large memory/logic IDMs (industry context)"]},
        {"group": "China/mature-node buyers (DUV)", "examples": ["Mature-node fabs (industry context)"]},
    ],
    products_to_customers_map={
        "EUV lithography systems": ["Leading-edge foundries", "IDMs at scale"],
        "DUV lithography systems": ["Leading-edge foundries", "IDMs at scale", "China/mature-node buyers (DUV)"],
        "Service + upgrades": ["Leading-edge foundries", "IDMs at scale", "China/mature-node buyers (DUV)"],
    },
    value_chain=[
        "Foundry/IDM roadmaps → node transitions → lithography intensity increases → tool orders → backlog → shipments → installed base service.",
        "EUV availability gates time-to-volume; uptime and service are integral to wafer output and yield."
    ],
    competitive_landscape=["Nikon (DUV)", "Canon (legacy nodes)"],
    risk_struct={
        "macro_risks": ["Capex pauses delay deliveries and acceptance; FX moves affect reported results."],
        "industry_risks": ["WFE downcycle can slow bookings; customer digestion phase reduces near-term demand."],
        "idiosyncratic_risks": ["Export controls constrain deliveries to certain regions", "Supplier concentration in optics/mechatronics", "Manufacturing cadence issues can push revenue timing"],
    },
    quant_profile={
        "cycle_exposure": {
            "wfe_cycle_sensitivity": 0.65,
            "leading_edge_node_transitions": 0.75,
            "installed_base_resilience": 0.35,
        },
        "supplier_dependency_risk": {
            "optics_partner_concentration": 0.85,
            "mechatronics_long_lead": 0.70,
            "regulatory_export_constraints": 0.75,
        },
        "customer_concentration_risk": {
            "top_foundry_customer_weight": 0.70,
            "few_customer_industry_structure": 0.75,
        },
        "capital_intensity": {
            "manufacturing_complexity": 0.70,
            "rnd_intensity": 0.80,
        },
        "moat_profile": {
            "near_monopoly_euv": 0.95,
            "qualification_switching_costs": 0.90,
            "installed_base_service_lock": 0.75,
        },
    },
    narrative={
        "one_liner": "Lithography choke-point: strongest when node transitions accelerate; constrained by export rules and supplier cadence.",
        "bull_case": "Leading-edge transitions stay on schedule; EUV shipments rise; service base compounds resilience.",
        "bear_case": "Capex pauses + export constraints reduce shipments; supplier constraints push revenue timing; backlog de-risks but delays occur.",
        "watch_items": ["EUV shipment cadence", "Export policy", "ZEISS/critical supplier throughput", "Backlog conversion"],
    },
    source_note="Deterministic institutional template (no live fundamentals)."
)

# ---- AMAT (Deep) ----
CHAIN["AMAT"] = _schema(
    ticker="AMAT",
    business_model=[
        "Broad wafer-fab equipment provider across deposition, etch adjacencies, and process steps; benefits from increasing process complexity.",
        "Economic engine is WFE cycle + technology inflections (more layers, new materials, gate-all-around/3D structures) plus services.",
        "Moat comes from breadth across steps, installed base, and process co-optimization with customers."
    ],
    revenue_mix={
        "semi_systems": "cyclical core",
        "applied_global_services": "stabilizer + margin support",
        "display_adjacent": "small/variable",
        "notes": "Service revenue smooths WFE volatility; systems leverage node transitions and capacity adds."
    },
    pricing_power=(
        "Moderate-to-high in process-critical steps and when tool performance is tied to yield; competitive where alternatives exist."
    ),
    suppliers=[
        {"name": "Precision component suppliers", "role": "Vacuum, RF power, motion control subsystems"},
        {"name": "Materials and consumables ecosystem", "role": "Chambers, parts, serviceables support uptime"},
    ],
    customers=[
        {"group": "Foundries", "examples": ["TSM", "GFS", "UMC"]},
        {"group": "Logic IDMs", "examples": ["INTC"]},
        {"group": "Memory makers", "examples": ["MU", "Large memory peers (industry context)"]},
    ],
    products_to_customers_map={
        "Deposition / materials engineering tools": ["Foundries", "Logic IDMs", "Memory makers"],
        "Process/implementation services": ["Foundries", "Logic IDMs", "Memory makers"],
    },
    value_chain=[
        "Device roadmap → process complexity increases → tool intensity per wafer start → WFE orders.",
        "Installed base + service contracts improve visibility and margin stability across cycles."
    ],
    competitive_landscape=["Lam Research", "Tokyo Electron (broadly)", "ASM International (some steps)"],
    risk_struct={
        "macro_risks": ["Global electronics downturn reduces wafer starts and capex."],
        "industry_risks": ["WFE downcycles can be sharp; memory capex is particularly volatile."],
        "idiosyncratic_risks": ["Export controls on advanced tools", "Mix exposure to memory vs logic affects volatility"],
    },
    quant_profile={
        "cycle_exposure": {
            "wfe_cycle_sensitivity": 0.75,
            "memory_capex_volatility": 0.70,
            "logic_node_transitions": 0.60,
        },
        "supplier_dependency_risk": {
            "precision_components": 0.45,
            "regulatory_export_constraints": 0.55,
        },
        "customer_concentration_risk": {
            "top_customer_weight": 0.55,
            "memory_mix_sensitivity": 0.60,
        },
        "capital_intensity": {
            "rnd_intensity": 0.65,
            "manufacturing_complexity": 0.45,
        },
        "moat_profile": {
            "installed_base_services": 0.75,
            "process_cooptimization": 0.70,
            "portfolio_breadth": 0.70,
        },
    },
    narrative={
        "one_liner": "Broad WFE bellwether: wins when complexity and capex rise; cushioned by services but still cyclical.",
        "bull_case": "Node transitions + complexity drive tool intensity; services compound; demand stays tight across logic and memory.",
        "bear_case": "WFE downcycle + memory capex collapse; export constraints; operating leverage swings margins.",
        "watch_items": ["WFE cycle", "Memory capex trend", "Service revenue mix", "Export policy"],
    },
    source_note="Deterministic institutional template (no live fundamentals)."
)

# ---- LRCX (Deep) ----
CHAIN["LRCX"] = _schema(
    ticker="LRCX",
    business_model=[
        "Etch and deposition equipment specialist leveraged to shrinking geometries and 3D device structures.",
        "Economic engine is WFE cycle with higher sensitivity to technology inflections (more etch steps per wafer, 3D NAND/DRAM complexity).",
        "Moat is process-criticality, deep customer integration, and yield-impacting performance."
    ],
    revenue_mix={
        "etch_systems": "core",
        "deposition_clean": "adjacent",
        "services": "stabilizer",
        "notes": "Exposure to memory can increase cyclicality; complexity can offset unit volatility via higher tool intensity."
    },
    pricing_power="Moderate-to-high where etch performance maps directly to yield and throughput; competitive pressure remains in some segments.",
    suppliers=[
        {"name": "Precision component ecosystem", "role": "Vacuum, plasma/RF, controls"},
        {"name": "Serviceables supply chain", "role": "Parts and consumables for uptime"},
    ],
    customers=[
        {"group": "Memory makers", "examples": ["MU", "Large memory peers (industry context)"]},
        {"group": "Foundries/Logic", "examples": ["TSM", "INTC", "GFS"]},
    ],
    products_to_customers_map={
        "Etch tools": ["Memory makers", "Foundries/Logic"],
        "Deposition/clean tools": ["Memory makers", "Foundries/Logic"],
        "Service + parts": ["Memory makers", "Foundries/Logic"],
    },
    value_chain=[
        "Device scaling/3D structures → more etch steps → higher tool intensity → WFE orders.",
        "Memory capex swings can dominate; services helps buffer but does not remove cyclicality."
    ],
    competitive_landscape=["Applied Materials", "Tokyo Electron", "ASM International (some steps)"],
    risk_struct={
        "macro_risks": ["Global downturn reduces wafer starts and capex."],
        "industry_risks": ["Memory capex volatility", "Inventory digestion delays tool demand"],
        "idiosyncratic_risks": ["Export restrictions on advanced tools", "High operating leverage to shipments"],
    },
    quant_profile={
        "cycle_exposure": {
            "wfe_cycle_sensitivity": 0.80,
            "memory_capex_volatility": 0.75,
            "node_complexity_intensity": 0.65,
        },
        "supplier_dependency_risk": {
            "precision_components": 0.45,
            "regulatory_export_constraints": 0.55,
        },
        "customer_concentration_risk": {
            "memory_customer_mix": 0.65,
            "top_customer_weight": 0.55,
        },
        "capital_intensity": {
            "rnd_intensity": 0.65,
            "manufacturing_complexity": 0.45,
        },
        "moat_profile": {
            "process_criticality": 0.70,
            "switching_costs_qualification": 0.65,
            "installed_base_services": 0.65,
        },
    },
    narrative={
        "one_liner": "Etch intensity lever: benefits from scaling/3D complexity, but memory capex swings can dominate near-term volatility.",
        "bull_case": "Complexity wave drives more etch steps; customers invest through cycle; services stabilizes margins.",
        "bear_case": "Memory capex collapses; WFE pause delays shipments; export limits constrain parts of demand.",
        "watch_items": ["Memory capex", "WFE cycle", "Etch intensity indicators", "Export policy"],
    },
    source_note="Deterministic institutional template (no live fundamentals)."
)

# ---- KLAC (Deep) ----
CHAIN["KLAC"] = _schema(
    ticker="KLAC",
    business_model=[
        "Process control and inspection/metrology tools that enable yield ramp and defect detection as devices scale.",
        "Economic engine is complexity (more layers, tighter tolerances) plus installed base/service; often more resilient than pure capacity tools.",
        "Moat comes from deep integration in fab workflows, high switching costs, and mission-critical yield impact."
    ],
    revenue_mix={
        "inspection_metrology_systems": "core",
        "service_installed_base": "meaningful stabilizer",
        "notes": "Yield-driven spend tends to persist during transitions even if overall WFE moderates."
    },
    pricing_power="High where tool performance is directly linked to yield and time-to-volume; supported by switching costs and service footprint.",
    suppliers=[
        {"name": "Optics and precision motion ecosystem", "role": "Critical subsystems"},
        {"name": "Industrial computing/controls", "role": "High-throughput data processing components"},
    ],
    customers=[
        {"group": "Foundries", "examples": ["TSM", "GFS", "UMC"]},
        {"group": "Logic IDMs", "examples": ["INTC"]},
        {"group": "Memory makers", "examples": ["MU", "Large memory peers (industry context)"]},
    ],
    products_to_customers_map={
        "Inspection tools": ["Foundries", "Logic IDMs", "Memory makers"],
        "Metrology/process control": ["Foundries", "Logic IDMs", "Memory makers"],
        "Service + upgrades": ["Foundries", "Logic IDMs", "Memory makers"],
    },
    value_chain=[
        "More layers + smaller features → defect discovery becomes harder → more inspection points per wafer start.",
        "During node ramps, customers prioritize yield learning; process control spend can be stickier than capacity adds."
    ],
    competitive_landscape=["Applied Materials (some metrology)", "Hitachi High-Tech (some inspection)"],
    risk_struct={
        "macro_risks": ["Broad WFE downturn still pressures shipments; service offsets partially."],
        "industry_risks": ["Customer capex timing shifts revenue recognition", "Long lead-time programs can be lumpy"],
        "idiosyncratic_risks": ["Mix exposure to leading-edge transitions; export policy can constrain some demand"],
    },
    quant_profile={
        "cycle_exposure": {
            "wfe_cycle_sensitivity": 0.60,
            "yield_transition_intensity": 0.75,
            "installed_base_resilience": 0.40,
        },
        "supplier_dependency_risk": {
            "optics_components": 0.45,
            "regulatory_export_constraints": 0.45,
        },
        "customer_concentration_risk": {
            "top_customer_weight": 0.55,
            "few_customer_industry_structure": 0.60,
        },
        "capital_intensity": {
            "rnd_intensity": 0.60,
            "manufacturing_complexity": 0.45,
        },
        "moat_profile": {
            "switching_costs_workflow_integration": 0.80,
            "yield_criticality": 0.80,
            "installed_base_service_lock": 0.75,
        },
    },
    narrative={
        "one_liner": "Yield gatekeeper: benefits from complexity and node ramps; comparatively resilient via installed base and high switching costs.",
        "bull_case": "Leading-edge transitions accelerate; customers invest in yield learning; service mix supports margins.",
        "bear_case": "WFE downturn reduces new system shipments; spending shifts toward maintenance; export constraints reduce some orders.",
        "watch_items": ["Leading-edge ramp cadence", "Service mix", "Inspection intensity indicators", "Export policy"],
    },
    source_note="Deterministic institutional template (no live fundamentals)."
)


# ============================================================
# Batch 2 Deepening (Group 2): Analog / Auto / Industrial backbone
# Tickers: TXN, ADI, NXPI, ON, STM, MCHP
# - Institutional ecosystem depth
# - Explicit supplier/customer mapping
# - Quant profiles tuned for analog/auto/industrial economics
# ============================================================

# ---- TXN (Deep) ----
CHAIN["TXN"] = _schema(
    ticker="TXN",
    business_model=[
        "Analog + embedded processing supplier with a broad catalog and very long product life cycles.",
        "Design-ins into industrial and automotive systems create sticky revenue streams; volume is steady but can swing with macro/industrial cycles.",
        "Economic engine: breadth + availability + lifecycle longevity, supported by manufacturing strategy and channel reach."
    ],
    revenue_mix={
        "industrial": "large",
        "automotive": "large",
        "personal_electronics": "smaller",
        "communications": "smaller",
        "notes": "Industrial/auto dominate; personal electronics adds cyclicality but typically smaller relative to core."
    },
    pricing_power=(
        "Generally strong: analog design-ins are sticky and switching can be costly, but pricing power weakens during channel corrections."
    ),
    suppliers=[
        {"name": "Wafer + substrate ecosystem", "role": "Core manufacturing inputs and specialty materials"},
        {"name": "OSAT / packaging partners", "role": "Assembly/test capacity (varies by device mix)"},
        {"name": "Distribution/channel partners", "role": "Inventory positioning and reach into long-tail industrial customers"},
    ],
    customers=[
        {"group": "Industrial OEMs", "examples": ["Factory automation", "Power/energy", "Instrumentation", "Industrial controls"]},
        {"group": "Automotive OEMs/Tier1", "examples": ["Tier1 suppliers", "Body/ADAS subsystems", "EV powertrain subsystems"]},
        {"group": "Consumer/OEM", "examples": ["Appliance OEMs", "Personal electronics OEMs"]},
    ],
    products_to_customers_map={
        "Power management (PMICs, regulators)": ["Industrial OEMs", "Automotive OEMs/Tier1", "Consumer/OEM"],
        "Signal chain (amplifiers, data converters)": ["Industrial OEMs", "Automotive OEMs/Tier1"],
        "Embedded processing (MCUs/DSPs)": ["Industrial OEMs", "Automotive OEMs/Tier1"],
        "Interface/connectivity (legacy & specialty)": ["Industrial OEMs", "Consumer/OEM"],
    },
    value_chain=[
        "System design cycle → analog selection/design-in → qualification → production ramps → multi-year replacement/maintenance demand.",
        "Channel inventory acts as a 'buffer' and can amplify cyclicality (corrections after over-ordering)."
    ],
    competitive_landscape=["ADI", "NXPI (MCUs)", "MCHP", "STM", "Broad catalog peers (industry context)"],
    risk_struct={
        "macro_risks": ["Industrial slowdown reduces new orders and triggers channel correction", "Auto production volatility impacts short-term demand"],
        "industry_risks": ["Inventory corrections can be multi-quarter", "Commoditization pressure in certain lower-end analog categories"],
        "idiosyncratic_risks": ["Channel visibility risk (sell-in vs sell-through)", "Manufacturing strategy execution (cost, availability)"],
    },
    quant_profile={
        "cycle_exposure": {
            "industrial_cycle": 0.60,
            "auto_cycle": 0.55,
            "channel_inventory_correction": 0.65,
        },
        "supplier_dependency_risk": {
            "manufacturing_inputs_dependency": 0.35,
            "osat_capacity_dependency": 0.30,
        },
        "customer_concentration_risk": {
            "customer_diversification": 0.25,
            "auto_mix_concentration": 0.45,
        },
        "capital_intensity": {
            "capex_intensity": 0.60,
            "fixed_cost_operating_leverage": 0.55,
            "rnd_intensity": 0.50,
        },
        "moat_profile": {
            "catalog_breadth": 0.80,
            "long_lifecycle_design_ins": 0.80,
            "switching_costs": 0.70,
            "availability_reputation": 0.65,
        },
    },
    narrative={
        "one_liner": "Analog catalog compounder: steady design-in economics with cyclical channel corrections as the main volatility driver.",
        "bull_case": "Industrial/auto stabilize; channel normalizes; long-tail catalog keeps margins resilient; steady share via availability.",
        "bear_case": "Prolonged industrial slowdown triggers extended correction; pricing softens in weaker categories; visibility declines.",
        "watch_items": ["Channel inventory", "Industrial order trends", "Auto build schedules", "Lead times/availability signals"],
    },
    source_note="Deterministic institutional template (no live fundamentals)."
)

# ---- ADI (Deep) ----
CHAIN["ADI"] = _schema(
    ticker="ADI",
    business_model=[
        "High-performance analog + mixed-signal supplier (signal chain, precision conversion) with deep content in industrial/auto/communications.",
        "Economic engine: performance differentiation + sticky design-ins, complemented by a large installed base and long customer qualification cycles.",
        "Often less volume-driven than commodity analog; more tied to system complexity and high-value end applications."
    ],
    revenue_mix={
        "industrial": "dominant",
        "automotive": "meaningful",
        "communications": "meaningful",
        "consumer": "smaller",
        "notes": "Industrial typically largest; comms can be cyclical with infrastructure spending."
    },
    pricing_power=(
        "Strong in precision/performance categories where qualification is deep; weaker in broader commoditized segments."
    ),
    suppliers=[
        {"name": "Wafer manufacturing ecosystem", "role": "Mixed internal/external fabs depending on product"},
        {"name": "Packaging/assembly partners", "role": "Complex packaging for high-performance mixed-signal devices"},
        {"name": "Test/measurement ecosystem", "role": "High test complexity for precision products"},
    ],
    customers=[
        {"group": "Industrial OEMs", "examples": ["Factory automation", "Process control", "Energy/power", "Aerospace/defense-like adjacencies"]},
        {"group": "Automotive OEMs/Tier1", "examples": ["ADAS", "Powertrain", "In-cabin sensing", "EV subsystems"]},
        {"group": "Comms infrastructure", "examples": ["Wireless infrastructure OEMs", "Data comm equipment OEMs"]},
    ],
    products_to_customers_map={
        "Precision data converters": ["Industrial OEMs", "Comms infrastructure", "Automotive OEMs/Tier1"],
        "Signal chain (amps, sensors interfaces)": ["Industrial OEMs", "Automotive OEMs/Tier1"],
        "Power management & mixed-signal": ["Industrial OEMs", "Automotive OEMs/Tier1"],
        "RF/comm front-end mixed-signal": ["Comms infrastructure"],
    },
    value_chain=[
        "High-value system design → long qualification → stable multi-year production; performance requirements reduce substitution risk.",
        "Comms infra cycles can spike demand when standards upgrade and then pause in digestion phases."
    ],
    competitive_landscape=["TXN", "NXPI (some mixed-signal)", "Broad analog peers (industry context)"],
    risk_struct={
        "macro_risks": ["Industrial demand softening impacts bookings", "Capex digestion in comms infrastructure"],
        "industry_risks": ["Channel corrections after supply tightness", "Pricing pressure in lower differentiation categories"],
        "idiosyncratic_risks": ["Mix sensitivity to industrial vs comms cycles", "Supply chain execution for complex devices"],
    },
    quant_profile={
        "cycle_exposure": {
            "industrial_cycle": 0.60,
            "comms_infra_cycle": 0.55,
            "auto_cycle": 0.45,
        },
        "supplier_dependency_risk": {
            "manufacturing_mix_dependency": 0.40,
            "complex_packaging_dependency": 0.40,
        },
        "customer_concentration_risk": {
            "customer_diversification": 0.30,
            "comms_program_concentration": 0.40,
        },
        "capital_intensity": {
            "rnd_intensity": 0.55,
            "test_complexity": 0.55,
            "capex_intensity": 0.50,
        },
        "moat_profile": {
            "performance_differentiation": 0.80,
            "qualification_switching_costs": 0.75,
            "installed_base_stickiness": 0.65,
        },
    },
    narrative={
        "one_liner": "Precision analog leader: best when industrial activity stabilizes and comms cycles re-accelerate; sticky design-ins support durability.",
        "bull_case": "Industrial rebounds; comms upgrades resume; high-performance mix sustains margins and pricing.",
        "bear_case": "Industrial stays weak; comms digestion persists; channel correction reduces near-term visibility.",
        "watch_items": ["Industrial order tone", "Comms infra spend", "Channel inventory", "High-performance mix"],
    },
    source_note="Deterministic institutional template (no live fundamentals)."
)

# ---- NXPI (Deep) ----
CHAIN["NXPI"] = _schema(
    ticker="NXPI",
    business_model=[
        "Auto/industrial semiconductor supplier with strong positions in MCUs, secure connectivity, and networking for vehicles and embedded systems.",
        "Economic engine: auto design-in cycles (sticky, multi-year) + increasing electronics content per vehicle; industrial adds cyclicality.",
        "Qualification and functional safety requirements increase switching costs, supporting durable program revenue once won."
    ],
    revenue_mix={
        "automotive": "dominant",
        "industrial_iot": "meaningful",
        "mobile_adjacent": "smaller",
        "notes": "Auto provides stickiness; industrial can swing with macro; connectivity/security is a structural tailwind."
    },
    pricing_power=(
        "Moderate-to-strong in automotive programs due to qualification and safety; weaker during broad auto downturns or supply normalization."
    ),
    suppliers=[
        {"name": "Foundry partners", "role": "External manufacturing dependence; lead-time planning important"},
        {"name": "OSAT/packaging ecosystem", "role": "Assembly/test capacity and automotive-quality requirements"},
        {"name": "IP/EDA ecosystem", "role": "Design enablement and safety certification flows"},
    ],
    customers=[
        {"group": "Automotive Tier1", "examples": ["ADAS Tier1 suppliers", "Body electronics suppliers", "Powertrain suppliers"]},
        {"group": "Automotive OEMs", "examples": ["Global auto OEMs (industry context)"]},
        {"group": "Industrial OEMs", "examples": ["Factory automation", "Energy", "Embedded/IoT OEMs"]},
    ],
    products_to_customers_map={
        "Automotive MCUs": ["Automotive Tier1", "Automotive OEMs"],
        "Secure connectivity (NFC/UWB/secure elements)": ["Automotive Tier1", "Industrial OEMs"],
        "In-vehicle networking (CAN/LIN/Ethernet)": ["Automotive Tier1"],
        "Industrial/IoT processors": ["Industrial OEMs"],
    },
    value_chain=[
        "Vehicle platform planning → design-in/qualification (multi-year) → SOP launch → stable multi-year production → refresh cycles.",
        "Electronics content growth (ADAS, electrification, connectivity) can outpace unit volumes over a cycle."
    ],
    competitive_landscape=["STM", "Infineon-like peers (industry context)", "Renesas-like peers (industry context)", "TXN (analog adjacencies)"],
    risk_struct={
        "macro_risks": ["Auto production downturn reduces near-term units", "Industrial slowdown impacts non-auto demand"],
        "industry_risks": ["Supply normalization can trigger inventory corrections", "Program timing risk (platform delays)"],
        "idiosyncratic_risks": ["Foundry dependence and allocation risk", "Customer concentration in large auto platforms"],
    },
    quant_profile={
        "cycle_exposure": {
            "auto_cycle": 0.65,
            "industrial_cycle": 0.55,
            "program_timing_risk": 0.55,
        },
        "supplier_dependency_risk": {
            "foundry_dependence": 0.60,
            "automotive_quality_supply_chain": 0.45,
        },
        "customer_concentration_risk": {
            "auto_platform_concentration": 0.65,
            "tier1_dependency": 0.55,
        },
        "capital_intensity": {
            "rnd_intensity": 0.55,
            "qualification_costs": 0.55,
            "capex_intensity": 0.40,
        },
        "moat_profile": {
            "auto_design_in_stickiness": 0.80,
            "functional_safety_barriers": 0.75,
            "security_connectivity_ip": 0.65,
        },
    },
    narrative={
        "one_liner": "Automotive design-in compounder: durable once programs launch, but exposed to unit cycles and platform timing.",
        "bull_case": "Auto electronics content rises (ADAS/connectivity/EV); platform wins compound; industrial stabilizes.",
        "bear_case": "Auto downturn + inventory correction; platform delays; foundry constraints or pricing pressure in normalization.",
        "watch_items": ["Auto build forecasts", "Program launches/SOP timing", "Channel inventory", "Foundry allocation signals"],
    },
    source_note="Deterministic institutional template (no live fundamentals)."
)

# ---- ON (Deep) ----
CHAIN["ON"] = _schema(
    ticker="ON",
    business_model=[
        "Power and sensing semiconductor supplier with strong exposure to automotive electrification and industrial power management.",
        "Economic engine: content per vehicle (power modules, inverters, charging) + industrial power demand; cycles can be amplified by capacity additions.",
        "Key differentiator is power device portfolio (Si/SiC), manufacturing execution, and long-term customer programs."
    ],
    revenue_mix={
        "automotive": "large",
        "industrial": "meaningful",
        "other": "smaller",
        "notes": "Auto electrification is structural; industrial is cyclical; SiC adoption pace is a key swing factor."
    },
    pricing_power=(
        "Strong during tight supply and high SiC demand; can weaken if capacity outpaces demand or customers dual-source aggressively."
    ),
    suppliers=[
        {"name": "SiC materials/substrate ecosystem", "role": "Substrate availability and quality affect yields/cost"},
        {"name": "Wafer fab / internal manufacturing", "role": "Execution and utilization drive margin volatility"},
        {"name": "Packaging/assembly partners", "role": "Auto-grade reliability requirements add complexity"},
    ],
    customers=[
        {"group": "Automotive OEMs/Tier1", "examples": ["EV programs", "Inverter/charger Tier1 suppliers", "Auto OEMs (industry context)"]},
        {"group": "Industrial power OEMs", "examples": ["Power supplies", "Renewables/inverters", "Industrial drives"]},
    ],
    products_to_customers_map={
        "SiC power devices/modules": ["Automotive OEMs/Tier1", "Industrial power OEMs"],
        "Silicon power MOSFETs/IGBTs": ["Automotive OEMs/Tier1", "Industrial power OEMs"],
        "Sensing (image/sensors)": ["Automotive OEMs/Tier1", "Industrial power OEMs"],
    },
    value_chain=[
        "EV adoption → inverter/charging content per vehicle rises → SiC penetration increases → supply chain (substrate/yields) becomes the bottleneck.",
        "Capacity builds are long-lead; mismatches between demand and capacity drive pricing and utilization swings."
    ],
    competitive_landscape=["Infineon-like peers (industry context)", "STM", "Wolfspeed (SiC materials)", "Other power semis peers"],
    risk_struct={
        "macro_risks": ["EV demand slowdown reduces near-term growth", "Industrial downturn impacts power demand"],
        "industry_risks": ["SiC supply/demand imbalance can compress pricing", "Inventory corrections after tight supply periods"],
        "idiosyncratic_risks": ["Execution risk in SiC ramp (yields/cost)", "Customer concentration in major EV programs"],
    },
    quant_profile={
        "cycle_exposure": {
            "ev_cycle": 0.70,
            "auto_cycle": 0.60,
            "industrial_cycle": 0.55,
        },
        "supplier_dependency_risk": {
            "sic_substrate_dependency": 0.70,
            "manufacturing_execution_risk": 0.60,
        },
        "customer_concentration_risk": {
            "auto_program_concentration": 0.65,
            "large_customer_bargaining_power": 0.55,
        },
        "capital_intensity": {
            "capex_intensity": 0.75,
            "fixed_cost_operating_leverage": 0.70,
            "rnd_intensity": 0.50,
        },
        "moat_profile": {
            "power_domain_expertise": 0.65,
            "auto_qualification_stickiness": 0.60,
            "portfolio_breadth": 0.55,
        },
    },
    narrative={
        "one_liner": "Auto power lever: structural EV content tailwind with real cyclicality from capacity builds and program concentration.",
        "bull_case": "EV/industrial demand holds; SiC penetration rises; execution yields improve and pricing stays rational.",
        "bear_case": "EV slowdown + capacity overshoot; pricing compresses; utilization drops; program concentration amplifies downside.",
        "watch_items": ["EV demand pace", "SiC capacity/yields", "Auto program wins", "Utilization + pricing signals"],
    },
    source_note="Deterministic institutional template (no live fundamentals)."
)

# ---- STM (Deep) ----
CHAIN["STM"] = _schema(
    ticker="STM",
    business_model=[
        "Broad industrial/automotive semiconductor supplier (MCUs, power, analog) with exposure to embedded control and electrification trends.",
        "Economic engine: auto/industrial design-ins and broad portfolio; mix sensitivity to industrial cycles and auto volumes.",
        "Differentiation comes from portfolio breadth, long customer programs, and power/MCU integration in embedded systems."
    ],
    revenue_mix={
        "automotive": "large",
        "industrial": "large",
        "personal_electronics": "smaller",
        "notes": "Industrial/auto dominate; personal electronics adds cyclical swings in some periods."
    },
    pricing_power=(
        "Moderate: design-ins support stickiness, but competitive intensity and supply normalization can pressure pricing."
    ),
    suppliers=[
        {"name": "Manufacturing footprint (internal + external)", "role": "Mix of internal fabs and foundry partners"},
        {"name": "Packaging/assembly ecosystem", "role": "Auto-grade reliability requirements"},
        {"name": "Materials/substrates", "role": "Power devices can have specialized materials needs"},
    ],
    customers=[
        {"group": "Automotive OEMs/Tier1", "examples": ["Body/ADAS subsystems", "Powertrain/EV subsystems", "Tier1 suppliers"]},
        {"group": "Industrial OEMs", "examples": ["Automation", "Energy", "Embedded/IoT OEMs"]},
        {"group": "Consumer/OEM", "examples": ["Appliances", "Personal electronics OEMs"]},
    ],
    products_to_customers_map={
        "MCUs/embedded processors": ["Automotive OEMs/Tier1", "Industrial OEMs", "Consumer/OEM"],
        "Power devices/modules": ["Automotive OEMs/Tier1", "Industrial OEMs"],
        "Analog/mixed-signal": ["Automotive OEMs/Tier1", "Industrial OEMs"],
    },
    value_chain=[
        "Embedded system design → qualification → multi-year production; portfolio breadth allows wallet-share expansion within programs.",
        "Industrial/auto cycles can cause inventory corrections; design-in stickiness reduces churn but not volume cyclicality."
    ],
    competitive_landscape=["NXPI", "Infineon-like peers (industry context)", "Renesas-like peers (industry context)", "TXN (analog adjacencies)"],
    risk_struct={
        "macro_risks": ["Industrial slowdown impacts broad demand", "Auto production volatility shifts near-term units"],
        "industry_risks": ["Inventory corrections post tight supply", "Competitive pricing in commoditized categories"],
        "idiosyncratic_risks": ["Manufacturing mix execution", "Exposure to a few large programs/verticals"],
    },
    quant_profile={
        "cycle_exposure": {
            "industrial_cycle": 0.65,
            "auto_cycle": 0.55,
            "inventory_correction_risk": 0.60,
        },
        "supplier_dependency_risk": {
            "manufacturing_mix_dependency": 0.50,
            "specialty_materials_dependency": 0.45,
        },
        "customer_concentration_risk": {
            "program_concentration": 0.55,
            "auto_mix_concentration": 0.55,
        },
        "capital_intensity": {
            "capex_intensity": 0.60,
            "fixed_cost_operating_leverage": 0.55,
            "rnd_intensity": 0.55,
        },
        "moat_profile": {
            "portfolio_breadth": 0.65,
            "auto_design_in_stickiness": 0.65,
            "embedded_ecosystem": 0.55,
        },
    },
    narrative={
        "one_liner": "Industrial/auto portfolio player: steady design-ins but meaningful cycle sensitivity through industrial demand and inventory corrections.",
        "bull_case": "Industrial improves; auto content rises; portfolio breadth increases wallet share; pricing remains rational.",
        "bear_case": "Industrial stays weak; inventory correction extends; competition pressures pricing and margins.",
        "watch_items": ["Industrial order trends", "Auto builds", "Inventory levels", "Manufacturing utilization"],
    },
    source_note="Deterministic institutional template (no live fundamentals)."
)

# ---- MCHP (Deep) ----
CHAIN["MCHP"] = _schema(
    ticker="MCHP",
    business_model=[
        "Microcontrollers + analog supplier with heavy industrial and automotive exposure; long design cycles and broad catalog.",
        "Economic engine: design-ins and embedded control adoption, with cyclicality driven by industrial demand and channel inventory.",
        "Once designed in, products can ship for many years; variability often comes from customer inventory adjustments."
    ],
    revenue_mix={
        "industrial": "large",
        "automotive": "meaningful",
        "other": "smaller",
        "notes": "Industrial drives much of demand; auto adds long-cycle stickiness; channel dynamics can amplify swings."
    },
    pricing_power="Moderate: design-in stickiness supports pricing, but channel corrections and competition can reduce near-term leverage.",
    suppliers=[
        {"name": "Manufacturing ecosystem (internal/external)", "role": "Mixed footprint; lead-time management important"},
        {"name": "OSAT/packaging partners", "role": "Assembly/test capacity and reliability requirements"},
        {"name": "Distribution/channel", "role": "Broad reach into long-tail industrial customers"},
    ],
    customers=[
        {"group": "Industrial OEMs", "examples": ["Automation", "Embedded controls", "Energy", "Instrumentation"]},
        {"group": "Automotive OEMs/Tier1", "examples": ["Body electronics", "Power/controls subsystems"]},
    ],
    products_to_customers_map={
        "Microcontrollers (MCUs)": ["Industrial OEMs", "Automotive OEMs/Tier1"],
        "Analog/power management": ["Industrial OEMs", "Automotive OEMs/Tier1"],
        "Connectivity/interface": ["Industrial OEMs"],
    },
    value_chain=[
        "Embedded platform selection → long qualification → steady shipments; weakness usually shows up as channel correction, not immediate design loss.",
        "Industrial spending tends to be more sensitive to macro; backlog burn can mask downturns before orders re-price."
    ],
    competitive_landscape=["TXN (MCU/analog adjacencies)", "NXPI (auto MCUs)", "STM", "Other MCU peers (industry context)"],
    risk_struct={
        "macro_risks": ["Industrial downturn reduces new orders and extends correction"],
        "industry_risks": ["Channel inventory swings can be multi-quarter", "Pricing pressure if competitors chase share in downturn"],
        "idiosyncratic_risks": ["Mix sensitivity to industrial programs", "Visibility risk in distribution-heavy models"],
    },
    quant_profile={
        "cycle_exposure": {
            "industrial_cycle": 0.70,
            "auto_cycle": 0.45,
            "channel_inventory_correction": 0.70,
        },
        "supplier_dependency_risk": {
            "manufacturing_mix_dependency": 0.45,
            "osat_capacity_dependency": 0.35,
        },
        "customer_concentration_risk": {
            "customer_diversification": 0.35,
            "industrial_program_concentration": 0.55,
        },
        "capital_intensity": {
            "capex_intensity": 0.55,
            "fixed_cost_operating_leverage": 0.55,
            "rnd_intensity": 0.50,
        },
        "moat_profile": {
            "long_design_cycles": 0.70,
            "catalog_breadth": 0.65,
            "switching_costs": 0.60,
        },
    },
    narrative={
        "one_liner": "Embedded MCU catalog: sticky design-ins with cycle volatility mostly expressed through industrial demand and channel corrections.",
        "bull_case": "Industrial stabilizes; channel normalizes; long-cycle design-ins support steady shipments and margin recovery.",
        "bear_case": "Industrial weakness persists; customers destock; competitive pricing pressure reduces leverage.",
        "watch_items": ["Industrial order trends", "Channel inventory", "Backlog burn", "Lead times"],
    },
    source_note="Deterministic institutional template (no live fundamentals)."
)


# ============================================================
# Batch 3 Deepening (Group 3): Connectivity / Networking / RF stack
# Tickers: MRVL, QCOM, SWKS, QRVO
# - Institutional ecosystem depth
# - Explicit supplier/customer mapping
# - Quant profiles tuned for hyperscaler capex + handset cycles + concentration risk
# ============================================================

# ---- MRVL (Deep) ----
CHAIN["MRVL"] = _schema(
    ticker="MRVL",
    business_model=[
        "Networking silicon + storage/DPUs/custom silicon exposure, with meaningful sensitivity to hyperscaler and networking OEM capex cycles.",
        "Economic engine: design wins in high-speed connectivity (switching/optical DSP/DPUs) and custom programs; once qualified, content tends to be sticky.",
        "Upside is tied to bandwidth growth per rack and expansion of custom silicon; downside comes from capex digestion and program timing slips."
    ],
    revenue_mix={
        "cloud_datacenter_connectivity": "large",
        "carrier_enterprise_networking": "meaningful",
        "storage_connectivity": "meaningful/variable",
        "custom_silicon": "growing option",
        "notes": "Mix varies with hyperscaler build cadence and enterprise networking cycles; custom programs can be lumpy but sticky."
    },
    pricing_power=(
        "Strong in qualified design wins and custom programs due to switching costs and long qualification cycles; weaker in competitive segments."
    ),
    suppliers=[
        {"name": "Foundry partners", "role": "Advanced node reliance (performance/watt constraints)"},
        {"name": "Advanced packaging ecosystem", "role": "High-speed IO and integration can require more complex packaging"},
        {"name": "SerDes/PHY IP ecosystem", "role": "High-speed interface IP and validation ecosystem"},
        {"name": "Optics/connector ecosystem", "role": "Adjacent system dependencies influence overall platform adoption"},
    ],
    customers=[
        {"group": "Hyperscalers / cloud operators", "examples": ["MSFT", "AMZN", "GOOGL", "META", "ORCL"]},
        {"group": "Networking OEMs", "examples": ["CSCO", "Arista-like peers (industry context)", "Juniper-like peers (industry context)"]},
        {"group": "Storage/enterprise OEMs", "examples": ["DELL", "HPE", "NetApp-like peers (industry context)"]},
    ],
    products_to_customers_map={
        "Switching / interconnect silicon": ["Hyperscalers / cloud operators", "Networking OEMs"],
        "Optical DSP / high-speed PHY": ["Hyperscalers / cloud operators", "Networking OEMs"],
        "DPUs / data processing acceleration": ["Hyperscalers / cloud operators"],
        "Storage connectivity/controllers": ["Storage/enterprise OEMs"],
        "Custom silicon programs": ["Hyperscalers / cloud operators", "Networking OEMs"],
    },
    value_chain=[
        "Cloud AI + data growth → bandwidth per rack increases → switch/optical interconnect content rises.",
        "Design win → long qualification → ramp; program timing and customer digestion phases drive quarter-to-quarter volatility.",
        "Custom silicon scales when customers want differentiated TCO/performance; sticky once integrated into platform."
    ],
    competitive_landscape=["AVGO", "NVDA (networking adjacency)", "INTC (some datacenter silicon)", "Other networking silicon peers"],
    risk_struct={
        "macro_risks": ["Capex slowdown reduces hyperscaler/network spend", "Enterprise IT pauses delay upgrades"],
        "industry_risks": ["Customer digestion phase after buildouts", "Inventory corrections in networking supply chains"],
        "idiosyncratic_risks": ["Program concentration risk (few big design wins)", "Foundry dependence", "Timing slips in custom silicon ramps"],
    },
    quant_profile={
        "cycle_exposure": {
            "hyperscaler_capex": 0.75,
            "networking_upgrade_cycle": 0.65,
            "enterprise_it_cycle": 0.55,
        },
        "supplier_dependency_risk": {
            "foundry_dependence": 0.65,
            "packaging_integration_dependency": 0.45,
            "high_speed_validation_complexity": 0.55,
        },
        "customer_concentration_risk": {
            "designwin_concentration": 0.75,
            "hyperscaler_mix_weight": 0.70,
        },
        "capital_intensity": {
            "rnd_intensity": 0.65,
            "program_nre_intensity": 0.60,
        },
        "moat_profile": {
            "qualification_switching_costs": 0.70,
            "high_speed_ip_and_validation": 0.65,
            "platform_stickiness": 0.65,
        },
    },
    narrative={
        "one_liner": "Cloud connectivity lever: wins when hyperscaler bandwidth/capex expands; risk is program concentration and digestion cycles.",
        "bull_case": "Hyperscaler capex re-accelerates; bandwidth per rack rises; custom programs scale; stickiness supports margins.",
        "bear_case": "Capex digestion extends; networking inventory correction; a few program delays drive outsized revenue swings.",
        "watch_items": ["Hyperscaler capex tone", "Networking inventory", "Custom silicon pipeline", "Optical interconnect cycle"],
    },
    source_note="Deterministic institutional template (no live fundamentals)."
)

# ---- QCOM (Deep) ----
CHAIN["QCOM"] = _schema(
    ticker="QCOM",
    business_model=[
        "Wireless platform supplier: modem/RF + application SoCs; anchored in smartphones with expansion into auto and IoT/edge.",
        "Economic engine: handset units + content per device (modem + RF front-end) and licensing/IP monetization (where applicable).",
        "Moat in cellular IP and integration; key risks are handset cyclicality, OEM concentration, and competitive/in-sourcing pressure."
    ],
    revenue_mix={
        "handsets": "dominant",
        "rf_front_end": "meaningful",
        "auto": "growing option",
        "iot_edge": "meaningful/variable",
        "notes": "Handsets drive cyclicality; auto/IoT diversify but take time to offset major handset swings."
    },
    pricing_power=(
        "Moderate-to-strong when leading in modem/RF integration and premium tiers; weaker in volume tiers and during handset downcycles."
    ),
    suppliers=[
        {"name": "Foundry partners", "role": "Advanced node dependence for flagship platforms"},
        {"name": "OSAT/packaging ecosystem", "role": "Complex packaging and test for RF/SoC integration"},
        {"name": "RF component ecosystem", "role": "Filters/PA/LNA/antenna tuning interplay affects platform performance"},
        {"name": "Software/OS ecosystem", "role": "Android ecosystem cadence influences platform cycles"},
    ],
    customers=[
        {"group": "Android OEMs", "examples": ["Samsung-like peers (industry context)", "Xiaomi-like peers (industry context)", "OPPO/Vivo-like peers (industry context)"]},
        {"group": "Premium smartphone platforms", "examples": ["Select premium OEMs (industry context)"]},
        {"group": "Automotive/tiers", "examples": ["Auto OEM programs", "Tier1 suppliers"]},
        {"group": "IoT/edge OEMs", "examples": ["Consumer IoT", "Industrial IoT OEMs"]},
    ],
    products_to_customers_map={
        "Modem + cellular connectivity": ["Android OEMs", "Premium smartphone platforms", "Automotive/tiers", "IoT/edge OEMs"],
        "Application SoCs (Snapdragon-like)": ["Android OEMs", "Premium smartphone platforms"],
        "RF front-end platforms": ["Android OEMs", "Premium smartphone platforms"],
        "Auto connectivity/compute": ["Automotive/tiers"],
        "IoT/edge platforms": ["IoT/edge OEMs"],
    },
    value_chain=[
        "Standards upgrades → platform refresh cycles → OEM design wins → seasonal ramps → channel inventory adjustments.",
        "Modem/RF integration improves power/performance; content per device rises with more bands and complexity, but OEMs may multi-source.",
        "Auto programs have long lead times and sticky revenue once SOP begins."
    ],
    competitive_landscape=["MediaTek-like peers (industry context)", "AAPL in-sourcing risk (where applicable)", "RF peers (SWKS/QRVO adjacencies)"],
    risk_struct={
        "macro_risks": ["Consumer demand downturn reduces handset units", "FX and regional demand swings affect OEM ordering"],
        "industry_risks": ["Handset inventory corrections can be sharp", "Pricing pressure in mid/low tiers"],
        "idiosyncratic_risks": ["OEM concentration risk", "In-sourcing/competitive modem pressure", "Regulatory/IP disputes (headline risk)"],
    },
    quant_profile={
        "cycle_exposure": {
            "smartphone_cycle": 0.80,
            "seasonality_ramp": 0.65,
            "auto_program_long_cycle": 0.40,
            "iot_edge_cycle": 0.45,
        },
        "supplier_dependency_risk": {
            "foundry_dependence": 0.70,
            "rf_integration_supply_chain": 0.55,
        },
        "customer_concentration_risk": {
            "top_oem_weight": 0.70,
            "android_oem_concentration": 0.60,
        },
        "capital_intensity": {
            "rnd_intensity": 0.70,
            "platform_nre_intensity": 0.65,
        },
        "moat_profile": {
            "cellular_ip_strength": 0.80,
            "platform_integration": 0.65,
            "ecosystem_presence": 0.60,
        },
    },
    narrative={
        "one_liner": "Wireless platform lever: dominant handset exposure with IP moat; diversification helps but smartphone cycle remains the key swing.",
        "bull_case": "Handset recovery + premium content gains; RF attach improves; auto/IoT ramps add steadier growth.",
        "bear_case": "Handset weakness persists; OEM concentration and in-sourcing pressure compress content; inventory correction hits shipments.",
        "watch_items": ["Handset unit trends", "OEM share shifts", "RF content/attach", "Auto backlog/SOP cadence"],
    },
    source_note="Deterministic institutional template (no live fundamentals)."
)

# ---- SWKS (Deep) ----
CHAIN["SWKS"] = _schema(
    ticker="SWKS",
    business_model=[
        "RF front-end components/modules supplier leveraged to smartphone units and content per device (more bands, 5G complexity).",
        "Economic engine: OEM design wins + content share in premium platforms; volatility amplified by handset cycle and customer concentration.",
        "Moat depends on integration, module performance, and long qualification cycles; risk rises if a major customer reduces share."
    ],
    revenue_mix={
        "smartphone_rf": "dominant",
        "broad_markets": "smaller",
        "notes": "Handsets dominate cyclicality; broad markets can diversify but usually not enough to offset big handset swings quickly."
    },
    pricing_power=(
        "Moderate: strong when content share is high in premium devices; weaker in downcycles and where OEMs multi-source aggressively."
    ),
    suppliers=[
        {"name": "Wafer + process ecosystem", "role": "Specialty RF processes and yield execution"},
        {"name": "Packaging/assembly ecosystem", "role": "Module integration and test complexity"},
        {"name": "Filter/antenna ecosystem adjacency", "role": "System-level RF performance depends on broader RF chain"},
    ],
    customers=[
        {"group": "Top smartphone OEMs", "examples": ["AAPL-like concentration risk (industry context)", "Android OEMs"]},
        {"group": "Broad markets OEMs", "examples": ["IoT/device OEMs", "Industrial/auto adjacencies (limited)"]},
    ],
    products_to_customers_map={
        "RF front-end modules (PAs, switches, tuners)": ["Top smartphone OEMs", "Broad markets OEMs"],
        "Discrete RF components": ["Top smartphone OEMs", "Broad markets OEMs"],
    },
    value_chain=[
        "Standards/band proliferation → RF complexity rises → content per device can increase, but OEMs multi-source to manage cost and supply.",
        "Design wins are sticky within a platform cycle; share changes typically occur at new generation transitions."
    ],
    competitive_landscape=["QRVO", "Broadcom (some RF adjacencies)", "Other RF module peers"],
    risk_struct={
        "macro_risks": ["Consumer demand downturn reduces handset units", "FX/regional demand impacts shipments"],
        "industry_risks": ["Handset inventory corrections", "Pricing pressure in commoditized RF components"],
        "idiosyncratic_risks": ["Customer concentration risk", "Content share losses at platform transitions", "Process/yield execution for RF modules"],
    },
    quant_profile={
        "cycle_exposure": {
            "smartphone_cycle": 0.85,
            "seasonality_ramp": 0.70,
            "broad_markets_offset": 0.30,
        },
        "supplier_dependency_risk": {
            "rf_process_yield_dependency": 0.50,
            "module_packaging_dependency": 0.55,
        },
        "customer_concentration_risk": {
            "top_customer_weight": 0.85,
            "platform_transition_risk": 0.70,
        },
        "capital_intensity": {
            "capex_intensity": 0.45,
            "rnd_intensity": 0.55,
        },
        "moat_profile": {
            "rf_module_integration": 0.60,
            "qualification_switching_costs": 0.60,
            "oem_relationships": 0.55,
        },
    },
    narrative={
        "one_liner": "RF handset lever: high unit-cycle sensitivity and major customer concentration; watch content share at platform transitions.",
        "bull_case": "Handset demand rebounds; premium content per device holds; share remains stable; broad markets slowly diversify.",
        "bear_case": "Handset cycle stays weak; major customer reduces share; multi-sourcing and pricing pressure compress margins.",
        "watch_items": ["Handset units", "Top-customer share signals", "Platform transition timing", "RF content per device"],
    },
    source_note="Deterministic institutional template (no live fundamentals)."
)

# ---- QRVO (Deep) ----
CHAIN["QRVO"] = _schema(
    ticker="QRVO",
    business_model=[
        "RF components and modules supplier with exposure to smartphone units and content share; diversification exists but handset cycle remains central.",
        "Economic engine: design wins in RF front-end + content per device; volatility driven by OEM concentration and competitive dynamics.",
        "Moat depends on RF performance, integration, and qualification; downside risk rises if share shifts at generation transitions."
    ],
    revenue_mix={
        "smartphone_rf": "dominant",
        "broad_markets": "meaningful/variable",
        "notes": "Broad markets can help diversify, but handset cycle typically dominates near-term results."
    },
    pricing_power=(
        "Moderate: stronger in differentiated modules; weaker in commodity components and during handset downcycles."
    ),
    suppliers=[
        {"name": "Process/manufacturing ecosystem", "role": "RF process execution and yield"},
        {"name": "Packaging/assembly partners", "role": "Module integration and reliability"},
        {"name": "RF supply chain adjacency", "role": "Filters/antennas and OEM RF architecture choices influence attach"},
    ],
    customers=[
        {"group": "Smartphone OEMs", "examples": ["AAPL-like concentration risk (industry context)", "Android OEMs"]},
        {"group": "Broad markets", "examples": ["Defense/industrial adjacencies", "Wi-Fi/IoT OEMs"]},
    ],
    products_to_customers_map={
        "RF modules/components": ["Smartphone OEMs", "Broad markets"],
        "Connectivity adjacencies (selected)": ["Broad markets"],
    },
    value_chain=[
        "Band proliferation and 5G complexity increase RF content; OEM cost/supply strategies push multi-sourcing.",
        "Share changes generally happen on new platform generations; broad markets can smooth but not eliminate handset cyclicality."
    ],
    competitive_landscape=["SWKS", "Broadcom (some RF adjacencies)", "Other RF peers"],
    risk_struct={
        "macro_risks": ["Consumer demand downturn reduces handset units"],
        "industry_risks": ["Handset inventory corrections and pricing pressure", "OEM multi-sourcing reduces pricing leverage"],
        "idiosyncratic_risks": ["Customer concentration", "Share loss at platform transitions", "Process execution (yield/cost)"],
    },
    quant_profile={
        "cycle_exposure": {
            "smartphone_cycle": 0.85,
            "seasonality_ramp": 0.70,
            "broad_markets_offset": 0.40,
        },
        "supplier_dependency_risk": {
            "rf_process_yield_dependency": 0.55,
            "module_packaging_dependency": 0.55,
        },
        "customer_concentration_risk": {
            "top_customer_weight": 0.80,
            "platform_transition_risk": 0.70,
        },
        "capital_intensity": {
            "capex_intensity": 0.45,
            "rnd_intensity": 0.55,
        },
        "moat_profile": {
            "rf_performance_ip": 0.60,
            "qualification_switching_costs": 0.60,
            "diversification_optional": 0.45,
        },
    },
    narrative={
        "one_liner": "RF cycle exposure: handset-driven with competitive and concentration risk; broad markets can buffer but not dominate near-term.",
        "bull_case": "Handset rebound plus stable content share; broad markets contribute steadier demand; execution improves margins.",
        "bear_case": "Handset weakness persists; share shifts at transitions; OEM multi-sourcing pressures pricing and margins.",
        "watch_items": ["Handset units", "Share signals at new launches", "Broad markets contribution", "Pricing/mix"],
    },
    source_note="Deterministic institutional template (no live fundamentals)."
)


# ============================================================
# Batch 4 Deepening (Group 4): Memory + Storage stack
# Tickers: MU, WDC
# - Institutional ecosystem depth
# - Explicit supplier/customer mapping
# - Quant profiles tuned for memory pricing cycle + storage demand cycles
# ============================================================

# ---- MU (Deep) ----
CHAIN["MU"] = _schema(
    ticker="MU",
    business_model=[
        "Memory manufacturer (DRAM + NAND) with exposure to commodity-like pricing cycles driven by supply discipline and end-demand.",
        "Economic engine: bit demand growth vs industry supply growth; mix shift toward higher-value products (e.g., HBM) can improve cycle position.",
        "High operating leverage: utilization and pricing move margins significantly; capex discipline is a key differentiator across cycles."
    ],
    revenue_mix={
        "dram": "dominant",
        "nand": "meaningful",
        "hbm_ai": "strategic high-value subset (within DRAM)",
        "notes": "HBM/AI mix can reduce commodity exposure at the margin, but baseline memory pricing cycle remains the primary swing factor."
    },
    pricing_power=(
        "Low-to-moderate structurally (commodity dynamics), but improves during tight supply periods and when mix shifts to higher-value SKUs."
    ),
    suppliers=[
        {"name": "WFE vendors", "role": "Capex and tool availability gate capacity adds and node transitions"},
        {"name": "Materials/chemicals ecosystem", "role": "Wafers, specialty gases, photoresists; quality impacts yields"},
        {"name": "Packaging/test ecosystem", "role": "HBM and advanced memory packaging/test complexity"},
        {"name": "Power/energy inputs", "role": "High fab energy use; costs matter over cycles"},
    ],
    customers=[
        {"group": "Hyperscalers / cloud", "examples": ["MSFT", "AMZN", "GOOGL", "META"]},
        {"group": "Enterprise/server OEMs", "examples": ["DELL", "HPE", "Lenovo"]},
        {"group": "PC OEMs", "examples": ["HPQ", "DELL", "Lenovo"]},
        {"group": "Mobile/consumer OEMs", "examples": ["Smartphone OEMs (industry context)"]},
        {"group": "Storage/SSD ecosystem", "examples": ["SSD makers / module houses (industry context)"]},
    ],
    products_to_customers_map={
        "DRAM (incl. DDR/LPDDR)": ["Hyperscalers / cloud", "Enterprise/server OEMs", "PC OEMs", "Mobile/consumer OEMs"],
        "HBM (AI)": ["Hyperscalers / cloud", "Enterprise/server OEMs"],
        "NAND (client/enterprise)": ["Storage/SSD ecosystem", "Enterprise/server OEMs", "PC OEMs", "Mobile/consumer OEMs"],
    },
    value_chain=[
        "Bit demand growth (compute, mobile, storage) vs supply growth (capex, node transitions) → pricing cycle.",
        "HBM is constrained by packaging/test and qualification; AI demand can tighten DRAM market even if non-AI segments are soft.",
        "Downcycles often begin with inventory buildup and aggressive supply adds; recoveries require supply discipline and demand normalization."
    ],
    competitive_landscape=["Samsung Electronics (industry context)", "SK hynix (industry context)", "Kioxia/WD NAND (industry context)"],
    risk_struct={
        "macro_risks": ["Global recession reduces electronics demand, accelerating inventory correction"],
        "industry_risks": ["Severe commodity pricing cycles; supply additions overshoot demand", "HBM supply chain constraints can cap upside or delay ramps"],
        "idiosyncratic_risks": ["Execution risk in node transitions (yield/cost)", "Capex discipline relative to peers", "Customer contract mix and pricing realization"],
    },
    quant_profile={
        "cycle_exposure": {
            "memory_pricing_cycle": 0.95,
            "inventory_correction_risk": 0.80,
            "ai_hbm_demand_support": 0.70,
        },
        "supplier_dependency_risk": {
            "wfe_dependency": 0.70,
            "materials_yield_dependency": 0.60,
            "hbm_packaging_test_dependency": 0.75,
        },
        "customer_concentration_risk": {
            "hyperscaler_mix_weight": 0.55,
            "oem_contract_concentration": 0.55,
        },
        "capital_intensity": {
            "fab_capex_intensity": 0.90,
            "fixed_cost_operating_leverage": 0.90,
            "rnd_intensity": 0.65,
        },
        "moat_profile": {
            "scale_cost_curve": 0.55,
            "hbm_execution_optional": 0.60,
            "customer_qualification": 0.55,
        },
    },
    narrative={
        "one_liner": "Memory cycle lever: huge upside in tight supply/HBM mix, but pricing cycles and operating leverage dominate volatility.",
        "bull_case": "AI/HBM demand tightens supply; capex discipline holds; pricing improves and mix shifts toward higher-value products.",
        "bear_case": "Supply overshoot + inventory correction drives steep pricing declines; utilization falls; margins compress sharply.",
        "watch_items": ["DRAM/NAND pricing signals", "HBM packaging capacity", "Capex discipline", "Inventory levels at OEMs/cloud"],
    },
    source_note="Deterministic institutional template (no live fundamentals)."
)

# ---- WDC (Deep) ----
CHAIN["WDC"] = _schema(
    ticker="WDC",
    business_model=[
        "Storage supplier across HDD and SSD ecosystems; demand driven by cloud storage buildouts, enterprise refresh, and PC/client cycles.",
        "Economic engine: mix of volume demand and pricing discipline; HDDs tend to be capacity/nearline cloud-driven, SSDs tie to NAND pricing and client/server demand.",
        "SanDisk is part of the portfolio/brand ecosystem (client storage identity), but the core driver is storage demand + component pricing cycles."
    ],
    revenue_mix={
        "hdd_nearline_cloud": "large swing driver",
        "client_storage": "cyclical",
        "flash_ssd": "cyclical with NAND pricing",
        "notes": "Cloud capex and nearline demand influence HDD; SSD/flash is more sensitive to NAND pricing and client cycles."
    },
    pricing_power=(
        "Moderate when capacity is tight and product transitions (higher TB per drive) support ASPs; weaker during inventory corrections and NAND downcycles."
    ),
    suppliers=[
        {"name": "NAND supply chain", "role": "NAND pricing and availability influence SSD economics"},
        {"name": "Head/media and components ecosystem", "role": "HDD component sourcing affects cost and ramp"},
        {"name": "Manufacturing/assembly ecosystem", "role": "Yield and scale execution matter; logistics impacts delivery"},
        {"name": "Cloud qualification ecosystem", "role": "Hyperscaler qualification cycles affect ramps and product transitions"},
    ],
    customers=[
        {"group": "Hyperscalers / cloud", "examples": ["MSFT", "AMZN", "GOOGL", "META"]},
        {"group": "Enterprise storage OEMs", "examples": ["DELL", "HPE", "NetApp-like peers (industry context)"]},
        {"group": "PC OEMs / channel", "examples": ["HPQ", "DELL", "Lenovo", "Retail channel"]},
        {"group": "Consumer/retail", "examples": ["External drives", "Client SSD buyers"]},
    ],
    products_to_customers_map={
        "Nearline HDD (high-capacity)": ["Hyperscalers / cloud", "Enterprise storage OEMs"],
        "Client HDD/SSD": ["PC OEMs / channel", "Consumer/retail"],
        "Enterprise SSD": ["Hyperscalers / cloud", "Enterprise storage OEMs"],
        "External/consumer storage": ["Consumer/retail"],
    },
    value_chain=[
        "Data growth → cloud storage demand → nearline capacity transitions → qualification → ramp; digestion phases create demand air pockets.",
        "Client storage follows PC unit cycle and channel inventory; SSD margins swing with NAND pricing and mix.",
        "Technology transitions (higher areal density / higher TB per drive) support ASPs but can be gated by yields and customer qualification."
    ],
    competitive_landscape=["Seagate (HDD)", "Samsung/SSD peers (industry context)", "Other SSD/NAND ecosystem players"],
    risk_struct={
        "macro_risks": ["Cloud/enterprise capex pauses reduce nearline demand", "PC downturn reduces client storage shipments"],
        "industry_risks": ["Inventory corrections in storage supply chain", "NAND pricing downcycles pressure SSD margins"],
        "idiosyncratic_risks": ["Customer concentration in hyperscalers", "Execution risk in capacity transitions and qualification timing"],
    },
    quant_profile={
        "cycle_exposure": {
            "cloud_storage_capex_cycle": 0.70,
            "pc_cycle_sensitivity": 0.60,
            "nand_pricing_cycle": 0.65,
            "inventory_correction_risk": 0.70,
        },
        "supplier_dependency_risk": {
            "nand_cost_dependency": 0.60,
            "component_supply_dependency": 0.45,
            "qualification_timing_dependency": 0.55,
        },
        "customer_concentration_risk": {
            "hyperscaler_mix_weight": 0.70,
            "top_customer_bargaining_power": 0.65,
        },
        "capital_intensity": {
            "manufacturing_capex_intensity": 0.65,
            "fixed_cost_operating_leverage": 0.70,
            "rnd_intensity": 0.50,
        },
        "moat_profile": {
            "scale_in_storage": 0.55,
            "qualification_stickiness_cloud": 0.60,
            "transition_execution": 0.55,
        },
    },
    narrative={
        "one_liner": "Storage demand + pricing cycle: nearline cloud transitions drive upside; NAND/PC cycles and hyperscaler digestion drive downside.",
        "bull_case": "Cloud storage demand re-accelerates; higher-capacity ramps succeed; pricing stays rational; SSD margins stabilize with NAND.",
        "bear_case": "Hyperscaler digestion + PC weakness; storage inventory correction; NAND downcycle compresses SSD margins.",
        "watch_items": ["Hyperscaler storage tone", "Nearline capacity ramps/qualification", "NAND pricing", "PC/channel inventory"],
    },
    source_note="Deterministic institutional template (no live fundamentals)."
)


# ============================================================
# Batch 5 Deepening (Group 5): Power + Photonics + Test + SiC materials
# Tickers: MPWR, COHR, WOLF, TER, ACLS
# ============================================================

# ---- MPWR (Deep) ----
CHAIN["MPWR"] = _schema(
    ticker="MPWR",
    business_model=[
        "Power management IC supplier leveraged to higher power density and efficiency needs across cloud, automotive, and industrial.",
        "Economic engine: secular power complexity (AI servers, electrification) + sticky design-ins; cycles exist but content per system is a tailwind.",
        "Moat: high-performance power architectures, fast time-to-market, and deep customer integration in power stages."
    ],
    revenue_mix={
        "enterprise_datacenter": "meaningful",
        "automotive": "growing",
        "industrial": "meaningful",
        "consumer": "variable",
        "notes": "Exposure to AI/servers can drive upside; consumer cycles add volatility but typically less structural than power secular trends."
    },
    pricing_power=(
        "Strong in high-performance power stages where efficiency/thermals matter; weaker in commoditized power categories."
    ),
    suppliers=[
        {"name": "Foundry partners", "role": "Manufacturing capacity and process suitability"},
        {"name": "Packaging ecosystem", "role": "Thermal/mechanical packaging for power density"},
        {"name": "Passive components ecosystem", "role": "Inductors/caps and system BOM dependencies influence adoption"},
    ],
    customers=[
        {"group": "Cloud/server OEMs", "examples": ["Hyperscaler platforms (industry context)", "Server OEMs"]},
        {"group": "Automotive", "examples": ["Tier1 suppliers", "EV subsystems"]},
        {"group": "Industrial OEMs", "examples": ["Automation", "Power supplies", "Embedded systems"]},
    ],
    products_to_customers_map={
        "DC-DC converters / power stages": ["Cloud/server OEMs", "Industrial OEMs", "Automotive"],
        "Power modules (high density)": ["Cloud/server OEMs", "Automotive"],
        "Mixed-signal power control": ["Industrial OEMs", "Automotive"],
    },
    value_chain=[
        "Compute/power density rises → need for efficiency/thermal management → power IC content per system increases.",
        "Design-in cycles create stickiness; near-term volatility often comes from customer inventory corrections, not immediate design loss."
    ],
    competitive_landscape=["TI/ADI analog power adjacencies", "Other power IC peers (industry context)"],
    risk_struct={
        "macro_risks": ["Enterprise/industrial slowdown reduces near-term builds"],
        "industry_risks": ["Customer inventory corrections can be sharp in electronics supply chains"],
        "idiosyncratic_risks": ["Design win concentration in certain platforms", "Foundry/packaging constraints for high density modules"],
    },
    quant_profile={
        "cycle_exposure": {
            "datacenter_build_cycle": 0.55,
            "industrial_cycle": 0.55,
            "auto_cycle": 0.45,
            "inventory_correction_risk": 0.60,
        },
        "supplier_dependency_risk": {
            "foundry_dependence": 0.50,
            "thermal_packaging_dependency": 0.55,
        },
        "customer_concentration_risk": {
            "platform_concentration": 0.55,
            "hyperscaler_mix_weight": 0.45,
        },
        "capital_intensity": {
            "rnd_intensity": 0.60,
            "nre_intensity": 0.55,
        },
        "moat_profile": {
            "power_density_performance": 0.75,
            "design_in_stickiness": 0.70,
            "time_to_market_execution": 0.65,
        },
    },
    narrative={
        "one_liner": "Power density compounder: secular demand from AI/efficiency, with cyclicality mainly from customer inventory corrections.",
        "bull_case": "AI server power demand accelerates; auto electrification expands content; differentiated power modules sustain margins.",
        "bear_case": "Inventory correction hits shipments; platform concentration hurts; packaging constraints slow ramps.",
        "watch_items": ["Datacenter build tone", "Customer inventory", "Module ramp/packaging constraints", "Auto content trajectory"],
    },
    source_note="Deterministic institutional template (no live fundamentals)."
)

# ---- COHR (Deep) ----
CHAIN["COHR"] = _schema(
    ticker="COHR",
    business_model=[
        "Photonics/lasers supplier with exposure to optical communications and industrial laser applications.",
        "Economic engine: datacenter and telecom optical upgrade cycles (bandwidth demand) plus industrial capex; cycles can be lumpy.",
        "Moat varies by segment: performance/efficiency and qualification matter in optical; industrial relies on application breadth."
    ],
    revenue_mix={
        "optical_comms": "meaningful swing",
        "industrial_lasers": "meaningful",
        "other_photonics": "variable",
        "notes": "Optical comms tied to bandwidth upgrades; industrial lasers tied to manufacturing capex and utilization."
    },
    pricing_power=(
        "Moderate in qualified optical components; weaker in more competitive industrial segments depending on product mix."
    ),
    suppliers=[
        {"name": "Semiconductor materials ecosystem", "role": "III-V materials, epitaxy supply chains for lasers"},
        {"name": "Optics/packaging ecosystem", "role": "Precision packaging and alignment critical for performance"},
        {"name": "Electronics/controls supply chain", "role": "Drivers and control electronics for laser systems"},
    ],
    customers=[
        {"group": "Optical module vendors / OEMs", "examples": ["Optical transceiver/module ecosystem (industry context)"]},
        {"group": "Telecom/networking OEMs", "examples": ["Networking equipment OEMs"]},
        {"group": "Industrial OEMs", "examples": ["Manufacturing equipment", "Materials processing"]},
    ],
    products_to_customers_map={
        "Datacom lasers / photonics": ["Optical module vendors / OEMs", "Telecom/networking OEMs"],
        "Industrial laser systems": ["Industrial OEMs"],
        "Specialty photonics components": ["Optical module vendors / OEMs", "Industrial OEMs"],
    },
    value_chain=[
        "Bandwidth growth → optical upgrades → module designs → component qualification → ramp; digestion phases create air pockets.",
        "Industrial demand follows manufacturing capex and utilization; product cycles can be project-driven."
    ],
    competitive_landscape=["Other photonics/laser peers (industry context)", "Lumentum-like peers (industry context)"],
    risk_struct={
        "macro_risks": ["Industrial slowdown reduces capex", "Enterprise IT/capex pauses slow optical upgrades"],
        "industry_risks": ["Datacom upgrade cycles are lumpy", "Inventory corrections in optical module channel"],
        "idiosyncratic_risks": ["Program concentration", "Execution/quality issues can impact qualification and returns"],
    },
    quant_profile={
        "cycle_exposure": {
            "datacenter_optical_cycle": 0.65,
            "telecom_cycle": 0.55,
            "industrial_capex_cycle": 0.60,
        },
        "supplier_dependency_risk": {
            "materials_epitaxy_dependency": 0.55,
            "precision_packaging_dependency": 0.60,
        },
        "customer_concentration_risk": {
            "program_concentration": 0.60,
            "channel_visibility_risk": 0.55,
        },
        "capital_intensity": {
            "manufacturing_complexity": 0.55,
            "rnd_intensity": 0.55,
        },
        "moat_profile": {
            "qualification_stickiness_optical": 0.60,
            "performance_differentiation": 0.55,
            "application_breadth": 0.45,
        },
    },
    narrative={
        "one_liner": "Photonics cycle lever: rides datacenter bandwidth upgrades and industrial capex; lumpy programs and channel inventory matter.",
        "bull_case": "Datacenter optical upgrades accelerate; qualification wins ramp; industrial demand improves.",
        "bear_case": "Optical digestion phase extends; industrial capex soft; program concentration drives volatility.",
        "watch_items": ["Datacenter capex/optical upgrade tone", "Module channel inventory", "Industrial order trends", "Program ramp cadence"],
    },
    source_note="Deterministic institutional template (no live fundamentals)."
)

# ---- WOLF (Deep) ----
CHAIN["WOLF"] = _schema(
    ticker="WOLF",
    business_model=[
        "SiC materials and power devices ecosystem exposure: positioned at the supply chain chokepoint for wide-bandgap adoption.",
        "Economic engine: EV and industrial power transition to SiC; success depends on scaling materials yield and customer qualification.",
        "High execution risk: manufacturing scale-up, cost curve, and customer program timing drive outcomes."
    ],
    revenue_mix={
        "sic_materials": "core strategic",
        "power_devices": "option/adjacent",
        "notes": "Business is highly execution-sensitive; adoption tailwind exists but timing and yield are key."
    },
    pricing_power=(
        "Potentially strong if high-quality substrates are scarce; weakens if competitors scale and pricing commoditizes."
    ),
    suppliers=[
        {"name": "Raw materials + crystal growth inputs", "role": "Quality impacts yields and cost"},
        {"name": "Manufacturing tool/process ecosystem", "role": "Scaling crystal growth and wafering is complex"},
        {"name": "Customer qualification ecosystem", "role": "Auto qualification and reliability standards create long ramps"},
    ],
    customers=[
        {"group": "EV/auto power supply chain", "examples": ["Auto OEM programs", "Tier1 inverter suppliers"]},
        {"group": "Industrial power OEMs", "examples": ["Renewables/inverters", "Industrial drives"]},
        {"group": "Power semiconductor peers", "examples": ["Device makers needing substrates (industry context)"]},
    ],
    products_to_customers_map={
        "SiC substrates/wafers": ["EV/auto power supply chain", "Industrial power OEMs", "Power semiconductor peers"],
        "SiC power devices (where applicable)": ["EV/auto power supply chain", "Industrial power OEMs"],
    },
    value_chain=[
        "EV adoption → inverter/charging demand → SiC penetration rises → substrate supply/yield becomes the bottleneck.",
        "Qualification cycles are long; capacity ramps can overshoot or undershoot demand depending on timing and yield learning."
    ],
    competitive_landscape=["ON (SiC)", "STM (SiC)", "Infineon-like peers (industry context)", "Other substrate providers (industry context)"],
    risk_struct={
        "macro_risks": ["EV demand slowdown delays adoption curve"],
        "industry_risks": ["SiC capacity build-out can compress pricing", "Technology transitions and yield learning are non-linear"],
        "idiosyncratic_risks": ["Scale-up execution risk", "Customer program timing slips", "High fixed-cost leverage in ramp phases"],
    },
    quant_profile={
        "cycle_exposure": {
            "ev_cycle": 0.75,
            "industrial_power_cycle": 0.55,
            "adoption_timing_risk": 0.80,
        },
        "supplier_dependency_risk": {
            "materials_yield_dependency": 0.80,
            "manufacturing_scale_dependency": 0.80,
        },
        "customer_concentration_risk": {
            "program_concentration": 0.70,
            "qualification_gate_risk": 0.75,
        },
        "capital_intensity": {
            "capex_intensity": 0.85,
            "fixed_cost_operating_leverage": 0.85,
            "rnd_intensity": 0.55,
        },
        "moat_profile": {
            "materials_knowhow": 0.60,
            "early_scale_optionality": 0.55,
            "qualification_barriers": 0.55,
        },
    },
    narrative={
        "one_liner": "SiC chokepoint bet: big structural tailwind, but execution (yields/scale) and program timing dominate risk.",
        "bull_case": "EV/industrial adoption accelerates; yields improve; long-term contracts stabilize demand; pricing remains rational.",
        "bear_case": "Adoption slows; scale-up delays and cost overruns; pricing compresses as supply expands; high leverage amplifies downside.",
        "watch_items": ["EV demand", "Yield/throughput progress", "Customer qualification wins", "Capacity ramp pacing"],
    },
    source_note="Deterministic institutional template (no live fundamentals)."
)

# ---- TER (Deep) ----
CHAIN["TER"] = _schema(
    ticker="TER",
    business_model=[
        "Semiconductor test equipment supplier with exposure to device unit volumes and complexity (more testing for advanced nodes/packaging).",
        "Economic engine: test intensity per device + capacity adds at OSATs/IDMs; cyclicality driven by semiconductor unit cycles and customer capex timing.",
        "Resilience comes from installed base/service and complexity tailwinds, but it remains capex-driven."
    ],
    revenue_mix={
        "semiconductor_test_systems": "core cyclical",
        "services_and_consumables": "stabilizer",
        "notes": "Test demand is tied to both capacity and complexity; AI/advanced packaging can increase test requirements."
    },
    pricing_power=(
        "Moderate: stronger in high-performance segments and when test complexity rises; competitive with peers and in-house solutions."
    ),
    suppliers=[
        {"name": "Precision components supply chain", "role": "Motion, electronics, and high-speed measurement subsystems"},
        {"name": "Probe cards / interface ecosystem", "role": "Interface hardware is critical for test performance"},
        {"name": "Software/automation ecosystem", "role": "Test software, data analytics, and uptime support"},
    ],
    customers=[
        {"group": "OSATs", "examples": ["ASE-like peers (industry context)", "Amkor-like peers (industry context)"]},
        {"group": "IDMs", "examples": ["INTC", "MU", "Other IDMs (industry context)"]},
        {"group": "Foundries (test ecosystem)", "examples": ["TSM ecosystem partners (industry context)"]},
    ],
    products_to_customers_map={
        "Test platforms (digital/analog/mixed)": ["OSATs", "IDMs"],
        "Interface/handlers (ecosystem)": ["OSATs", "IDMs"],
        "Service + upgrades": ["OSATs", "IDMs"],
    },
    value_chain=[
        "Device complexity increases → more tests and tighter tolerances → test time/content rises.",
        "Capacity adds occur in waves; digestion phases follow; service helps buffer but does not eliminate capex cyclicality."
    ],
    competitive_landscape=["Advantest-like peers (industry context)", "Other test equipment peers (industry context)"],
    risk_struct={
        "macro_risks": ["Broad semiconductor downturn reduces unit volumes and test capex"],
        "industry_risks": ["Capex digestion cycles at OSATs/IDMs", "Pricing pressure if competition intensifies"],
        "idiosyncratic_risks": ["Customer concentration in major OSAT/IDM accounts", "Timing lags between silicon demand and test orders"],
    },
    quant_profile={
        "cycle_exposure": {
            "semi_unit_cycle": 0.75,
            "capex_digestion_risk": 0.70,
            "complexity_test_intensity": 0.55,
        },
        "supplier_dependency_risk": {
            "precision_components": 0.45,
            "probe_interface_dependency": 0.55,
        },
        "customer_concentration_risk": {
            "top_customer_weight": 0.60,
            "osat_dependency": 0.55,
        },
        "capital_intensity": {
            "rnd_intensity": 0.50,
            "manufacturing_complexity": 0.45,
        },
        "moat_profile": {
            "installed_base_service_lock": 0.65,
            "test_platform_stickiness": 0.55,
            "complexity_tailwind": 0.55,
        },
    },
    narrative={
        "one_liner": "Test capex cycle: benefits from rising complexity, but remains tied to OSAT/IDM capex waves and digestion phases.",
        "bull_case": "AI/advanced packaging increases test intensity; customers add capacity; service mix supports margins.",
        "bear_case": "Semi downturn triggers capex pause; digestion extends; pricing pressure reduces leverage.",
        "watch_items": ["OSAT/IDM capex tone", "Unit demand signals", "Advanced packaging/test intensity", "Service mix"],
    },
    source_note="Deterministic institutional template (no live fundamentals)."
)

# ---- ACLS (Deep) ----
CHAIN["ACLS"] = _schema(
    ticker="ACLS",
    business_model=[
        "Ion implantation equipment supplier used in semiconductor manufacturing; demand tied to WFE cycles and process complexity.",
        "Economic engine: WFE spend + implant intensity per wafer; installed base supports service/parts but systems remain cyclical.",
        "Moat arises from tool performance, uptime, and qualification; exposure is concentrated in certain customer programs."
    ],
    revenue_mix={
        "implant_systems": "core cyclical",
        "services_parts": "stabilizer",
        "notes": "Implant demand generally follows WFE but can be influenced by technology inflections and customer mix."
    },
    pricing_power="Moderate: strong where performance matters and switching is difficult; competitive pressures exist in some segments.",
    suppliers=[
        {"name": "Precision components ecosystem", "role": "High voltage power, vacuum, beamline components"},
        {"name": "Serviceables/parts supply chain", "role": "Installed base uptime and parts availability"},
    ],
    customers=[
        {"group": "Foundries", "examples": ["TSM", "GFS", "UMC"]},
        {"group": "IDMs", "examples": ["INTC", "MU", "Other IDMs (industry context)"]},
        {"group": "Memory fabs", "examples": ["MU", "Large memory peers (industry context)"]},
    ],
    products_to_customers_map={
        "Ion implant systems": ["Foundries", "IDMs", "Memory fabs"],
        "Service + parts": ["Foundries", "IDMs", "Memory fabs"],
    },
    value_chain=[
        "Node transitions + capacity adds → implant tool demand; digestion phases follow capex waves.",
        "Installed base drives recurring service, improving resilience relative to pure systems shipments."
    ],
    competitive_landscape=["Applied Materials (some adjacencies)", "Other implant tool peers (industry context)"],
    risk_struct={
        "macro_risks": ["WFE downturn reduces bookings and shipments"],
        "industry_risks": ["Customer digestion phases delay orders", "Export controls can constrain some demand"],
        "idiosyncratic_risks": ["Customer concentration in a few large fabs/programs", "Manufacturing and field performance issues can impact reputation"],
    },
    quant_profile={
        "cycle_exposure": {
            "wfe_cycle_sensitivity": 0.75,
            "capex_digestion_risk": 0.70,
            "node_transition_intensity": 0.55,
        },
        "supplier_dependency_risk": {
            "precision_components": 0.45,
            "regulatory_export_constraints": 0.55,
        },
        "customer_concentration_risk": {
            "top_customer_weight": 0.65,
            "few_customer_industry_structure": 0.60,
        },
        "capital_intensity": {
            "rnd_intensity": 0.50,
            "manufacturing_complexity": 0.45,
        },
        "moat_profile": {
            "qualification_switching_costs": 0.55,
            "field_uptime_reputation": 0.55,
            "installed_base_services": 0.55,
        },
    },
    narrative={
        "one_liner": "Implant WFE lever: cyclical with capex waves, buffered by service base; concentration and digestion phases matter.",
        "bull_case": "Node transitions and capacity adds resume; service base grows; tool performance wins share.",
        "bear_case": "WFE downturn extends; digestion delays orders; export constraints and concentration amplify volatility.",
        "watch_items": ["WFE cycle", "Customer capex plans", "Service mix", "Export policy"],
    },
    source_note="Deterministic institutional template (no live fundamentals)."
)


# ============================================================
# Batch 6 Deepening (Group 6): Foundry / IDM / CPU IP ecosystem
# Tickers: INTC, GFS, ARM, UMC
# ============================================================

# ---- INTC (Deep) ----
CHAIN["INTC"] = _schema(
    ticker="INTC",
    business_model=[
        "Integrated Device Manufacturer (IDM) with CPU platform franchise plus growing foundry ambitions (IFS).",
        "Economic engine splits: (1) client/server CPU platforms tied to PC and datacenter refresh cycles; (2) foundry services tied to external customer roadmaps and long-cycle capex.",
        "Moat historically from x86 ecosystem and manufacturing scale; key swing factors are execution on process roadmaps and competitive platform positioning."
    ],
    revenue_mix={
        "pc_client": "large",
        "datacenter_server": "large/variable",
        "network_edge": "smaller",
        "foundry_services": "option/early",
        "notes": "Client + server dominate cyclicality; foundry adds multi-year optionality but requires heavy capex and execution credibility."
    },
    pricing_power=(
        "Platform pricing power depends on performance-per-watt leadership and competitive landscape. "
        "In downcycles, OEM/channel corrections reduce leverage; in upcycles with leadership, pricing and mix can improve."
    ),
    suppliers=[
        {"name": "WFE vendors", "role": "Process roadmap execution depends on tool availability and manufacturing cadence"},
        {"name": "Materials/chemicals ecosystem", "role": "Yield and reliability depend on materials consistency"},
        {"name": "Advanced packaging ecosystem", "role": "Chiplet/heterogeneous integration relies on packaging/test capacity"},
        {"name": "Foundry ecosystem partners", "role": "If scaling IFS, needs EDA/IP enablement and ecosystem validation"},
    ],
    customers=[
        {"group": "PC OEMs", "examples": ["DELL", "HPQ", "Lenovo"]},
        {"group": "Cloud/enterprise buyers", "examples": ["MSFT", "AMZN", "GOOGL", "META", "Enterprise datacenter buyers"]},
        {"group": "Server OEMs", "examples": ["DELL", "HPE", "Lenovo", "Supermicro-like peers (industry context)"]},
        {"group": "Foundry customers (IFS)", "examples": ["Fabless/IDM customers (industry context)"]},
    ],
    products_to_customers_map={
        "Client CPUs/platforms": ["PC OEMs"],
        "Server CPUs/platforms": ["Cloud/enterprise buyers", "Server OEMs"],
        "Network/edge silicon": ["Cloud/enterprise buyers", "Enterprise/telecom OEMs (industry context)"],
        "Foundry manufacturing services": ["Foundry customers (IFS)"],
        "Packaging/advanced integration services": ["Foundry customers (IFS)", "Internal product platforms"],
    },
    value_chain=[
        "PC refresh cycle + enterprise demand → CPU unit volumes and mix; channel inventory and OEM builds amplify swings.",
        "Datacenter demand tied to cloud capex and enterprise IT; platform transitions drive share shifts.",
        "Foundry build-out: node roadmap credibility + ecosystem enablement → customer design-ins → multi-year ramps; large upfront capex with long payback."
    ],
    competitive_landscape=["AMD", "NVDA (accelerators adjacency)", "ARM ecosystem (CPU IP)", "TSM (manufacturing benchmark)", "Samsung Foundry"],
    risk_struct={
        "macro_risks": ["PC and enterprise demand downturns reduce volumes; risk-off compresses multiples"],
        "industry_risks": ["Intense CPU competition; platform share can move quickly at performance inflections", "Foundry market is scale/credibility driven"],
        "idiosyncratic_risks": ["Process roadmap delays and yield/ramp issues", "High fixed-cost leverage from fabs and capex", "Foundry customer acquisition risk (ecosystem + trust)"],
    },
    quant_profile={
        "cycle_exposure": {
            "pc_cycle": 0.75,
            "datacenter_refresh_cycle": 0.65,
            "cloud_capex_sensitivity": 0.55,
            "foundry_investment_cycle": 0.60,
        },
        "supplier_dependency_risk": {
            "wfe_dependency": 0.60,
            "advanced_packaging_dependency": 0.55,
            "materials_yield_dependency": 0.50,
        },
        "customer_concentration_risk": {
            "oem_platform_concentration": 0.55,
            "cloud_buyer_bargaining_power": 0.55,
        },
        "capital_intensity": {
            "fab_capex_burden": 0.90,
            "fixed_cost_operating_leverage": 0.85,
            "rnd_intensity": 0.70,
        },
        "moat_profile": {
            "ecosystem_platform_stickiness": 0.60,
            "manufacturing_scale_optionality": 0.55,
            "chiplet_packaging_capability": 0.55,
        },
    },
    narrative={
        "one_liner": "CPU platform + foundry optionality: upside on execution and leadership, downside from competition and high fixed-cost leverage.",
        "bull_case": "Process execution improves; platform competitiveness strengthens; PC/server cycles normalize; foundry credibility grows with wins.",
        "bear_case": "Share loss in CPUs persists; process delays; PC/enterprise demand weak; capex burden pressures margins and FCF.",
        "watch_items": ["Process roadmap milestones", "PC channel inventory", "Server share/benchmarks", "IFS customer design-ins", "Packaging/chiplet roadmap"],
    },
    source_note="Deterministic institutional template (no live fundamentals)."
)

# ---- GFS (Deep) ----
CHAIN["GFS"] = _schema(
    ticker="GFS",
    business_model=[
        "Specialty and mature-node foundry focused on differentiated process technologies (RF, power, embedded, FDX-like differentiation) rather than bleeding-edge EUV.",
        "Economic engine: diversified end markets (auto/industrial/IoT/communications) + long-cycle customer programs; utilization and pricing discipline drive margins.",
        "Moat comes from specialty process portfolio, customer co-development, and reliability/availability for long-lived end markets."
    ],
    revenue_mix={
        "auto": "meaningful",
        "industrial_iot": "meaningful",
        "communications": "meaningful",
        "consumer": "smaller/variable",
        "notes": "Mix tends to be steadier than leading-edge foundries; still cyclical via industrial demand and inventory corrections."
    },
    pricing_power=(
        "Moderate: stronger in specialty processes with qualification and co-development; more competitive in generic mature-node capacity."
    ),
    suppliers=[
        {"name": "WFE vendors (mature-node)", "role": "Capacity adds and node upgrades depend on tool availability"},
        {"name": "Materials/wafer ecosystem", "role": "Stable supply supports reliability and yield"},
        {"name": "EDA/IP ecosystem", "role": "PDKs and design enablement improve customer stickiness"},
        {"name": "OSAT/packaging ecosystem", "role": "Packaging and test are critical for end-customer qualification"},
    ],
    customers=[
        {"group": "Auto/industrial fabless", "examples": ["NXPI", "MCHP", "STM (some programs)", "ON (some programs)"]},
        {"group": "RF/communications designers", "examples": ["QCOM (some segments)", "RF/IoT designers (industry context)"]},
        {"group": "Long-life embedded programs", "examples": ["Industrial/IoT OEMs via fabless (industry context)"]},
    ],
    products_to_customers_map={
        "Specialty RF / mixed-signal processes": ["RF/communications designers", "Auto/industrial fabless"],
        "Embedded / IoT processes": ["Long-life embedded programs", "Auto/industrial fabless"],
        "Mature-node capacity manufacturing": ["Auto/industrial fabless", "RF/communications designers"],
    },
    value_chain=[
        "End-market demand (auto/industrial/IoT) → customer design-ins → long qualification → stable multi-year production.",
        "Inventory corrections still occur, but long-life programs typically reduce churn; pricing depends on capacity tightness and specialty differentiation."
    ],
    competitive_landscape=["UMC", "SMIC-like peers (industry context)", "TSMC (mature-node share)", "IDMs with foundry-like capacity (industry context)"],
    risk_struct={
        "macro_risks": ["Industrial slowdown reduces wafer demand", "Auto production volatility affects programs"],
        "industry_risks": ["Mature-node capacity expansions can cause oversupply", "Pricing pressure in commoditized nodes"],
        "idiosyncratic_risks": ["Customer concentration in key programs", "Geopolitical/regulatory constraints in certain regions", "Execution risk in specialty roadmap delivery"],
    },
    quant_profile={
        "cycle_exposure": {
            "industrial_cycle": 0.60,
            "auto_cycle": 0.55,
            "inventory_correction_risk": 0.60,
            "specialty_process_differentiation": 0.45,
        },
        "supplier_dependency_risk": {
            "wfe_dependency_mature": 0.45,
            "materials_yield_dependency": 0.40,
            "eda_ip_enablement_dependency": 0.45,
        },
        "customer_concentration_risk": {
            "program_concentration": 0.60,
            "end_market_mix_concentration": 0.55,
        },
        "capital_intensity": {
            "fab_capex_intensity": 0.75,
            "fixed_cost_operating_leverage": 0.70,
            "rnd_intensity": 0.50,
        },
        "moat_profile": {
            "specialty_process_portfolio": 0.65,
            "qualification_stickiness": 0.60,
            "reliability_availability": 0.55,
        },
    },
    narrative={
        "one_liner": "Specialty foundry: steadier than leading edge, but still cyclical via industrial demand and inventory corrections; differentiation matters.",
        "bull_case": "Specialty processes win share; utilization stays healthy; long-life programs support pricing and margins.",
        "bear_case": "Industrial slowdown and destocking; mature-node oversupply pressures pricing; utilization drops with high fixed-cost leverage.",
        "watch_items": ["Utilization", "Industrial/auto order tone", "Specialty process adoption", "Inventory levels in auto/industrial supply chain"],
    },
    source_note="Deterministic institutional template (no live fundamentals)."
)

# ---- ARM (Deep) ----
CHAIN["ARM"] = _schema(
    ticker="ARM",
    business_model=[
        "CPU and system IP licensor with pervasive ecosystem across mobile, consumer, embedded, and increasingly datacenter/AI-adjacent designs.",
        "Economic engine: licensing (upfront) + royalties (unit-based), driven by device shipments and content/value per chip (higher performance cores, more IP blocks).",
        "Moat: ecosystem standardization, developer/toolchain support, and broad partner network; risks include customer concentration and alternative architectures."
    ],
    revenue_mix={
        "royalties": "recurring and unit-tied",
        "licensing": "project-driven",
        "mobile_ecosystem": "dominant unit base",
        "infra_datacenter": "growing option",
        "notes": "Royalties follow unit cycles; licensing depends on project pipelines and performance roadmaps."
    },
    pricing_power=(
        "Strong where ecosystem lock-in and performance roadmaps are critical; negotiated economics can vary with very large customers."
    ),
    suppliers=[
        {"name": "EDA tool ecosystem", "role": "Partners need robust design flows and IP integration"},
        {"name": "Foundry/packaging ecosystem (indirect)", "role": "Customers rely on manufacturing partners; affects adoption of high-performance cores"},
        {"name": "Software/developer ecosystem", "role": "Toolchains, compilers, OS support drive stickiness"},
    ],
    customers=[
        {"group": "Mobile SoC designers", "examples": ["QCOM", "MediaTek-like peers (industry context)", "Samsung-like peers (industry context)"]},
        {"group": "Hyperscalers / server silicon teams", "examples": ["AMZN", "GOOGL", "MSFT (industry context)"]},
        {"group": "Embedded/IoT designers", "examples": ["NXPI", "STM", "MCHP (adjacent use)", "Industrial OEM silicon teams (industry context)"]},
        {"group": "Consumer electronics SoC designers", "examples": ["Gaming/consumer SoCs (industry context)"]},
    ],
    products_to_customers_map={
        "CPU core IP (performance/efficiency tiers)": ["Mobile SoC designers", "Embedded/IoT designers", "Consumer electronics SoC designers", "Hyperscalers / server silicon teams"],
        "System IP (interconnect, memory controllers, etc.)": ["Mobile SoC designers", "Hyperscalers / server silicon teams"],
        "Security/graphics/compute IP (adjacent)": ["Mobile SoC designers", "Embedded/IoT designers", "Consumer electronics SoC designers"],
    },
    value_chain=[
        "Architecture roadmap → customer licensing → SoC design-in → tapeout → device shipment → royalties.",
        "Royalties scale with unit volumes; mix improves with adoption of higher-value cores/IP blocks.",
        "Datacenter/infra adoption is long-cycle and qualification-heavy, but can carry higher value per design."
    ],
    competitive_landscape=["RISC-V ecosystem (industry context)", "x86 ecosystem (server)", "Other IP licensors (industry context)"],
    risk_struct={
        "macro_risks": ["Consumer device unit downturn reduces royalties"],
        "industry_risks": ["Alternative architecture adoption (RISC-V) in some segments", "Pricing pressure from large customers negotiating economics"],
        "idiosyncratic_risks": ["Customer concentration in major mobile platforms", "Execution risk in roadmap and ecosystem support", "Regulatory/export constraints affecting certain customers"],
    },
    quant_profile={
        "cycle_exposure": {
            "mobile_unit_cycle": 0.75,
            "consumer_unit_cycle": 0.60,
            "datacenter_adoption_cycle": 0.45,
        },
        "supplier_dependency_risk": {
            "ecosystem_enablement_dependency": 0.55,
            "software_toolchain_dependency": 0.55,
        },
        "customer_concentration_risk": {
            "top_customer_weight": 0.70,
            "large_customer_bargaining_power": 0.65,
        },
        "capital_intensity": {
            "rnd_intensity": 0.70,
            "platform_roadmap_investment": 0.70,
        },
        "moat_profile": {
            "ecosystem_lock_in": 0.80,
            "developer_toolchain_strength": 0.70,
            "partner_network_breadth": 0.75,
        },
    },
    narrative={
        "one_liner": "IP ecosystem tollbooth: recurring royalties with unit cycles; moat is ecosystem scale, risk is customer concentration and alternative architectures.",
        "bull_case": "Higher-value cores/IP adoption raises royalty rate; mobile stabilizes; infra/datacenter adoption expands value per design.",
        "bear_case": "Mobile units weaken; major customers renegotiate/shift architectures; alternative ISA adoption grows in key segments.",
        "watch_items": ["Mobile unit trends", "Royalty rate/mix", "RISC-V adoption signals", "Infra/datacenter design wins"],
    },
    source_note="Deterministic institutional template (no live fundamentals)."
)

# ---- UMC (Deep) ----
CHAIN["UMC"] = _schema(
    ticker="UMC",
    business_model=[
        "Mature-node foundry focused on mainstream processes for consumer, industrial, and communications end markets.",
        "Economic engine: utilization and pricing in mature nodes; diversification across customers helps, but exposure to consumer cycles and inventory corrections remains.",
        "Moat is operational execution, cost, and customer relationships in stable nodes; less tied to leading-edge EUV races."
    ],
    revenue_mix={
        "consumer": "meaningful",
        "communications": "meaningful",
        "industrial": "meaningful",
        "notes": "Mature nodes still face cyclicality; demand swings and customer inventory corrections impact utilization."
    },
    pricing_power="Low-to-moderate; improves when capacity is tight, but competition is significant in commoditized nodes.",
    suppliers=[
        {"name": "Mature-node WFE vendors", "role": "Capacity additions and tool refresh cycles"},
        {"name": "Materials/wafer ecosystem", "role": "Stable supply supports yield and delivery"},
        {"name": "EDA/IP ecosystem", "role": "PDK enablement improves stickiness"},
    ],
    customers=[
        {"group": "Consumer/communications fabless", "examples": ["Broad fabless ecosystem (industry context)"]},
        {"group": "Industrial embedded designers", "examples": ["Industrial/IoT fabless (industry context)"]},
        {"group": "Platform OEM supply chains", "examples": ["Consumer electronics supply chain (industry context)"]},
    ],
    products_to_customers_map={
        "Mature-node wafer manufacturing": ["Consumer/communications fabless", "Industrial embedded designers", "Platform OEM supply chains"],
        "Specialty variants (where applicable)": ["Industrial embedded designers", "Consumer/communications fabless"],
    },
    value_chain=[
        "End demand → fabless orders → wafer starts → utilization drives margin; inventory corrections reduce starts quickly.",
        "Cost and reliability are key differentiators; long-lived nodes support stable programs but do not remove cyclicality."
    ],
    competitive_landscape=["GFS", "SMIC-like peers (industry context)", "TSMC mature nodes", "Other mature-node foundries"],
    risk_struct={
        "macro_risks": ["Consumer downturn reduces wafer demand"],
        "industry_risks": ["Mature-node oversupply compresses pricing", "Inventory corrections reduce utilization"],
        "idiosyncratic_risks": ["Mix concentration in certain consumer programs", "Geopolitical/regulatory headline risks"],
    },
    quant_profile={
        "cycle_exposure": {
            "consumer_cycle": 0.65,
            "inventory_correction_risk": 0.70,
            "industrial_cycle": 0.50,
        },
        "supplier_dependency_risk": {
            "wfe_dependency_mature": 0.40,
            "materials_yield_dependency": 0.35,
            "eda_enablement_dependency": 0.40,
        },
        "customer_concentration_risk": {
            "program_concentration": 0.55,
            "consumer_mix_concentration": 0.60,
        },
        "capital_intensity": {
            "fab_capex_intensity": 0.70,
            "fixed_cost_operating_leverage": 0.70,
            "rnd_intensity": 0.35,
        },
        "moat_profile": {
            "cost_execution": 0.55,
            "reliability_availability": 0.55,
            "customer_relationships": 0.50,
        },
    },
    narrative={
        "one_liner": "Mature-node foundry: utilization-driven economics with consumer/inventory cycle sensitivity; wins via cost and reliability.",
        "bull_case": "Utilization tightens; pricing improves; industrial demand steadies; customer programs remain sticky.",
        "bear_case": "Consumer demand slows; inventory correction reduces starts; oversupply pressures pricing and margins.",
        "watch_items": ["Utilization", "Consumer inventory signals", "Pricing in mature nodes", "Customer order visibility"],
    },
    source_note="Deterministic institutional template (no live fundamentals)."
)


# ============================================================
# Batch 7 Deepening (Group 7): Photonics + Institutional++ mega-caps
# Tickers: IPGP (new deep), and second-pass deepening for NVDA, AMD, AVGO
# Notes:
# - This is a "same-schema" upgrade. We overwrite CHAIN entries for these tickers with deeper versions.
# ============================================================

# ---- IPGP (Deep) ----
CHAIN["IPGP"] = _schema(
    ticker="IPGP",
    business_model=[
        "Fiber laser supplier with exposure to industrial manufacturing capex, automation, and niche high-power/specialty photonics applications.",
        "Economic engine: industrial utilization and capex cycles (cutting/welding/marking), plus adoption of automation and electrification-driven manufacturing upgrades.",
        "Moat: vertical integration in fiber laser architecture, performance/cost, and reliability; cycles can be sharp when industrial demand turns."
    ],
    revenue_mix={
        "materials_processing_lasers": "core",
        "high_power_applications": "meaningful",
        "other_photonics": "variable",
        "notes": "Industrial capex dominates; end-demand is indirectly linked to auto, machine tools, and general manufacturing health."
    },
    pricing_power=(
        "Moderate: stronger where performance/reliability is critical; weaker in highly competitive commodity-like segments and during downturns."
    ),
    suppliers=[
        {"name": "Optics/components ecosystem", "role": "Precision optics, isolation, and packaging influence performance"},
        {"name": "Semiconductor components supply chain", "role": "Drivers, control electronics, and specialty components"},
        {"name": "Industrial distribution/integrators", "role": "System integrators influence adoption and end-customer reach"},
    ],
    customers=[
        {"group": "Industrial OEMs / integrators", "examples": ["Machine tool builders", "Automation integrators"]},
        {"group": "Auto/manufacturing supply chain", "examples": ["Welding/cutting lines", "EV manufacturing adjacencies"]},
        {"group": "General manufacturing", "examples": ["Metal processing", "Electronics manufacturing adjacencies"]},
    ],
    products_to_customers_map={
        "Fiber lasers (cutting/welding/marking)": ["Industrial OEMs / integrators", "Auto/manufacturing supply chain", "General manufacturing"],
        "High-power/specialty lasers": ["Industrial OEMs / integrators", "Auto/manufacturing supply chain"],
        "Components/subsystems": ["Industrial OEMs / integrators"],
    },
    value_chain=[
        "Manufacturing utilization rises → customers invest in throughput/automation → laser tool demand increases.",
        "Downturns often cause capex pauses and channel inventory corrections; recovery depends on utilization and order backlog rebuilding."
    ],
    competitive_landscape=["Other industrial laser peers (industry context)", "COHR (photonics adjacency)"],
    risk_struct={
        "macro_risks": ["Industrial recession reduces capex quickly"],
        "industry_risks": ["Competitive pricing pressure during downturns", "Channel inventory corrections"],
        "idiosyncratic_risks": ["Geographic demand concentration (industrial hubs)", "Product mix shifts between high-value vs commodity segments"],
    },
    quant_profile={
        "cycle_exposure": {
            "industrial_capex_cycle": 0.80,
            "auto_manufacturing_cycle": 0.55,
            "channel_inventory_correction": 0.65,
        },
        "supplier_dependency_risk": {
            "precision_optics_dependency": 0.45,
            "components_supply_dependency": 0.40,
        },
        "customer_concentration_risk": {
            "integrator_channel_dependency": 0.55,
            "end_market_concentration": 0.55,
        },
        "capital_intensity": {
            "rnd_intensity": 0.50,
            "manufacturing_complexity": 0.45,
        },
        "moat_profile": {
            "vertical_integration_cost_advantage": 0.60,
            "reliability_reputation": 0.55,
            "performance_differentiation": 0.50,
        },
    },
    narrative={
        "one_liner": "Industrial laser cycle: high sensitivity to manufacturing capex, with moat in integration/performance but real pricing pressure in downcycles.",
        "bull_case": "Industrial utilization improves; automation investments rise; higher-value applications expand; pricing stabilizes.",
        "bear_case": "Industrial capex freezes; channel correction hits shipments; competitive pricing compresses margins.",
        "watch_items": ["Industrial PMI/capex tone", "Channel inventory", "Auto manufacturing trends", "Mix (high-power vs commodity)"],
    },
    source_note="Deterministic institutional template (no live fundamentals)."
)

# ---- NVDA (Institutional++ Deep) ----
CHAIN["NVDA"] = _schema(
    ticker="NVDA",
    business_model=[
        "Compute platform company: accelerated compute for AI training/inference across GPUs, networking, and full-stack software ecosystem.",
        "Economic engine: datacenter AI capex cycles + platform share; demand is shaped by hyperscaler buildouts, model scaling, and inference deployment.",
        "Moat: CUDA/software ecosystem, developer mindshare, platform integration (GPU + networking + systems), and pace of roadmap execution."
    ],
    revenue_mix={
        "datacenter_ai": "dominant",
        "networking": "meaningful and strategic",
        "gaming": "cyclical smaller relative to AI",
        "auto_edge": "option/long-cycle",
        "notes": (
            "Datacenter AI is primary driver; networking and systems integration increase attach and lock-in. "
            "Non-AI segments add cyclicality but are no longer the main determinant of near-term earnings."
        ),
    },
    pricing_power=(
        "Very high in constrained supply regimes and when performance-per-watt and time-to-market are decisive; "
        "moderates over time as competition and supply scale, but platform lock-in can preserve pricing umbrella."
    ),
    suppliers=[
        {"name": "TSMC", "role": "Leading-edge foundry capacity; roadmap cadence and allocation are critical"},
        {"name": "Advanced packaging ecosystem", "role": "2.5D/3D integration (CoWoS-class) is a gating constraint for AI accelerators"},
        {"name": "HBM memory supply chain", "role": "HBM availability and quality gate system shipments and cost structure"},
        {"name": "Substrate/component ecosystem", "role": "ABF substrates, power delivery, and high-speed IO components constrain scale"},
    ],
    customers=[
        {"group": "Hyperscalers / cloud", "examples": ["MSFT", "AMZN", "GOOGL", "META", "ORCL"]},
        {"group": "Enterprise AI + server OEMs", "examples": ["DELL", "HPE", "SMCI-like peers (industry context)"]},
        {"group": "Sovereign / national labs / HPC", "examples": ["Public sector HPC buyers (industry context)"]},
        {"group": "Platform ecosystem partners", "examples": ["Networking OEMs", "System integrators"]},
    ],
    products_to_customers_map={
        "AI accelerators (training/inference)": ["Hyperscalers / cloud", "Enterprise AI + server OEMs", "Sovereign / national labs / HPC"],
        "Networking (high-speed interconnect)": ["Hyperscalers / cloud", "Enterprise AI + server OEMs", "Platform ecosystem partners"],
        "Full-stack platforms (systems + software)": ["Hyperscalers / cloud", "Enterprise AI + server OEMs"],
        "Edge/auto compute (long-cycle)": ["Platform ecosystem partners"],
    },
    value_chain=[
        "AI model scaling → compute demand → hyperscaler capex → capacity constraints (HBM/packaging/foundry) → shipments.",
        "Platform transitions occur in waves; digestion phases can follow large buildouts when customers pause to deploy and optimize utilization.",
        "Inference growth shifts demand to efficiency/TCO and may broaden competition; software ecosystem increases stickiness."
    ],
    competitive_landscape=["AMD", "AVGO (custom silicon adjacency)", "Hyperscaler in-house accelerators (industry context)", "Other accelerator ecosystems"],
    risk_struct={
        "macro_risks": ["Capex slowdowns or higher rates can pause hyperscaler builds", "Risk-off can compress multiples even if fundamentals are solid"],
        "industry_risks": ["Post-buildout digestion phases and inventory timing", "Competition via custom silicon and alternative accelerators as inference matures"],
        "idiosyncratic_risks": [
            "Supply chain chokepoints (HBM, packaging, substrates) cap near-term upside",
            "Customer concentration in hyperscalers; bargaining power increases as supply loosens",
            "Regulatory/export constraints affecting certain regions and product mixes",
        ],
    },
    quant_profile={
        "cycle_exposure": {
            "hyperscaler_ai_capex": 0.90,
            "deployment_digestion_risk": 0.70,
            "inference_efficiency_shift": 0.60,
        },
        "supplier_dependency_risk": {
            "foundry_dependence": 0.80,
            "hbm_dependency": 0.85,
            "advanced_packaging_dependency": 0.85,
            "substrate_component_constraints": 0.75,
        },
        "customer_concentration_risk": {
            "hyperscaler_mix_weight": 0.85,
            "top_customer_bargaining_power": 0.70,
        },
        "capital_intensity": {
            "rnd_intensity": 0.75,
            "platform_roadmap_investment": 0.75,
        },
        "moat_profile": {
            "software_ecosystem_lock_in": 0.90,
            "platform_integration": 0.80,
            "roadmap_execution": 0.80,
            "developer_mindshare": 0.85,
        },
    },
    narrative={
        "one_liner": "AI platform tollbooth: strongest when capex and deployment accelerate; main risks are digestion phases and supply-chain chokepoints.",
        "bull_case": "AI spend persists; supply constraints ease without pricing collapse; platform attach (networking/software) deepens lock-in.",
        "bear_case": "Capex pauses/digestion; custom silicon displaces some demand; supply loosens and pricing umbrella compresses; export limits hit mix.",
        "watch_items": ["Hyperscaler AI capex tone", "HBM + packaging capacity", "Inference demand vs training mix", "Competitive custom silicon adoption"],
    },
    source_note="Deterministic institutional template (no live fundamentals)."
)

# ---- AMD (Institutional++ Deep) ----
CHAIN["AMD"] = _schema(
    ticker="AMD",
    business_model=[
        "Compute and datacenter silicon supplier across CPUs and GPUs with increasing AI accelerator exposure.",
        "Economic engine: datacenter CPU refresh cycles + AI accelerator adoption; gains are driven by competitive performance and platform ecosystem.",
        "Moat: chiplet design competency, performance-per-watt in certain segments, and ability to leverage foundry roadmap."
    ],
    revenue_mix={
        "datacenter_cpus": "large",
        "ai_gpus_accelerators": "growing option",
        "client": "cyclical",
        "embedded_other": "variable",
        "notes": "Datacenter growth and AI accelerator penetration are the key swing factors; client PC adds cyclicality."
    },
    pricing_power=(
        "Moderate-to-strong when competitive at performance/TCO and supply is tight; weaker in client downcycles and when competition intensifies."
    ),
    suppliers=[
        {"name": "TSMC", "role": "Leading-edge manufacturing; allocation and node timing influence competitiveness"},
        {"name": "Advanced packaging ecosystem", "role": "Chiplet packaging and high-density integration for datacenter parts"},
        {"name": "HBM supply chain", "role": "For AI accelerators, HBM availability gates shipments and mix"},
    ],
    customers=[
        {"group": "Hyperscalers / cloud", "examples": ["MSFT", "AMZN", "GOOGL", "META", "ORCL"]},
        {"group": "Enterprise/server OEMs", "examples": ["DELL", "HPE", "Lenovo"]},
        {"group": "PC OEMs", "examples": ["HPQ", "DELL", "Lenovo"]},
    ],
    products_to_customers_map={
        "Datacenter CPUs": ["Hyperscalers / cloud", "Enterprise/server OEMs"],
        "AI accelerators (GPUs)": ["Hyperscalers / cloud", "Enterprise/server OEMs"],
        "Client CPUs/GPUs": ["PC OEMs"],
        "Embedded compute (selected)": ["Enterprise/server OEMs"],
    },
    value_chain=[
        "Server refresh → platform qualification → volume ramps; share shifts occur at performance inflections and platform transitions.",
        "AI accelerators depend on software ecosystem and system integration; HBM/packaging constraints can gate near-term ramps.",
        "Client segments amplify volatility via channel inventory cycles."
    ],
    competitive_landscape=["INTC (CPUs)", "NVDA (AI accelerators)", "ARM ecosystem (some server silicon)"],
    risk_struct={
        "macro_risks": ["Enterprise IT pauses and PC weakness pressure volumes"],
        "industry_risks": ["Competitive price/performance battles; platform transitions can shift share quickly"],
        "idiosyncratic_risks": ["Software ecosystem gap vs incumbent in AI", "Supply chain constraints for HBM/packaging", "Customer concentration in hyperscalers"],
    },
    quant_profile={
        "cycle_exposure": {
            "datacenter_refresh_cycle": 0.70,
            "hyperscaler_capex": 0.65,
            "pc_cycle": 0.60,
            "ai_accelerator_adoption": 0.65,
        },
        "supplier_dependency_risk": {
            "foundry_dependence": 0.80,
            "advanced_packaging_dependency": 0.60,
            "hbm_dependency": 0.70,
        },
        "customer_concentration_risk": {
            "hyperscaler_mix_weight": 0.70,
            "top_customer_bargaining_power": 0.60,
        },
        "capital_intensity": {
            "rnd_intensity": 0.70,
            "platform_nre_intensity": 0.65,
        },
        "moat_profile": {
            "chiplet_architecture_strength": 0.70,
            "performance_tco_competitiveness": 0.65,
            "execution_roadmap": 0.65,
        },
    },
    narrative={
        "one_liner": "Compute challenger: upside on datacenter share and AI ramp; risks are ecosystem gaps, supply constraints, and platform competition cycles.",
        "bull_case": "Datacenter share gains persist; AI accelerators ramp with improved software/system support; supply constraints ease smoothly.",
        "bear_case": "Share gains stall; AI ecosystem adoption lags; PC downcycle persists; hyperscaler bargaining compresses pricing.",
        "watch_items": ["Server benchmarks/share", "AI accelerator pipeline + software stack", "HBM/packaging availability", "PC channel inventory"],
    },
    source_note="Deterministic institutional template (no live fundamentals)."
)

# ---- AVGO (Institutional++ Deep) ----
CHAIN["AVGO"] = _schema(
    ticker="AVGO",
    business_model=[
        "Diversified semiconductor supplier with strong positions in networking, broadband, storage connectivity, and custom silicon (where applicable).",
        "Economic engine: hyperscaler/networking capex cycles + high-value connectivity franchises; custom programs can be lumpy but sticky once integrated.",
        "Moat: deep customer relationships, breadth of connectivity portfolio, and ability to deliver high-performance silicon at scale."
    ],
    revenue_mix={
        "datacenter_networking": "large",
        "broadband_connectivity": "meaningful",
        "storage_connectivity": "meaningful",
        "custom_silicon": "strategic option",
        "notes": "Capex cycles drive volatility; custom programs and large platforms create concentration risk but also stickiness."
    },
    pricing_power=(
        "Strong in critical connectivity and custom silicon; moderated by large-customer bargaining power and capex timing."
    ),
    suppliers=[
        {"name": "Foundry partners", "role": "Advanced node manufacturing for high-performance connectivity and custom silicon"},
        {"name": "Packaging ecosystem", "role": "High-speed IO packaging and signal integrity constraints"},
        {"name": "IP/SerDes ecosystem", "role": "High-speed interface validation and ecosystem compatibility"},
    ],
    customers=[
        {"group": "Hyperscalers / cloud", "examples": ["MSFT", "AMZN", "GOOGL", "META", "ORCL"]},
        {"group": "Networking OEMs", "examples": ["CSCO", "Arista-like peers (industry context)"]},
        {"group": "Broadband/telecom OEMs", "examples": ["Telecom equipment OEMs (industry context)"]},
        {"group": "Storage/enterprise OEMs", "examples": ["DELL", "HPE"]},
    ],
    products_to_customers_map={
        "Switching/interconnect silicon": ["Hyperscalers / cloud", "Networking OEMs"],
        "Custom accelerators/connectivity": ["Hyperscalers / cloud"],
        "Broadband SoCs/connectivity": ["Broadband/telecom OEMs"],
        "Storage connectivity/controllers": ["Storage/enterprise OEMs", "Hyperscalers / cloud"],
    },
    value_chain=[
        "Bandwidth demand growth → switch/optical/interconnect content rises; hyperscaler capex cadence gates near-term demand.",
        "Design wins are sticky; digestion phases after large builds can pause orders; custom programs have long ramps but strong lock-in once deployed."
    ],
    competitive_landscape=["MRVL", "NVDA (networking adjacency)", "Other connectivity peers (industry context)"],
    risk_struct={
        "macro_risks": ["Capex slowdowns reduce orders", "Enterprise/networking digestion phases"],
        "industry_risks": ["Inventory corrections in networking/broadband channels", "Customer pushes for cost-down over time"],
        "idiosyncratic_risks": ["Concentration in a few large customers/programs", "Foundry/packaging constraints", "Program timing slips in custom ramps"],
    },
    quant_profile={
        "cycle_exposure": {
            "hyperscaler_capex": 0.75,
            "networking_upgrade_cycle": 0.65,
            "broadband_cycle": 0.55,
        },
        "supplier_dependency_risk": {
            "foundry_dependence": 0.65,
            "packaging_signal_integrity_dependency": 0.55,
        },
        "customer_concentration_risk": {
            "designwin_concentration": 0.75,
            "top_customer_bargaining_power": 0.70,
        },
        "capital_intensity": {
            "rnd_intensity": 0.60,
            "nre_intensity_custom": 0.60,
        },
        "moat_profile": {
            "portfolio_breadth_connectivity": 0.70,
            "customer_relationship_depth": 0.70,
            "qualification_switching_costs": 0.65,
        },
    },
    narrative={
        "one_liner": "Connectivity heavyweight: wins when hyperscaler/network spend rises; risks are digestion phases and concentration in large programs.",
        "bull_case": "Capex stays elevated; custom programs scale; networking upgrades accelerate; pricing remains rational.",
        "bear_case": "Capex digestion extends; inventory corrections hit shipments; large customers push cost-down and diversify suppliers.",
        "watch_items": ["Hyperscaler capex tone", "Networking inventory", "Custom program ramps", "Foundry/packaging constraints"],
    },
    source_note="Deterministic institutional template (no live fundamentals)."
)


# ============================================================
# Batch 8 Deepening (Group 8): Edge AI SoCs + FPGA + Semi materials + Test/inspection handlers
# Tickers: AMBA, LSCC, ENTG, COHU
# ============================================================

# ---- AMBA (Deep) ----
CHAIN["AMBA"] = _schema(
    ticker="AMBA",
    business_model=[
        "Edge AI and vision SoC supplier, historically strong in video/imaging pipelines and increasingly focused on AI inference at the edge.",
        "Economic engine: design wins in automotive (ADAS/central compute/vision) and select industrial/IoT vision applications; long qualification cycles create stickiness.",
        "Volatility drivers: program timing, auto platform ramps, and customer concentration in key design wins."
    ],
    revenue_mix={
        "automotive_adas": "growing/dominant direction",
        "industrial_edge_ai": "meaningful option",
        "legacy_video_security": "declining/variable",
        "notes": "Auto ramps can be lumpy but long-cycle; legacy video exposure adds transition risk as product mix shifts."
    },
    pricing_power=(
        "Moderate: stronger in differentiated ADAS/edge AI platforms with deep integration; weaker in commoditized vision/video segments."
    ),
    suppliers=[
        {"name": "Foundry partners", "role": "SoC manufacturing; node timing affects performance/power competitiveness"},
        {"name": "Packaging/test ecosystem", "role": "Automotive-grade reliability and test requirements"},
        {"name": "Software/toolchain ecosystem", "role": "SDKs and model deployment tooling drive adoption and lock-in"},
    ],
    customers=[
        {"group": "Automotive OEMs/Tier1", "examples": ["ADAS Tier1 suppliers", "Auto OEM compute platforms (industry context)"]},
        {"group": "Industrial/IoT OEMs", "examples": ["Robotics", "Machine vision", "Edge gateways"]},
        {"group": "Security/video OEMs", "examples": ["Legacy camera/security OEMs (industry context)"]},
    ],
    products_to_customers_map={
        "ADAS/vision SoCs": ["Automotive OEMs/Tier1"],
        "Edge AI inference SoCs": ["Automotive OEMs/Tier1", "Industrial/IoT OEMs"],
        "Legacy video processing SoCs": ["Security/video OEMs"],
    },
    value_chain=[
        "Auto platform planning → design-in → functional safety/qualification → SOP ramp → multi-year shipments.",
        "Edge AI adoption requires tooling + model support; ecosystem maturity increases stickiness and reduces churn."
    ],
    competitive_landscape=["Mobile/edge SoC peers (industry context)", "NVDA (edge/auto adjacency)", "QCOM (auto/edge adjacency)"],
    risk_struct={
        "macro_risks": ["Auto production downturn delays ramps", "Industrial demand softness reduces edge deployments"],
        "industry_risks": ["Auto program timing risk and platform cancellations", "Competitive displacement at platform transitions"],
        "idiosyncratic_risks": ["Customer/program concentration", "Execution risk in transitioning away from legacy markets", "Software ecosystem adoption pace"],
    },
    quant_profile={
        "cycle_exposure": {
            "auto_cycle": 0.60,
            "program_timing_risk": 0.75,
            "industrial_edge_cycle": 0.45,
        },
        "supplier_dependency_risk": {
            "foundry_dependence": 0.60,
            "automotive_quality_dependency": 0.55,
            "software_stack_dependency": 0.60,
        },
        "customer_concentration_risk": {
            "top_program_weight": 0.75,
            "tier1_dependency": 0.65,
        },
        "capital_intensity": {
            "rnd_intensity": 0.70,
            "platform_nre_intensity": 0.65,
        },
        "moat_profile": {
            "vision_domain_expertise": 0.65,
            "auto_qualification_stickiness": 0.65,
            "software_sdk_stickiness": 0.55,
        },
    },
    narrative={
        "one_liner": "Edge AI/vision design-in story: best when auto ramps execute; biggest risk is program concentration and timing slippage.",
        "bull_case": "ADAS/edge AI design wins ramp on schedule; software ecosystem adoption improves; mix shifts to higher-value auto platforms.",
        "bear_case": "Auto ramps delayed or cancelled; customer concentration bites; legacy markets fade faster than new wins scale.",
        "watch_items": ["Auto SOP timing", "Design win pipeline", "Customer concentration", "Toolchain/software adoption"],
    },
    source_note="Deterministic institutional template (no live fundamentals)."
)

# ---- LSCC (Deep) ----
CHAIN["LSCC"] = _schema(
    ticker="LSCC",
    business_model=[
        "FPGA supplier focused on low-power and mid-range FPGAs used in communications, industrial, and embedded applications.",
        "Economic engine: design wins in long-lived embedded systems; stickiness from qualification and firmware/software integration.",
        "Cyclicality is typically tied to comms/industrial capex and inventory corrections more than bleeding-edge compute cycles."
    ],
    revenue_mix={
        "communications": "meaningful",
        "industrial": "meaningful",
        "consumer": "smaller/variable",
        "notes": "Embedded wins are durable; comms cycles can be lumpy around infrastructure upgrades."
    },
    pricing_power=(
        "Moderate: better in differentiated low-power niches; competitive pressure exists vs other FPGA/ASIC approaches."
    ),
    suppliers=[
        {"name": "Foundry partners", "role": "Manufacturing for FPGA fabric; node choices influence power and cost"},
        {"name": "Packaging/test ecosystem", "role": "Reliability and lifecycle support for embedded customers"},
        {"name": "EDA/tools ecosystem", "role": "FPGA toolchains and IP cores are key to customer stickiness"},
    ],
    customers=[
        {"group": "Comms infrastructure OEMs", "examples": ["Wireless infrastructure OEMs", "Networking equipment OEMs"]},
        {"group": "Industrial OEMs", "examples": ["Automation", "Machine control", "Embedded systems"]},
        {"group": "Aerospace/defense adjacencies", "examples": ["Long-life embedded programs (industry context)"]},
    ],
    products_to_customers_map={
        "Low-power FPGAs": ["Industrial OEMs", "Comms infrastructure OEMs", "Aerospace/defense adjacencies"],
        "Mid-range FPGAs + IP": ["Comms infrastructure OEMs", "Industrial OEMs"],
        "Toolchains/IP cores": ["Industrial OEMs", "Comms infrastructure OEMs"],
    },
    value_chain=[
        "System requirements → FPGA selection/design-in → firmware/IP integration → qualification → multi-year shipments and support.",
        "Infrastructure upgrade cycles can create demand spikes followed by digestion; embedded base supports stability."
    ],
    competitive_landscape=["Xilinx/AMD FPGA ecosystem (industry context)", "Intel PSG (industry context)", "ASIC/ASSP alternatives"],
    risk_struct={
        "macro_risks": ["Industrial and comms capex pauses reduce orders"],
        "industry_risks": ["Inventory corrections after supply tightness", "Design displacement by ASICs/ASSPs in high-volume applications"],
        "idiosyncratic_risks": ["Customer concentration in certain comms programs", "Toolchain competitiveness and developer adoption"],
    },
    quant_profile={
        "cycle_exposure": {
            "communications_capex_cycle": 0.60,
            "industrial_cycle": 0.55,
            "inventory_correction_risk": 0.55,
        },
        "supplier_dependency_risk": {
            "foundry_dependence": 0.55,
            "toolchain_dependency": 0.60,
        },
        "customer_concentration_risk": {
            "program_concentration": 0.60,
            "comms_mix_concentration": 0.55,
        },
        "capital_intensity": {
            "rnd_intensity": 0.55,
            "platform_nre_intensity": 0.50,
        },
        "moat_profile": {
            "embedded_lifecycle_stickiness": 0.65,
            "low_power_niche_positioning": 0.60,
            "toolchain_ip_ecosystem": 0.55,
        },
    },
    narrative={
        "one_liner": "Embedded FPGA supplier: sticky design-ins with comms/industrial cycle sensitivity; watch inventory and infrastructure upgrade cadence.",
        "bull_case": "Comms upgrades resume; industrial stabilizes; embedded wins compound with long lifecycle support.",
        "bear_case": "Capex digestion extends; inventory correction hits orders; ASIC displacement pressures growth in some segments.",
        "watch_items": ["Comms capex tone", "Industrial order trends", "Toolchain adoption", "Inventory indicators"],
    },
    source_note="Deterministic institutional template (no live fundamentals)."
)

# ---- ENTG (Deep) ----
CHAIN["ENTG"] = _schema(
    ticker="ENTG",
    business_model=[
        "Semiconductor materials and contamination control supplier: filtration, chemicals handling, and advanced materials used in wafer fab processes.",
        "Economic engine: WFE/fab utilization + increasing process complexity (more steps, tighter tolerances) which raises consumables intensity per wafer.",
        "Resilience comes from recurring consumables and installed-base penetration, but spending still correlates with fab capex cycles."
    ],
    revenue_mix={
        "contamination_control": "core recurring",
        "materials_handling": "core",
        "advanced_materials": "meaningful/variable",
        "notes": "Consumables provide stability; new fab builds and node transitions drive bursts of demand."
    },
    pricing_power=(
        "Moderate: strong where qualification and yield impact are material; customer cost-down pressure exists over time."
    ),
    suppliers=[
        {"name": "Specialty materials ecosystem", "role": "Polymers, chemicals, and precision components"},
        {"name": "Manufacturing/quality ecosystem", "role": "High purity and reliability standards gate supplier qualification"},
        {"name": "Logistics and service network", "role": "On-site support and rapid replacement drive stickiness"},
    ],
    customers=[
        {"group": "Leading-edge foundries", "examples": ["TSM", "Samsung Foundry (industry context)"]},
        {"group": "Memory fabs", "examples": ["MU", "Other memory peers (industry context)"]},
        {"group": "IDMs", "examples": ["INTC", "Other IDMs (industry context)"]},
    ],
    products_to_customers_map={
        "Filtration/contamination control consumables": ["Leading-edge foundries", "Memory fabs", "IDMs"],
        "Chemicals handling / delivery systems": ["Leading-edge foundries", "Memory fabs", "IDMs"],
        "Advanced materials (selected)": ["Leading-edge foundries", "Memory fabs"],
    },
    value_chain=[
        "Node complexity increases → more process steps and tighter purity requirements → higher consumables intensity per wafer.",
        "New fab builds and node ramps pull forward demand; digestion phases can follow capex peaks, but installed base supports recurring streams."
    ],
    competitive_landscape=["Other specialty materials and contamination control suppliers (industry context)"],
    risk_struct={
        "macro_risks": ["WFE downturn reduces new equipment installs and slows expansions"],
        "industry_risks": ["Customer capex digestion phases", "Pricing pressure via supplier consolidation and cost-down initiatives"],
        "idiosyncratic_risks": ["Quality incidents can cause rapid disqualification", "Customer concentration in top fabs"],
    },
    quant_profile={
        "cycle_exposure": {
            "wfe_cycle_sensitivity": 0.65,
            "fab_utilization_sensitivity": 0.60,
            "node_complexity_tailwind": 0.55,
        },
        "supplier_dependency_risk": {
            "quality_purity_dependency": 0.70,
            "materials_supply_dependency": 0.45,
        },
        "customer_concentration_risk": {
            "top_fab_concentration": 0.70,
            "few_customer_industry_structure": 0.65,
        },
        "capital_intensity": {
            "manufacturing_complexity": 0.45,
            "rnd_intensity": 0.45,
        },
        "moat_profile": {
            "qualification_stickiness": 0.70,
            "installed_base_consumables": 0.65,
            "process_criticality": 0.60,
        },
    },
    narrative={
        "one_liner": "Fab consumables and contamination control: benefits from process complexity and installed base; watch WFE/utilization cycles and quality execution.",
        "bull_case": "Node ramps and new fabs drive demand; consumables intensity rises; strong quality performance supports share.",
        "bear_case": "Capex digestion slows installs; utilization dips; pricing pressure rises; any quality incident causes rapid downside.",
        "watch_items": ["WFE cycle", "Fab utilization", "Node ramp cadence", "Quality/qualification signals"],
    },
    source_note="Deterministic institutional template (no live fundamentals)."
)

# ---- COHU (Deep) ----
CHAIN["COHU"] = _schema(
    ticker="COHU",
    business_model=[
        "Semiconductor test/inspection and handling equipment supplier with exposure to unit cycles and device mix (auto/industrial reliability needs).",
        "Economic engine: OSAT/IDM test capacity adds and handler demand; cyclicality driven by semiconductor unit cycle and customer capex timing.",
        "Differentiation: specific test/handler niches, reliability, and installed base/service; still capex-driven with digestion phases."
    ],
    revenue_mix={
        "test_handlers_and_interface": "core cyclical",
        "inspection_metrology": "variable",
        "services": "stabilizer",
        "notes": "Autos/industrial reliability can support mix, but spending still follows capex waves."
    },
    pricing_power=(
        "Moderate in niche handler/test segments with qualification; weaker in broad downturns where customers delay capex."
    ),
    suppliers=[
        {"name": "Precision components supply chain", "role": "Motion control, electronics, and measurement subsystems"},
        {"name": "Probe/interface ecosystem", "role": "Interfaces and contactors are critical for uptime and yield"},
        {"name": "Software/automation ecosystem", "role": "Test automation and analytics improve customer stickiness"},
    ],
    customers=[
        {"group": "OSATs", "examples": ["ASE-like peers (industry context)", "Amkor-like peers (industry context)"]},
        {"group": "IDMs", "examples": ["INTC", "MU", "Auto-focused IDMs (industry context)"]},
        {"group": "Auto/industrial supply chains", "examples": ["Reliability-driven test programs (industry context)"]},
    ],
    products_to_customers_map={
        "Handlers + automation": ["OSATs", "IDMs"],
        "Test interface/probe systems": ["OSATs", "IDMs"],
        "Inspection/metrology (selected)": ["OSATs", "IDMs"],
        "Service/consumables": ["OSATs", "IDMs"],
    },
    value_chain=[
        "Unit demand and device transitions → test capacity needs → capex waves; digestion phases follow after customers add capacity.",
        "Auto/industrial reliability requirements can increase test intensity and support steadier spending in certain programs."
    ],
    competitive_landscape=["TER (test)", "Other handler/test peers (industry context)"],
    risk_struct={
        "macro_risks": ["Broad semi downturn reduces capex quickly"],
        "industry_risks": ["Capex digestion cycles at OSATs/IDMs", "Competitive pricing in handlers/test"],
        "idiosyncratic_risks": ["Customer concentration", "Timing lag between silicon demand and test orders", "Execution/field reliability issues"],
    },
    quant_profile={
        "cycle_exposure": {
            "semi_unit_cycle": 0.75,
            "capex_digestion_risk": 0.70,
            "auto_reliability_mix_support": 0.45,
        },
        "supplier_dependency_risk": {
            "precision_components": 0.45,
            "interface_dependency": 0.55,
        },
        "customer_concentration_risk": {
            "top_customer_weight": 0.60,
            "osat_dependency": 0.55,
        },
        "capital_intensity": {
            "rnd_intensity": 0.45,
            "manufacturing_complexity": 0.40,
        },
        "moat_profile": {
            "installed_base_service_lock": 0.55,
            "niche_handler_positioning": 0.50,
            "reliability_reputation": 0.50,
        },
    },
    narrative={
        "one_liner": "Test/handling capex cycle: benefits from reliability and installed base, but remains tied to OSAT/IDM capex waves and digestion phases.",
        "bull_case": "Capacity adds resume; auto/industrial reliability drives higher test intensity; service mix supports profitability.",
        "bear_case": "Semi downturn extends; customers pause capex; digestion lasts longer; pricing pressure reduces leverage.",
        "watch_items": ["OSAT/IDM capex tone", "Unit demand", "Auto/industrial mix", "Service mix and backlog"],
    },
    source_note="Deterministic institutional template (no live fundamentals)."
)


# ============================================================
# Batch 9 Deepening (Group 9): Semi Equipment Institutional++ (second-pass)
# Tickers: ASML, AMAT, LRCX, KLAC (overwrite with deeper versions)
# ============================================================

# ---- ASML (Institutional++ Deep) ----
CHAIN["ASML"] = _schema(
    ticker="ASML",
    business_model=[
        "Critical lithography equipment supplier enabling advanced-node scaling; structural bottleneck in the semiconductor value chain.",
        "Economic engine: multi-year tool backlog + service/upgrade stream; demand driven by leading-edge node transitions and capacity adds at top fabs.",
        "Moat: extreme engineering complexity, ecosystem integration, and years-long customer qualification; substitution risk is extremely low."
    ],
    revenue_mix={
        "lithography_systems": "dominant (multi-year)",
        "service_upgrades": "large and recurring",
        "notes": "Service stabilizes; system revenue follows capex waves but is buffered by backlog and long lead times."
    },
    pricing_power=(
        "Very high due to near-monopoly dynamics in key tool categories; tempered mainly by customer bargaining and political/regulatory constraints."
    ),
    suppliers=[
        {"name": "Ultra-precision optics ecosystem", "role": "High-end optics are mission-critical; quality/schedule directly impact shipments"},
        {"name": "Light source subsystem ecosystem", "role": "EUV source performance and uptime determine tool productivity"},
        {"name": "Mechatronics and control systems", "role": "Extreme precision motion and feedback systems underpin yield"},
        {"name": "Specialty materials/components", "role": "High reliability parts; supply disruptions can constrain output"},
    ],
    customers=[
        {"group": "Leading-edge foundries", "examples": ["TSM", "Samsung Foundry (industry context)"]},
        {"group": "Advanced IDMs", "examples": ["INTC"]},
        {"group": "Memory leaders (selected)", "examples": ["Leading memory fabs (industry context)"]},
    ],
    products_to_customers_map={
        "EUV lithography systems": ["Leading-edge foundries", "Advanced IDMs"],
        "DUV lithography systems": ["Leading-edge foundries", "Advanced IDMs", "Memory leaders (selected)"],
        "Service, upgrades, productivity packages": ["Leading-edge foundries", "Advanced IDMs", "Memory leaders (selected)"],
    },
    value_chain=[
        "Node roadmap → fab planning → lithography capacity orders → long lead manufacturing → installation and qualification → productivity upgrades over time.",
        "Industry downturns can delay customer capex, but installed base service and strategic node transitions preserve baseline demand.",
        "Geopolitics/export rules can redirect demand and influence order timing."
    ],
    competitive_landscape=["(Effectively none in EUV)", "DUV niche competitors (industry context)"],
    risk_struct={
        "macro_risks": ["WFE downturn delays tool deliveries/acceptance timing"],
        "industry_risks": ["Customer capex digestion phases can slow incremental orders", "Supply chain bottlenecks in critical subsystems cap output"],
        "idiosyncratic_risks": ["Export/regulatory constraints", "Execution risk in next-gen roadmap and productivity targets", "Supplier concentration in optics/source subsystems"],
    },
    quant_profile={
        "cycle_exposure": {
            "wfe_cycle_sensitivity": 0.60,
            "leading_edge_node_transition": 0.80,
            "backlog_buffering": 0.60,
        },
        "supplier_dependency_risk": {
            "critical_supplier_concentration": 0.75,
            "subsystem_throughput_dependency": 0.70,
        },
        "customer_concentration_risk": {
            "top_fab_concentration": 0.80,
            "few_customer_industry_structure": 0.75,
        },
        "capital_intensity": {
            "rnd_intensity": 0.75,
            "manufacturing_complexity": 0.75,
        },
        "moat_profile": {
            "substitution_barrier": 0.95,
            "ecosystem_integration": 0.85,
            "installed_base_service": 0.70,
        },
    },
    narrative={
        "one_liner": "Lithography bottleneck: structurally indispensable with strong service recurrence; main risks are geopolitics and supply-chain throughput.",
        "bull_case": "Leading-edge transitions accelerate; backlog converts smoothly; productivity upgrades lift service and system ASPs.",
        "bear_case": "WFE downturn delays acceptance; export constraints reshape demand; subsystem bottlenecks limit shipments and margins.",
        "watch_items": ["Backlog/lead times", "EUV productivity and uptime", "Customer capex plans", "Export policy headlines", "Supplier throughput"],
    },
    source_note="Deterministic institutional template (no live fundamentals)."
)

# ---- AMAT (Institutional++ Deep) ----
CHAIN["AMAT"] = _schema(
    ticker="AMAT",
    business_model=[
        "Broad WFE supplier spanning deposition, etch, CMP, metrology/inspection adjacencies and services; leveraged to wafer fab capex and process complexity.",
        "Economic engine: WFE cycles + rising steps per wafer as nodes scale and packaging advances; services and installed base buffer cyclicality.",
        "Moat: breadth across process steps, co-optimization with customers, and large installed base."
    ],
    revenue_mix={
        "wfe_systems": "dominant cyclical",
        "services": "large stabilizer",
        "notes": "End-market exposure diversified across foundry, memory, and logic; memory cycles can amplify volatility."
    },
    pricing_power=(
        "Moderate-to-strong in differentiated process modules and where co-optimization improves yield; still subject to customer cost-down over time."
    ),
    suppliers=[
        {"name": "Precision components ecosystem", "role": "Vacuum, RF power, motion control subsystems"},
        {"name": "Materials and consumables ecosystem", "role": "Chambers/liners and consumables influence uptime and margins"},
        {"name": "Service logistics network", "role": "Field service responsiveness drives stickiness"},
    ],
    customers=[
        {"group": "Leading-edge foundries", "examples": ["TSM", "Samsung Foundry (industry context)"]},
        {"group": "IDMs", "examples": ["INTC", "Other IDMs (industry context)"]},
        {"group": "Memory fabs", "examples": ["MU", "Other memory peers (industry context)"]},
    ],
    products_to_customers_map={
        "Deposition (CVD/PVD/ALD etc.)": ["Leading-edge foundries", "IDMs", "Memory fabs"],
        "Etch / patterning adjacencies": ["Leading-edge foundries", "IDMs", "Memory fabs"],
        "CMP and planarization": ["Leading-edge foundries", "IDMs", "Memory fabs"],
        "Service and spares": ["Leading-edge foundries", "IDMs", "Memory fabs"],
    },
    value_chain=[
        "Node transitions and capacity adds → WFE orders; complexity increases steps per wafer, supporting structural demand.",
        "Downcycles create digestion phases where tool demand pauses; service and upgrade streams smooth results.",
        "Memory capex swings can be sharper than logic, influencing near-term variability."
    ],
    competitive_landscape=["LRCX", "KLAC (inspection adjacency)", "ASML (litho)", "Other WFE peers (industry context)"],
    risk_struct={
        "macro_risks": ["WFE downturn and customer capex pauses"],
        "industry_risks": ["Memory capex volatility", "Export controls affecting certain tool demand and mix"],
        "idiosyncratic_risks": ["Share shifts across process steps", "Execution risk in next-gen process modules", "Service attach and uptime performance"],
    },
    quant_profile={
        "cycle_exposure": {
            "wfe_cycle_sensitivity": 0.75,
            "memory_capex_volatility": 0.65,
            "process_complexity_tailwind": 0.60,
            "digestion_phase_risk": 0.65,
        },
        "supplier_dependency_risk": {
            "precision_components": 0.45,
            "field_service_dependency": 0.50,
        },
        "customer_concentration_risk": {
            "top_fab_concentration": 0.65,
            "few_customer_industry_structure": 0.60,
        },
        "capital_intensity": {
            "rnd_intensity": 0.55,
            "manufacturing_complexity": 0.50,
        },
        "moat_profile": {
            "process_step_breadth": 0.70,
            "co_optimization_yield": 0.60,
            "installed_base_service": 0.70,
        },
    },
    narrative={
        "one_liner": "Broad WFE bellwether: cyclical with capex waves, structurally supported by rising process complexity and buffered by services.",
        "bull_case": "Node ramps + advanced packaging drive more steps per wafer; service attach remains high; share stable across modules.",
        "bear_case": "Capex digestion extends, especially in memory; export constraints and pricing pressure hit mix; service growth slows.",
        "watch_items": ["Foundry vs memory capex", "Services growth/attach", "Export policy", "Customer utilization and digestion signals"],
    },
    source_note="Deterministic institutional template (no live fundamentals)."
)

# ---- LRCX (Institutional++ Deep) ----
CHAIN["LRCX"] = _schema(
    ticker="LRCX",
    business_model=[
        "WFE supplier with strong exposure to etch and deposition steps, historically levered to memory intensity and advanced patterning needs.",
        "Economic engine: WFE cycle with above-average sensitivity to memory capex; structural tailwind from 3D scaling and more patterning steps.",
        "Moat: process leadership in critical etch/deposition modules and deep customer co-optimization."
    ],
    revenue_mix={
        "etch": "core",
        "deposition": "core",
        "services": "stabilizer",
        "notes": "Memory spend is a major swing factor; logic/foundry provides diversification but memory sensitivity remains meaningful."
    },
    pricing_power=(
        "Moderate-to-strong in critical modules where yield impact is high; still subject to capex cycles and customer cost-down initiatives."
    ),
    suppliers=[
        {"name": "Precision components ecosystem", "role": "Vacuum, RF power, plasma subsystems"},
        {"name": "Materials/consumables ecosystem", "role": "Chamber parts and consumables drive service margin dynamics"},
        {"name": "Field service network", "role": "Uptime and response time increase customer stickiness"},
    ],
    customers=[
        {"group": "Memory fabs", "examples": ["MU", "Other memory peers (industry context)"]},
        {"group": "Leading-edge foundries", "examples": ["TSM", "Samsung Foundry (industry context)"]},
        {"group": "IDMs", "examples": ["INTC", "Other IDMs (industry context)"]},
    ],
    products_to_customers_map={
        "Etch systems": ["Memory fabs", "Leading-edge foundries", "IDMs"],
        "Deposition systems": ["Memory fabs", "Leading-edge foundries", "IDMs"],
        "Service/spares": ["Memory fabs", "Leading-edge foundries", "IDMs"],
    },
    value_chain=[
        "Scaling (3D NAND/advanced DRAM) and leading-edge logic → more etch/deposition steps per wafer → structural demand tailwind.",
        "Memory capex cycles are volatile; digestion phases can cause sharp order reductions; service helps buffer but remains correlated."
    ],
    competitive_landscape=["AMAT", "Other etch/deposition peers (industry context)"],
    risk_struct={
        "macro_risks": ["WFE downturn reduces tool orders"],
        "industry_risks": ["Memory capex volatility and inventory corrections", "Export constraints affect certain demand segments"],
        "idiosyncratic_risks": ["Share shifts in key process steps", "Execution risk on new modules supporting scaling", "Overexposure to a single end-market capex cycle"],
    },
    quant_profile={
        "cycle_exposure": {
            "wfe_cycle_sensitivity": 0.80,
            "memory_capex_volatility": 0.75,
            "process_complexity_tailwind": 0.60,
            "digestion_phase_risk": 0.70,
        },
        "supplier_dependency_risk": {
            "precision_components": 0.45,
            "service_consumables_dependency": 0.55,
        },
        "customer_concentration_risk": {
            "top_fab_concentration": 0.65,
            "few_customer_industry_structure": 0.60,
        },
        "capital_intensity": {
            "rnd_intensity": 0.55,
            "manufacturing_complexity": 0.50,
        },
        "moat_profile": {
            "critical_process_leadership": 0.65,
            "co_optimization_yield": 0.60,
            "installed_base_service": 0.65,
        },
    },
    narrative={
        "one_liner": "Etch/deposition leader: structural complexity tailwind but high memory capex sensitivity; watch digestion phases and memory spend turns.",
        "bull_case": "Memory capex turns up with scaling; logic/foundry stays healthy; services provide strong buffer and margins.",
        "bear_case": "Memory capex downcycle extends; digestion delays; export constraints and competition pressure mix and share.",
        "watch_items": ["Memory capex guidance", "Service growth", "Scaling intensity (3D NAND/DRAM)", "Export policy"],
    },
    source_note="Deterministic institutional template (no live fundamentals)."
)

# ---- KLAC (Institutional++ Deep) ----
CHAIN["KLAC"] = _schema(
    ticker="KLAC",
    business_model=[
        "Process control, inspection, and metrology leader: critical to yield learning and defect detection as nodes scale and packaging advances.",
        "Economic engine: WFE cycle with strong structural tailwind from rising inspection/metrology intensity per wafer and advanced packaging complexity.",
        "Moat: deep installed base, software/analytics, and mission-critical role in yield; switching costs are high."
    ],
    revenue_mix={
        "inspection_metrology_systems": "core cyclical",
        "service": "large stabilizer",
        "notes": "Intensity rises with complexity, making the category more resilient than some pure capacity tools."
    },
    pricing_power=(
        "Strong due to mission-critical yield role and high switching costs; customers still push for productivity/cost improvements over time."
    ),
    suppliers=[
        {"name": "Precision optics and sensors", "role": "Metrology accuracy depends on optics/sensor supply and calibration"},
        {"name": "High-precision mechatronics", "role": "Motion control and stability are critical for measurement fidelity"},
        {"name": "Software/compute ecosystem", "role": "Analytics, data pipelines, and algorithms drive differentiation"},
    ],
    customers=[
        {"group": "Leading-edge foundries", "examples": ["TSM", "Samsung Foundry (industry context)"]},
        {"group": "IDMs", "examples": ["INTC", "Other IDMs (industry context)"]},
        {"group": "Memory fabs", "examples": ["MU", "Other memory peers (industry context)"]},
    ],
    products_to_customers_map={
        "Inspection tools (defect detection)": ["Leading-edge foundries", "IDMs", "Memory fabs"],
        "Metrology tools (critical dimension, overlay, etc.)": ["Leading-edge foundries", "IDMs", "Memory fabs"],
        "Yield analytics / software": ["Leading-edge foundries", "IDMs", "Memory fabs"],
        "Service and spares": ["Leading-edge foundries", "IDMs", "Memory fabs"],
    },
    value_chain=[
        "As nodes shrink and packaging becomes complex, yield learning demands more measurement points and tighter defect control.",
        "Tool purchases follow capex cycles, but inspection intensity per wafer and installed base service improve resilience.",
        "Advanced packaging and new materials increase metrology needs and can shift mix toward higher-value systems."
    ],
    competitive_landscape=["AMAT (inspection adjacency)", "Other metrology/inspection peers (industry context)"],
    risk_struct={
        "macro_risks": ["WFE downturn reduces orders/acceptance timing"],
        "industry_risks": ["Capex digestion phases", "Customer cost-down initiatives can pressure pricing"],
        "idiosyncratic_risks": ["Execution risk on new measurement modalities", "Customer concentration among top fabs", "Supply constraints in precision subsystems"],
    },
    quant_profile={
        "cycle_exposure": {
            "wfe_cycle_sensitivity": 0.70,
            "process_control_intensity_tailwind": 0.75,
            "digestion_phase_risk": 0.55,
        },
        "supplier_dependency_risk": {
            "precision_optics_dependency": 0.55,
            "software_analytics_dependency": 0.60,
        },
        "customer_concentration_risk": {
            "top_fab_concentration": 0.75,
            "few_customer_industry_structure": 0.70,
        },
        "capital_intensity": {
            "rnd_intensity": 0.55,
            "manufacturing_complexity": 0.45,
        },
        "moat_profile": {
            "switching_costs_yield_role": 0.80,
            "installed_base_service": 0.70,
            "analytics_differentiation": 0.65,
        },
    },
    narrative={
        "one_liner": "Yield gatekeeper: structural winner from rising complexity with strong switching costs; still cyclical but more resilient than pure capacity tools.",
        "bull_case": "Node and packaging complexity increases inspection intensity; service expands; new modalities drive mix up.",
        "bear_case": "Capex pause delays orders; customers push cost-down; supply constraints and execution issues slow upgrades.",
        "watch_items": ["Inspection intensity trends", "Advanced packaging demand", "Service growth", "Foundry/memory capex cadence"],
    },
    source_note="Deterministic institutional template (no live fundamentals)."
)


# ============================================================
# Batch 10 Deepening (FINAL for Phase B baseline): Analog/RF/Auto + Connectivity Institutional++ (second-pass)
# Overwrites: TXN, ADI, NXPI, MCHP, ON, STM, QCOM, MRVL, SWKS, QRVO
# Goal: "Top 25–30 tradable semis" are now institutional-grade across ecosystem/chain/quant.
# ============================================================

# ---- TXN (Institutional++ Deep) ----
CHAIN["TXN"] = _schema(
    ticker="TXN",
    business_model=[
        "Analog and embedded processing supplier with massive catalog breadth; exposed to industrial and automotive content growth.",
        "Economic engine: long-lifecycle analog components designed into systems for years; revenue driven by broad industrial/auto cycles and inventory corrections.",
        "Moat: breadth, reliability, and customer support; manufacturing strategy (internal capacity where applicable) supports supply assurance and lifecycle control."
    ],
    revenue_mix={
        "industrial": "dominant",
        "automotive": "large and growing",
        "personal_electronics": "smaller/variable",
        "notes": "Industrial is the key swing factor; auto content is structural tailwind but not immune to production cycles."
    },
    pricing_power=(
        "Strong in long-life, qualified analog where switching costs and qualification are meaningful; "
        "moderated by broad-based cost-down pressure and customer inventory cycles."
    ),
    suppliers=[
        {"name": "Wafer materials + mature-node ecosystem", "role": "Analog often uses mature nodes; supply assurance and cost matter"},
        {"name": "Packaging/test ecosystem", "role": "High mix/low volume packaging and testing; reliability requirements"},
        {"name": "Distribution/channel ecosystem", "role": "Channel inventory and demand visibility are major drivers of near-term volatility"},
    ],
    customers=[
        {"group": "Industrial OEMs", "examples": ["Automation", "Factory equipment", "Power supplies", "Embedded systems"]},
        {"group": "Automotive OEMs/Tier1", "examples": ["Auto Tier1 suppliers", "EV subsystems"]},
        {"group": "Broad electronics OEMs", "examples": ["Consumer electronics supply chains (industry context)"]},
        {"group": "Distributors", "examples": ["Global distribution partners (industry context)"]},
    ],
    products_to_customers_map={
        "Power management + analog signal chain": ["Industrial OEMs", "Automotive OEMs/Tier1", "Broad electronics OEMs"],
        "Embedded MCUs/processing (selected)": ["Industrial OEMs", "Automotive OEMs/Tier1"],
        "Connectivity/interface analog": ["Industrial OEMs", "Broad electronics OEMs"],
    },
    value_chain=[
        "Analog content per system rises with electrification and automation → long design-in cycles → sticky multi-year revenue.",
        "Near-term volatility: customer/channel inventory corrections can overwhelm end-demand signal; recovery typically follows normalization of inventory.",
        "Pricing holds better in qualified parts; mix shifts (industrial vs consumer) drive margins."
    ],
    competitive_landscape=["ADI", "NXPI (auto/embedded adjacency)", "MCHP (embedded)", "Other analog peers (industry context)"],
    risk_struct={
        "macro_risks": ["Industrial recession reduces orders; broad electronics demand slows"],
        "industry_risks": ["Channel inventory corrections and demand visibility risk", "Long lead-time bullwhip effects"],
        "idiosyncratic_risks": ["Mix shifts (industrial vs consumer)", "Capacity/wafer strategy misalignment", "Pricing pressure from large OEMs"],
    },
    quant_profile={
        "cycle_exposure": {
            "industrial_cycle": 0.75,
            "auto_cycle": 0.55,
            "inventory_correction_risk": 0.75,
            "long_lifecycle_stability": 0.35,  # lower risk = more stable (but keep as factor)
        },
        "supplier_dependency_risk": {
            "mature_node_supply_dependency": 0.40,
            "packaging_test_dependency": 0.45,
            "channel_dependency": 0.65,
        },
        "customer_concentration_risk": {
            "broad_customer_diversification": 0.35,
            "channel_concentration": 0.55,
        },
        "capital_intensity": {
            "capex_intensity": 0.55,
            "rnd_intensity": 0.45,
        },
        "moat_profile": {
            "catalog_breadth": 0.85,
            "design_in_stickiness": 0.75,
            "reliability_lifecycle_support": 0.70,
        },
    },
    narrative={
        "one_liner": "Analog catalog tollbooth: structurally sticky design-ins, but cyclical through industrial demand and channel inventory corrections.",
        "bull_case": "Industrial demand rebounds; inventory normalizes; electrification and automation drive higher analog content; pricing holds.",
        "bear_case": "Industrial downturn persists; channel correction extends; large OEMs pressure pricing; recovery delayed by visibility issues.",
        "watch_items": ["Industrial order trends", "Distributor inventory", "Auto production tone", "Lead times/pricing discipline"],
    },
    source_note="Deterministic institutional template (no live fundamentals)."
)

# ---- ADI (Institutional++ Deep) ----
CHAIN["ADI"] = _schema(
    ticker="ADI",
    business_model=[
        "High-performance analog, mixed-signal, and RF signal chain supplier leveraged to industrial, auto, and communications sensing/control.",
        "Economic engine: complex signal chains in instrumentation, automation, and connectivity; long design cycles and qualification create stickiness.",
        "Moat: performance/precision, system-level expertise, and deep customer integration in mission-critical applications."
    ],
    revenue_mix={
        "industrial": "dominant",
        "automotive": "large",
        "communications": "meaningful",
        "consumer": "smaller",
        "notes": "Industrial precision applications are key; comms can be lumpy; auto is multi-year but tied to production cycles."
    },
    pricing_power=(
        "Strong in precision and mission-critical analog; customers value performance and reliability, though cost-down pressure exists."
    ),
    suppliers=[
        {"name": "Mature-node manufacturing ecosystem", "role": "Analog production stability and yield"},
        {"name": "Packaging/test ecosystem", "role": "High-mix packaging and reliability requirements"},
        {"name": "Channel ecosystem (selected)", "role": "Visibility and inventory cycles influence near-term demand"},
    ],
    customers=[
        {"group": "Industrial OEMs", "examples": ["Instrumentation", "Automation", "Aerospace/defense adjacencies (industry context)"]},
        {"group": "Automotive OEMs/Tier1", "examples": ["ADAS sensors", "EV power and control subsystems"]},
        {"group": "Comms infrastructure OEMs", "examples": ["Wireless infrastructure OEMs", "Networking equipment OEMs"]},
    ],
    products_to_customers_map={
        "Precision ADC/DAC + signal chain": ["Industrial OEMs", "Comms infrastructure OEMs"],
        "Sensors + power/management analog": ["Industrial OEMs", "Automotive OEMs/Tier1"],
        "RF/mixed-signal components": ["Comms infrastructure OEMs", "Automotive OEMs/Tier1"],
    },
    value_chain=[
        "More sensing/control complexity → more high-performance analog content per system → long design-ins drive durable revenue.",
        "Industrial cycles and inventory swings create near-term volatility; precision segments tend to be less commodity-like.",
        "In comms, upgrade cycles drive spikes followed by digestion."
    ],
    competitive_landscape=["TXN", "NXPI (auto adjacencies)", "Other high-performance analog peers (industry context)"],
    risk_struct={
        "macro_risks": ["Industrial slowdown reduces demand"],
        "industry_risks": ["Inventory correction cycles", "Comms upgrade digestion phases"],
        "idiosyncratic_risks": ["Program concentration in certain high-value segments", "Competitive pricing pressure in less differentiated products"],
    },
    quant_profile={
        "cycle_exposure": {
            "industrial_cycle": 0.70,
            "auto_cycle": 0.50,
            "comms_upgrade_cycle": 0.55,
            "inventory_correction_risk": 0.70,
        },
        "supplier_dependency_risk": {
            "mature_node_supply_dependency": 0.40,
            "packaging_test_dependency": 0.45,
            "channel_dependency": 0.55,
        },
        "customer_concentration_risk": {
            "broad_customer_diversification": 0.40,
            "segment_program_concentration": 0.55,
        },
        "capital_intensity": {
            "capex_intensity": 0.50,
            "rnd_intensity": 0.55,
        },
        "moat_profile": {
            "precision_performance_differentiation": 0.75,
            "design_in_stickiness": 0.70,
            "system_level_expertise": 0.65,
        },
    },
    narrative={
        "one_liner": "Precision analog leader: sticky design-ins with cyclical industrial and inventory swings; comms upgrades add lumpiness.",
        "bull_case": "Industrial and auto demand strengthen; precision content expands; comms upgrades accelerate; pricing holds in high-value segments.",
        "bear_case": "Industrial downturn + destocking persists; comms digestion extends; mix shifts lower; pricing pressure rises.",
        "watch_items": ["Industrial demand tone", "Inventory/lead times", "Comms upgrade cycle", "Auto production and content trends"],
    },
    source_note="Deterministic institutional template (no live fundamentals)."
)

# ---- NXPI (Institutional++ Deep) ----
CHAIN["NXPI"] = _schema(
    ticker="NXPI",
    business_model=[
        "Auto and industrial embedded leader: MCUs, connectivity, and secure processing with heavy exposure to automotive electrification and ADAS content.",
        "Economic engine: auto design wins are long-cycle with deep qualification; industrial embedded adds diversification but is cyclical.",
        "Moat: automotive-grade reliability, broad portfolio, and sticky platform relationships with Tier1s and OEMs."
    ],
    revenue_mix={
        "automotive": "dominant",
        "industrial_iot": "meaningful",
        "mobile_adjacent": "smaller",
        "notes": "Auto is structural tailwind, but near-term can be volatile via production and customer inventory cycles."
    },
    pricing_power=(
        "Strong in qualified auto programs; moderated by large-customer bargaining power and periodic semiconductor supply/inventory cycles."
    ),
    suppliers=[
        {"name": "Foundry/IDM manufacturing ecosystem", "role": "Mature and specialty nodes; supply assurance matters"},
        {"name": "Packaging/test ecosystem", "role": "Automotive qualification and reliability testing requirements"},
        {"name": "Secure element/IP ecosystem", "role": "Security and standards compliance for auto/IoT"},
    ],
    customers=[
        {"group": "Automotive Tier1s/OEMs", "examples": ["Tier1 suppliers", "Auto OEM platforms (industry context)"]},
        {"group": "Industrial OEMs", "examples": ["Automation", "Embedded systems", "Factory/energy systems"]},
        {"group": "Consumer/IoT OEMs", "examples": ["Connectivity modules and devices (industry context)"]},
    ],
    products_to_customers_map={
        "Auto MCUs + gateways": ["Automotive Tier1s/OEMs"],
        "ADAS/compute adjacencies + connectivity": ["Automotive Tier1s/OEMs"],
        "Industrial MCUs + connectivity": ["Industrial OEMs"],
        "Secure processing / NFC adjacencies": ["Industrial OEMs", "Consumer/IoT OEMs"],
    },
    value_chain=[
        "Auto platform selection → design-in → qualification → SOP ramp → multi-year shipments; switching costs are high.",
        "Electrification and software-defined vehicles increase silicon content; inventory corrections and production changes drive near-term volatility."
    ],
    competitive_landscape=["ON (power/auto)", "STM", "MCHP", "Infineon-like peers (industry context)", "TI/ADI analog adjacencies"],
    risk_struct={
        "macro_risks": ["Auto production downturn reduces near-term shipments", "Industrial slowdown reduces embedded demand"],
        "industry_risks": ["Inventory corrections at Tier1s/OEMs", "Platform concentration risk in major OEM programs"],
        "idiosyncratic_risks": ["Program timing slippage", "Competitive displacement at platform transitions", "Supply assurance constraints"],
    },
    quant_profile={
        "cycle_exposure": {
            "auto_cycle": 0.70,
            "industrial_cycle": 0.55,
            "inventory_correction_risk": 0.70,
            "electrification_tailwind": 0.45,
        },
        "supplier_dependency_risk": {
            "manufacturing_supply_assurance": 0.55,
            "automotive_quality_dependency": 0.60,
        },
        "customer_concentration_risk": {
            "tier1_oem_concentration": 0.65,
            "program_concentration": 0.65,
        },
        "capital_intensity": {
            "rnd_intensity": 0.55,
            "platform_nre_intensity": 0.55,
        },
        "moat_profile": {
            "auto_qualification_stickiness": 0.75,
            "portfolio_breadth": 0.65,
            "embedded_ecosystem": 0.60,
        },
    },
    narrative={
        "one_liner": "Auto embedded backbone: strong structural content growth with real cycle/inventory volatility; watch OEM/Tier1 inventories and platform shifts.",
        "bull_case": "Auto content ramps; inventories normalize; industrial stabilizes; design wins compound into multi-year shipments.",
        "bear_case": "Auto production/inventory correction extends; platform concentration hurts; industrial downturn persists; pricing pressure rises.",
        "watch_items": ["Auto OEM/Tier1 inventory", "SOP ramps", "Industrial order trends", "Platform share shifts"],
    },
    source_note="Deterministic institutional template (no live fundamentals)."
)

# ---- MCHP (Institutional++ Deep) ----
CHAIN["MCHP"] = _schema(
    ticker="MCHP",
    business_model=[
        "Microcontroller and embedded solutions supplier with exposure to industrial, auto, and long-life embedded systems.",
        "Economic engine: broad MCU catalog designed into systems for long periods; growth driven by embedded content and customer lifecycle support.",
        "Volatility primarily from industrial demand and channel inventory cycles rather than rapid node transitions."
    ],
    revenue_mix={
        "industrial": "dominant",
        "automotive": "meaningful",
        "consumer": "smaller",
        "notes": "Embedded lifecycles are long, but customers can still swing orders sharply during inventory corrections."
    },
    pricing_power=(
        "Moderate: stronger in long-life embedded programs with switching costs; "
        "weaker during broad destocking when customers prioritize inventory reduction."
    ),
    suppliers=[
        {"name": "Manufacturing ecosystem (mature nodes)", "role": "Supply assurance and cost stability for MCUs"},
        {"name": "Packaging/test ecosystem", "role": "High mix support and reliability"},
        {"name": "Channel/distribution", "role": "Inventory cycles and demand visibility"},
    ],
    customers=[
        {"group": "Industrial OEMs", "examples": ["Automation", "Power systems", "Embedded controllers"]},
        {"group": "Automotive Tier1s/OEMs", "examples": ["Body electronics", "Control systems (industry context)"]},
        {"group": "Broad embedded customers", "examples": ["Appliance/control systems (industry context)"]},
    ],
    products_to_customers_map={
        "MCUs + embedded controllers": ["Industrial OEMs", "Automotive Tier1s/OEMs", "Broad embedded customers"],
        "Analog/power adjacencies": ["Industrial OEMs", "Automotive Tier1s/OEMs"],
        "Software tools/firmware ecosystem": ["Industrial OEMs", "Broad embedded customers"],
    },
    value_chain=[
        "Design-in → firmware integration → qualification → multi-year shipments; lifecycle support creates stickiness.",
        "Demand visibility is often mediated by distribution; corrections can be sharp when customers destock."
    ],
    competitive_landscape=["TXN (embedded adjacency)", "NXPI", "STM", "Renesas-like peers (industry context)"],
    risk_struct={
        "macro_risks": ["Industrial slowdown reduces orders"],
        "industry_risks": ["Channel inventory corrections and bullwhip", "Competitive pricing in commoditized MCU segments"],
        "idiosyncratic_risks": ["Concentration in some industrial programs", "Execution risk in product roadmap and tooling ecosystem"],
    },
    quant_profile={
        "cycle_exposure": {
            "industrial_cycle": 0.70,
            "auto_cycle": 0.45,
            "inventory_correction_risk": 0.75,
        },
        "supplier_dependency_risk": {
            "mature_node_supply_dependency": 0.40,
            "channel_dependency": 0.65,
        },
        "customer_concentration_risk": {
            "broad_customer_diversification": 0.45,
            "channel_concentration": 0.55,
        },
        "capital_intensity": {
            "rnd_intensity": 0.45,
            "capex_intensity": 0.40,
        },
        "moat_profile": {
            "embedded_lifecycle_stickiness": 0.70,
            "catalog_breadth": 0.65,
            "tooling_ecosystem": 0.55,
        },
    },
    narrative={
        "one_liner": "Embedded MCU franchise: sticky lifecycles but highly sensitive to industrial destocking and channel-driven visibility swings.",
        "bull_case": "Industrial stabilizes; inventory clears; long-life embedded wins compound; pricing holds in qualified programs.",
        "bear_case": "Destocking persists; channel correction drags; competitive pricing pressures commoditized segments; recovery delayed.",
        "watch_items": ["Distributor inventory", "Industrial order tone", "Lead times", "Backlog normalization"],
    },
    source_note="Deterministic institutional template (no live fundamentals)."
)

# ---- ON (Institutional++ Deep) ----
CHAIN["ON"] = _schema(
    ticker="ON",
    business_model=[
        "Power and sensing semiconductor supplier leveraged to electrification: SiC power devices/materials exposure plus broad power discrete portfolio.",
        "Economic engine: EV and industrial power adoption; success depends on capacity/yield execution and customer program wins.",
        "Moat: power portfolio breadth and vertical integration in SiC; risks include program timing and pricing as supply scales."
    ],
    revenue_mix={
        "auto_ev_power": "large/growing",
        "industrial_power": "meaningful",
        "sensing": "meaningful",
        "notes": "EV adoption drives upside but adds cyclicality; industrial can buffer but also cycles."
    },
    pricing_power=(
        "Strong when supply is constrained and qualification is sticky; moderates as supply expands and customers push cost-down."
    ),
    suppliers=[
        {"name": "SiC materials ecosystem", "role": "Substrate supply and yields influence cost and capacity"},
        {"name": "Manufacturing/capex ecosystem", "role": "Scaling power devices and packaging/testing"},
        {"name": "Auto qualification ecosystem", "role": "Long qualification creates stickiness but slows ramps"},
    ],
    customers=[
        {"group": "EV/auto power supply chain", "examples": ["Auto OEM programs", "Tier1 inverter suppliers"]},
        {"group": "Industrial power OEMs", "examples": ["Renewables/inverters", "Industrial drives"]},
        {"group": "Sensing customers", "examples": ["Industrial sensing", "Auto sensing programs (industry context)"]},
    ],
    products_to_customers_map={
        "SiC power devices": ["EV/auto power supply chain", "Industrial power OEMs"],
        "Power discretes/analog": ["Industrial power OEMs", "EV/auto power supply chain"],
        "Image/sensing products": ["Sensing customers", "EV/auto power supply chain"],
    },
    value_chain=[
        "Electrification increases power silicon content → SiC penetration rises → materials/yield become bottlenecks.",
        "Ramps are gated by qualification and capacity; oversupply risks emerge if multiple players scale simultaneously."
    ],
    competitive_landscape=["WOLF (materials)", "STM (SiC)", "Infineon-like peers (industry context)"],
    risk_struct={
        "macro_risks": ["EV demand slowdown delays SiC adoption curve"],
        "industry_risks": ["SiC supply expansions compress pricing over time", "Program timing and qualification delays"],
        "idiosyncratic_risks": ["Yield/capacity execution", "Customer concentration in large EV programs", "High fixed-cost leverage in ramp phases"],
    },
    quant_profile={
        "cycle_exposure": {
            "ev_cycle": 0.70,
            "industrial_power_cycle": 0.55,
            "adoption_timing_risk": 0.65,
        },
        "supplier_dependency_risk": {
            "sic_materials_dependency": 0.70,
            "manufacturing_scale_dependency": 0.65,
        },
        "customer_concentration_risk": {
            "program_concentration": 0.65,
            "qualification_gate_risk": 0.60,
        },
        "capital_intensity": {
            "capex_intensity": 0.70,
            "fixed_cost_operating_leverage": 0.70,
            "rnd_intensity": 0.50,
        },
        "moat_profile": {
            "power_portfolio_breadth": 0.65,
            "vertical_integration_optionality": 0.60,
            "qualification_stickiness": 0.55,
        },
    },
    narrative={
        "one_liner": "Power electrification lever: wins when EV/industrial adoption accelerates; key risks are yield/scale execution and program timing.",
        "bull_case": "EV and industrial demand accelerate; capacity/yields improve; contracts stabilize mix; pricing stays rational.",
        "bear_case": "EV slowdown and destocking; ramps slip; pricing compresses as supply expands; leverage amplifies downside.",
        "watch_items": ["EV demand", "Capacity/yield progress", "Program wins and timing", "SiC pricing signals"],
    },
    source_note="Deterministic institutional template (no live fundamentals)."
)

# ---- STM (Institutional++ Deep) ----
CHAIN["STM"] = _schema(
    ticker="STM",
    business_model=[
        "European IDM with broad exposure to industrial and automotive, including microcontrollers, power, and sensing; also participates in wide-bandgap (SiC) transition.",
        "Economic engine: embedded and power content growth in auto/industrial; cyclicality from industrial demand, auto production, and inventory corrections.",
        "Moat: broad portfolio in embedded and power; risks include exposure to cyclical end-markets and execution in advanced power transitions."
    ],
    revenue_mix={
        "automotive": "large",
        "industrial": "large",
        "personal_electronics": "variable",
        "notes": "Auto/industrial dominate; consumer/handset-adjacent adds volatility; wide-bandgap is an execution lever."
    },
    pricing_power=(
        "Moderate-to-strong in qualified auto/industrial programs; moderated by customer cost-down and cyclicality."
    ),
    suppliers=[
        {"name": "Manufacturing ecosystem (IDM + partners)", "role": "Capacity planning and node strategy influence margins"},
        {"name": "Packaging/test ecosystem", "role": "Auto-grade qualification and high-mix production"},
        {"name": "Power materials ecosystem (SiC)", "role": "Substrate supply/yields influence wide-bandgap economics"},
    ],
    customers=[
        {"group": "Automotive Tier1s/OEMs", "examples": ["Tier1 suppliers", "Auto OEM platforms (industry context)"]},
        {"group": "Industrial OEMs", "examples": ["Automation", "Energy systems", "Embedded devices"]},
        {"group": "Consumer OEMs", "examples": ["Electronics OEM supply chains (industry context)"]},
    ],
    products_to_customers_map={
        "MCUs + embedded controllers": ["Automotive Tier1s/OEMs", "Industrial OEMs"],
        "Power discretes + SiC": ["Automotive Tier1s/OEMs", "Industrial OEMs"],
        "Sensors (MEMS, etc.)": ["Automotive Tier1s/OEMs", "Industrial OEMs", "Consumer OEMs"],
    },
    value_chain=[
        "Auto platform cycles → multi-year shipments; industrial demand drives incremental growth; inventory corrections can cause sharp pauses.",
        "SiC transition adds upside if execution and yields improve; also adds capex and pricing risk if supply expands."
    ],
    competitive_landscape=["NXPI (embedded)", "ON (power)", "Infineon-like peers (industry context)", "MCHP (MCU)"],
    risk_struct={
        "macro_risks": ["Industrial recession reduces demand", "Auto production downturn impacts shipments"],
        "industry_risks": ["Inventory corrections across auto/industrial supply chains", "Pricing pressure as supply normalizes"],
        "idiosyncratic_risks": ["Execution in SiC/wide-bandgap ramps", "Mix volatility in consumer-adjacent segments"],
    },
    quant_profile={
        "cycle_exposure": {
            "auto_cycle": 0.65,
            "industrial_cycle": 0.65,
            "inventory_correction_risk": 0.70,
            "wide_bandgap_execution_risk": 0.55,
        },
        "supplier_dependency_risk": {
            "manufacturing_capacity_dependency": 0.55,
            "sic_materials_dependency": 0.60,
            "automotive_quality_dependency": 0.60,
        },
        "customer_concentration_risk": {
            "tier1_oem_concentration": 0.60,
            "program_concentration": 0.60,
        },
        "capital_intensity": {
            "capex_intensity": 0.70,
            "fixed_cost_operating_leverage": 0.70,
            "rnd_intensity": 0.55,
        },
        "moat_profile": {
            "portfolio_breadth": 0.60,
            "auto_qualification_stickiness": 0.65,
            "embedded_ecosystem": 0.55,
        },
    },
    narrative={
        "one_liner": "Auto/industrial IDM: strong embedded and power content tailwinds with real cyclical destocking risk; SiC execution is a key lever.",
        "bull_case": "Auto/industrial demand rebounds; inventories normalize; SiC ramps execute; pricing holds in qualified programs.",
        "bear_case": "Destocking persists; auto/industrial weak; SiC pricing compresses; operating leverage hurts margins and FCF.",
        "watch_items": ["Auto/industrial order tone", "Inventory levels", "SiC ramp/yields", "Consumer mix volatility"],
    },
    source_note="Deterministic institutional template (no live fundamentals)."
)

# ---- QCOM (Institutional++ Deep) ----
CHAIN["QCOM"] = _schema(
    ticker="QCOM",
    business_model=[
        "Mobile and connectivity platform supplier with handset chipset exposure plus long-term diversification into auto and IoT; also benefits from RF front-end attach.",
        "Economic engine: handset unit cycles + content/attach (premium tier) + licensing/royalty-like economics in parts of the model (conceptually).",
        "Moat: modem/RF integration, platform relationships, and IP; risks include handset cyclicality, customer concentration, and competitive platforms."
    ],
    revenue_mix={
        "handset_chipsets": "dominant cyclical",
        "rf_front_end": "meaningful",
        "auto": "growing option",
        "iot": "meaningful option",
        "notes": "Near-term tied to handset units and inventory; auto/IoT provide diversification but ramp over longer cycles."
    },
    pricing_power=(
        "Moderate-to-strong in premium modem/RF platforms; pressured in downcycles and where OEMs pursue dual sourcing or in-house solutions."
    ),
    suppliers=[
        {"name": "Foundry partners", "role": "Advanced node production for premium SoCs"},
        {"name": "RF component ecosystem", "role": "Filters/amplifiers and RF modules supply chain"},
        {"name": "Software/OS ecosystem", "role": "Platform enablement and compatibility for handset/IoT and auto stacks"},
    ],
    customers=[
        {"group": "Android handset OEMs", "examples": ["Samsung (Android OEM context)", "Xiaomi-like peers (industry context)", "Oppo/Vivo-like peers (industry context)"]},
        {"group": "Auto OEMs/Tier1 (long-cycle)", "examples": ["Auto digital cockpit/telematics programs (industry context)"]},
        {"group": "IoT device OEMs", "examples": ["Industrial IoT", "Consumer IoT OEMs (industry context)"]},
    ],
    products_to_customers_map={
        "Mobile SoCs + modems": ["Android handset OEMs"],
        "RF front-end modules": ["Android handset OEMs"],
        "Auto platforms (cockpit/telematics/connectivity)": ["Auto OEMs/Tier1 (long-cycle)"],
        "IoT connectivity/compute": ["IoT device OEMs"],
    },
    value_chain=[
        "Handset launches and upgrade cycles → OEM builds → channel inventory swings → chipset demand.",
        "Premium tier and RF attach improve mix; auto/IoT require long design cycles but can become sticky.",
        "OEM consolidation and bargaining power influence pricing and share."
    ],
    competitive_landscape=["MediaTek-like peers (industry context)", "Apple in-house silicon (industry context)", "RF peers (SWKS/QRVO/AVGO adjacencies)"],
    risk_struct={
        "macro_risks": ["Consumer downturn reduces handset upgrades"],
        "industry_risks": ["Inventory corrections and OEM build volatility", "Competitive pricing and platform share shifts"],
        "idiosyncratic_risks": ["Customer concentration in major OEMs", "In-house silicon substitution risk", "Auto/IoT ramp execution timing"],
    },
    quant_profile={
        "cycle_exposure": {
            "handset_unit_cycle": 0.85,
            "inventory_correction_risk": 0.75,
            "auto_ramp_optionality": 0.45,
            "rf_attach_mix": 0.55,
        },
        "supplier_dependency_risk": {
            "foundry_dependence": 0.65,
            "rf_supply_chain_dependency": 0.55,
            "software_enablement_dependency": 0.55,
        },
        "customer_concentration_risk": {
            "oem_concentration": 0.70,
            "bargaining_power": 0.65,
        },
        "capital_intensity": {
            "rnd_intensity": 0.70,
            "platform_nre_intensity": 0.65,
        },
        "moat_profile": {
            "modem_rf_integration": 0.70,
            "platform_relationships": 0.65,
            "ip_portfolio_strength": 0.60,
        },
    },
    narrative={
        "one_liner": "Connectivity platform lever: near-term tied to handset cycles and inventory, with longer-cycle diversification into auto/IoT.",
        "bull_case": "Handset cycle rebounds; premium share and RF attach improve; auto/IoT ramps add durable growth; pricing stabilizes.",
        "bear_case": "Handset weakness and destocking persist; OEMs diversify/in-house; pricing pressure rises; auto/IoT ramps slower than expected.",
        "watch_items": ["Handset unit trends", "Channel inventory", "Premium tier share", "Auto/IoT design win ramps"],
    },
    source_note="Deterministic institutional template (no live fundamentals)."
)

# ---- MRVL (Institutional++ Deep) ----
CHAIN["MRVL"] = _schema(
    ticker="MRVL",
    business_model=[
        "Connectivity and infrastructure silicon supplier with exposure to datacenter networking, storage connectivity, and custom/cloud programs.",
        "Economic engine: hyperscaler/networking capex cycles + custom program ramps; demand can be lumpy with digestion phases.",
        "Moat: high-speed SerDes and connectivity IP, deep customer integration in infrastructure programs, and long design cycles."
    ],
    revenue_mix={
        "datacenter_networking": "large",
        "storage_connectivity": "meaningful",
        "custom_cloud_programs": "strategic and lumpy",
        "carrier_infra": "variable",
        "notes": "Custom programs create concentration risk but can be sticky; networking cycles drive volatility."
    },
    pricing_power=(
        "Moderate-to-strong in high-speed connectivity and sticky custom programs; moderated by hyperscaler bargaining power."
    ),
    suppliers=[
        {"name": "Foundry partners", "role": "Advanced node manufacturing for high-speed connectivity"},
        {"name": "Packaging ecosystem", "role": "Signal integrity and high-speed IO packaging constraints"},
        {"name": "IP/SerDes ecosystem", "role": "Interface validation and standards compatibility"},
    ],
    customers=[
        {"group": "Hyperscalers / cloud", "examples": ["MSFT", "AMZN", "GOOGL", "META", "ORCL"]},
        {"group": "Networking OEMs", "examples": ["CSCO", "Arista-like peers (industry context)"]},
        {"group": "Storage/enterprise OEMs", "examples": ["DELL", "HPE"]},
    ],
    products_to_customers_map={
        "Switching/interconnect silicon": ["Hyperscalers / cloud", "Networking OEMs"],
        "Storage connectivity/controllers": ["Hyperscalers / cloud", "Storage/enterprise OEMs"],
        "Custom ASIC programs": ["Hyperscalers / cloud"],
        "Carrier/edge infrastructure silicon": ["Networking OEMs"],
    },
    value_chain=[
        "Bandwidth and storage demand → infrastructure upgrades → long design-in cycles → ramps; digestion phases can pause orders after large builds.",
        "Custom programs have high stickiness once deployed but are timing-sensitive and concentrated."
    ],
    competitive_landscape=["AVGO", "Other connectivity peers (industry context)", "In-house hyperscaler silicon (industry context)"],
    risk_struct={
        "macro_risks": ["Capex slowdowns reduce infrastructure orders"],
        "industry_risks": ["Inventory corrections in networking channels", "Hyperscaler program timing volatility"],
        "idiosyncratic_risks": ["Concentration in large custom programs", "Share shifts at platform transitions", "Foundry/packaging constraints"],
    },
    quant_profile={
        "cycle_exposure": {
            "hyperscaler_capex": 0.75,
            "networking_upgrade_cycle": 0.65,
            "digestion_phase_risk": 0.65,
            "custom_program_timing": 0.70,
        },
        "supplier_dependency_risk": {
            "foundry_dependence": 0.65,
            "packaging_signal_integrity_dependency": 0.55,
        },
        "customer_concentration_risk": {
            "custom_program_concentration": 0.80,
            "hyperscaler_bargaining_power": 0.70,
        },
        "capital_intensity": {
            "rnd_intensity": 0.60,
            "nre_intensity_custom": 0.65,
        },
        "moat_profile": {
            "serdes_ip_differentiation": 0.65,
            "customer_integration_depth": 0.65,
            "design_in_stickiness": 0.60,
        },
    },
    narrative={
        "one_liner": "Infra connectivity lever: best when hyperscaler/network spend expands; biggest risk is concentrated custom program timing and digestion phases.",
        "bull_case": "Capex stays elevated; custom programs ramp; networking/storage upgrades accelerate; supply constraints ease smoothly.",
        "bear_case": "Capex digestion extends; program ramps slip; customers diversify suppliers; pricing and mix compress.",
        "watch_items": ["Hyperscaler capex tone", "Program ramps", "Networking inventory", "Foundry/packaging constraints"],
    },
    source_note="Deterministic institutional template (no live fundamentals)."
)

# ---- SWKS (Institutional++ Deep) ----
CHAIN["SWKS"] = _schema(
    ticker="SWKS",
    business_model=[
        "RF front-end component supplier (power amps, modules, connectivity) heavily exposed to smartphone units and premium-tier attach rates.",
        "Economic engine: handset unit cycles + RF content per phone (more bands/complexity) offset by OEM concentration and pricing pressure.",
        "Moat: RF integration and module performance, but customer concentration is a dominant risk factor."
    ],
    revenue_mix={
        "smartphones": "dominant",
        "broad_markets": "smaller diversification",
        "notes": "RF content tailwind exists, but handset unit cycles and OEM concentration dominate earnings volatility."
    },
    pricing_power=(
        "Limited-to-moderate: stronger in integrated modules and premium designs; pressured by large OEM bargaining power and competitive alternatives."
    ),
    suppliers=[
        {"name": "RF materials/components ecosystem", "role": "Filters, substrates, and specialized RF components"},
        {"name": "Foundry/packaging ecosystem", "role": "RF manufacturing and advanced packaging for modules"},
    ],
    customers=[
        {"group": "Handset OEMs", "examples": ["Major smartphone OEMs (industry context)"]},
        {"group": "Broad markets OEMs", "examples": ["IoT devices", "Connectivity modules (industry context)"]},
    ],
    products_to_customers_map={
        "RF front-end modules": ["Handset OEMs"],
        "Power amplifiers/filters integration": ["Handset OEMs"],
        "Connectivity components (selected)": ["Broad markets OEMs"],
    },
    value_chain=[
        "Handset launch cycles → OEM builds → channel inventory swings → RF component demand.",
        "RF complexity increases with more bands, but OEM integration and in-house/alternative sourcing can cap share and pricing."
    ],
    competitive_landscape=["QRVO", "AVGO (RF adjacencies)", "OEM in-house RF efforts (industry context)"],
    risk_struct={
        "macro_risks": ["Consumer downturn reduces handset upgrades"],
        "industry_risks": ["Inventory corrections and OEM build volatility", "Pricing pressure in RF as competition intensifies"],
        "idiosyncratic_risks": ["High customer concentration", "Share loss risk at platform transitions", "Dependence on premium-tier attach"],
    },
    quant_profile={
        "cycle_exposure": {
            "handset_unit_cycle": 0.90,
            "inventory_correction_risk": 0.80,
            "rf_content_tailwind": 0.55,
        },
        "supplier_dependency_risk": {
            "rf_supply_chain_dependency": 0.55,
            "packaging_dependency": 0.50,
        },
        "customer_concentration_risk": {
            "oem_concentration": 0.85,
            "bargaining_power": 0.75,
        },
        "capital_intensity": {
            "rnd_intensity": 0.55,
            "manufacturing_complexity": 0.50,
        },
        "moat_profile": {
            "rf_integration_capability": 0.55,
            "module_performance": 0.50,
            "design_in_stickiness": 0.45,
        },
    },
    narrative={
        "one_liner": "RF handset lever: very sensitive to smartphone cycles and OEM concentration; RF complexity helps but does not eliminate pricing/share risk.",
        "bull_case": "Handset cycle rebounds; premium attach improves; RF content rises; diversification grows outside handsets.",
        "bear_case": "Handset weakness and destocking persist; OEMs diversify suppliers/in-house; pricing pressure compresses margins.",
        "watch_items": ["Handset unit trends", "Channel inventory", "Attach/share signals", "OEM concentration changes"],
    },
    source_note="Deterministic institutional template (no live fundamentals)."
)

# ---- QRVO (Institutional++ Deep) ----
CHAIN["QRVO"] = _schema(
    ticker="QRVO",
    business_model=[
        "RF front-end and connectivity component supplier with exposure to smartphone units plus diversification efforts into broad markets.",
        "Economic engine: handset cycle + RF content per device; diversification depends on winning in less concentrated end markets.",
        "Moat: RF component engineering and integration; major risk remains handset OEM concentration and pricing."
    ],
    revenue_mix={
        "smartphones": "dominant (but diversifying)",
        "broad_markets": "growing option",
        "notes": "Broad markets can reduce volatility over time if scaled; near-term remains handset-driven."
    },
    pricing_power=(
        "Limited-to-moderate: RF is competitive and large OEMs have bargaining power; differentiation helps mainly in specialized modules."
    ),
    suppliers=[
        {"name": "RF materials/components ecosystem", "role": "Specialized substrates and RF components"},
        {"name": "Foundry/packaging ecosystem", "role": "RF manufacturing and module packaging"},
    ],
    customers=[
        {"group": "Handset OEMs", "examples": ["Major smartphone OEMs (industry context)"]},
        {"group": "Broad markets OEMs", "examples": ["Defense/aerospace adjacencies", "Industrial connectivity (industry context)"]},
    ],
    products_to_customers_map={
        "RF front-end modules": ["Handset OEMs"],
        "Connectivity components (selected)": ["Broad markets OEMs"],
        "Specialty RF (defense/infra adjacencies)": ["Broad markets OEMs"],
    },
    value_chain=[
        "Handset demand swings → OEM build changes → RF demand volatility; diversification success depends on scaling non-handset wins.",
        "RF content tailwind exists, but customer concentration and competitive dynamics dominate profitability."
    ],
    competitive_landscape=["SWKS", "AVGO (RF adjacencies)", "OEM in-house RF efforts (industry context)"],
    risk_struct={
        "macro_risks": ["Consumer downturn reduces handset upgrades"],
        "industry_risks": ["Inventory corrections", "Pricing pressure as OEMs dual-source"],
        "idiosyncratic_risks": ["Customer concentration", "Diversification execution risk", "Share loss at platform transitions"],
    },
    quant_profile={
        "cycle_exposure": {
            "handset_unit_cycle": 0.90,
            "inventory_correction_risk": 0.80,
            "diversification_execution": 0.65,
        },
        "supplier_dependency_risk": {
            "rf_supply_chain_dependency": 0.55,
            "packaging_dependency": 0.50,
        },
        "customer_concentration_risk": {
            "oem_concentration": 0.85,
            "bargaining_power": 0.75,
        },
        "capital_intensity": {
            "rnd_intensity": 0.55,
            "manufacturing_complexity": 0.50,
        },
        "moat_profile": {
            "rf_engineering": 0.55,
            "module_integration": 0.50,
            "specialty_segment_positioning": 0.45,
        },
    },
    narrative={
        "one_liner": "RF handset lever with diversification option: core risk is OEM concentration and pricing; upside if broad markets scale meaningfully.",
        "bull_case": "Handset cycle rebounds; diversification gains traction; RF content increases; pricing stabilizes in differentiated modules.",
        "bear_case": "Handset weakness persists; OEM cost-down and dual-source intensify; diversification under-delivers; margins compress.",
        "watch_items": ["Handset units", "Channel inventory", "Broad markets growth", "Customer concentration changes"],
    },
    source_note="Deterministic institutional template (no live fundamentals)."
)
# ---- Baseline templates (Tier1/Tier2) ----
def _baseline(
    ticker: str,
    lane: str,
    suppliers: List[Dict[str, str]],
    customers: List[Dict[str, Any]],
    p2c: Dict[str, List[str]],
    cycle: Dict[str, float],
    supp: Dict[str, float],
    conc: Dict[str, float],
    capx: Dict[str, float],
    moat: Dict[str, float],
    bull: str,
    bear: str,
    watch: List[str],
) -> Dict[str, Any]:
    return _schema(
        ticker=ticker,
        business_model=[f"{ticker}: {lane} (deterministic template)."],
        revenue_mix={"notes": "Baseline template; deepen over time."},
        pricing_power="Varies by cycle and competitive intensity; see quant_profile.",
        suppliers=suppliers,
        customers=customers,
        products_to_customers_map=p2c,
        value_chain=["Baseline value chain stub; expand per ticker."],
        competitive_landscape=[],
        risk_struct={
            "macro_risks": ["Rates/risk-off can compress multiples and slow capex demand."],
            "industry_risks": ["Inventory cycles + end-demand volatility."],
            "idiosyncratic_risks": ["Execution/competition; customer/supplier concentration per quant_profile."],
        },
        quant_profile={
            "cycle_exposure": cycle,
            "supplier_dependency_risk": supp,
            "customer_concentration_risk": conc,
            "capital_intensity": capx,
            "moat_profile": moat,
        },
        narrative={
            "one_liner": f"{ticker}: baseline institutional chain stub (to be deepened).",
            "bull_case": bull,
            "bear_case": bear,
            "watch_items": watch,
        },
        source_note="Baseline deterministic template."
    )


# Fill baseline coverage for remaining tickers (Tier1/Tier2) not deep-built above
BASELINES: Dict[str, Dict[str, Any]] = {
    # Foundry / equipment / memory
    "TSM": _baseline(
        "TSM",
        "Leading foundry manufacturing advanced nodes; depends on customer design cycles.",
        suppliers=[{"name": "ASML", "role": "EUV lithography supply"}, {"name": "Materials/chemicals", "role": "Process inputs"}],
        customers=[{"group": "Fabless designers", "examples": ["NVDA", "AMD", "AVGO", "QCOM", "AAPL"]}],
        p2c={"Advanced node wafers": ["Fabless designers"]},
        cycle={"semiconductor_cycle": 0.65, "ai_node_mix": 0.60},
        supp={"tooling_dependence": 0.55, "geo_supply_risk": 0.70},
        conc={"top_customer_weight": 0.70},
        capx={"fab_capex_intensity": 0.90},
        moat={"process_lead": 0.85, "scale": 0.80},
        bull="High utilization + leading-node demand; strong pricing for advanced processes.",
        bear="Utilization downcycle; geopolitical/operational risk; capex burden.",
        watch=["Utilization", "Leading-node mix", "Geopolitics"]
    ),
    "ASML": _baseline(
        "ASML",
        "Critical lithography tools (EUV/DUV) enabling leading-edge manufacturing.",
        suppliers=[{"name": "Precision components ecosystem", "role": "High-precision optics/mechatronics"}, {"name": "Zeiss", "role": "Optics partnership (key dependency)"}],
        customers=[{"group": "Foundries/IDMs", "examples": ["TSM", "INTC", "Samsung-like peers (industry context)"]}],
        p2c={"EUV systems": ["Foundries/IDMs"], "DUV systems": ["Foundries/IDMs"]},
        cycle={"wafer_fab_equipment_cycle": 0.65, "leading_edge_capex": 0.70},
        supp={"component_concentration": 0.60},
        conc={"customer_concentration": 0.55},
        capx={"manufacturing_complexity": 0.55, "rnd_intensity": 0.70},
        moat={"monopoly_like_position": 0.95, "switching_costs": 0.85},
        bull="Leading-edge node transitions drive tool demand; backlog converts.",
        bear="Capex pauses delay deliveries; export restrictions reduce TAM.",
        watch=["Backlog", "Export restrictions", "Leading-edge capex"]
    ),
    "AMAT": _baseline(
        "AMAT",
        "Semiconductor manufacturing equipment (deposition/etch/metrology adjacencies).",
        suppliers=[{"name": "Component suppliers", "role": "Subassemblies and precision parts"}],
        customers=[{"group": "Foundries/IDMs", "examples": ["TSM", "INTC", "GFS"]}],
        p2c={"Deposition/etch tools": ["Foundries/IDMs"]},
        cycle={"wafer_fab_equipment_cycle": 0.70},
        supp={"component_supply": 0.45},
        conc={"customer_concentration": 0.55},
        capx={"rnd_intensity": 0.60},
        moat={"installed_base_services": 0.70, "process_knowhow": 0.65},
        bull="WFE upcycle + node transitions drive upgrades.",
        bear="WFE downcycle; customer capex cuts.",
        watch=["WFE cycle", "China/export mix"]
    ),
    "LRCX": _baseline(
        "LRCX",
        "Etch/deposition equipment leveraged to node complexity.",
        suppliers=[{"name": "Precision component ecosystem", "role": "Critical subsystems"}],
        customers=[{"group": "Foundries/IDMs", "examples": ["TSM", "INTC", "GFS"]}],
        p2c={"Etch tools": ["Foundries/IDMs"]},
        cycle={"wafer_fab_equipment_cycle": 0.70},
        supp={"component_supply": 0.45},
        conc={"customer_concentration": 0.55},
        capx={"rnd_intensity": 0.60},
        moat={"process_criticality": 0.70},
        bull="Node complexity increases etch intensity.",
        bear="Capex cuts reduce tool shipments.",
        watch=["WFE cycle", "Node transitions"]
    ),
    "KLAC": _baseline(
        "KLAC",
        "Process control / inspection tools; benefits from complexity + yield focus.",
        suppliers=[{"name": "Optics/mechatronics ecosystem", "role": "High precision components"}],
        customers=[{"group": "Foundries/IDMs", "examples": ["TSM", "INTC", "GFS"]}],
        p2c={"Inspection/metrology": ["Foundries/IDMs"]},
        cycle={"wafer_fab_equipment_cycle": 0.60, "yield_focus": 0.70},
        supp={"component_concentration": 0.45},
        conc={"customer_concentration": 0.50},
        capx={"rnd_intensity": 0.55},
        moat={"high_switching_costs": 0.70},
        bull="More layers/complexity increases inspection needs.",
        bear="WFE pause slows tool demand.",
        watch=["WFE cycle", "Service revenue resilience"]
    ),
    "MU": _baseline(
        "MU",
        "Memory (DRAM/NAND) producer; highly cyclical pricing.",
        suppliers=[{"name": "Equipment suppliers", "role": "WFE for memory fabs"}, {"name": "Materials", "role": "Wafers/chemicals"}],
        customers=[{"group": "OEMs/Cloud", "examples": ["Hyperscalers", "PC OEMs", "Mobile OEMs"]}],
        p2c={"DRAM/HBM": ["Hyperscalers", "OEMs"], "NAND": ["OEMs", "Enterprise SSD buyers"]},
        cycle={"memory_pricing_cycle": 0.90, "ai_hbm_mix": 0.70},
        supp={"manufacturing_complexity": 0.60},
        conc={"customer_concentration": 0.55},
        capx={"fab_capex_intensity": 0.85},
        moat={"scale_cost_curve": 0.55},
        bull="Tight supply + AI/HBM mix lifts margins.",
        bear="Oversupply compresses pricing; demand shock.",
        watch=["DRAM pricing", "HBM mix", "Supply discipline"]
    ),

    # IDMs / analog / RF / auto power
    "INTC": _baseline(
        "INTC",
        "CPU/platform + foundry ambitions; mix of client/server and manufacturing execution.",
        suppliers=[{"name": "Equipment suppliers", "role": "WFE for fabs"}],
        customers=[{"group": "PC/Server OEMs", "examples": ["DELL", "HPQ", "Lenovo", "HPE"]}],
        p2c={"Client/server CPUs": ["PC/Server OEMs"]},
        cycle={"pc_cycle_sensitivity": 0.70, "enterprise_it_cycle": 0.60},
        supp={"manufacturing_execution_risk": 0.70},
        conc={"oem_concentration": 0.55},
        capx={"fab_capex_intensity": 0.90},
        moat={"ecosystem_inertia": 0.65},
        bull="Execution improves; share stabilizes; foundry wins.",
        bear="Execution slips; competition erodes share; capex drag.",
        watch=["Node execution", "Foundry customers", "Share trends"]
    ),
    "TXN": _baseline(
        "TXN",
        "Analog + embedded processing with long product life cycles.",
        suppliers=[{"name": "Internal fabs", "role": "Integrated manufacturing (less external dependency)"}],
        customers=[{"group": "Industrial/Auto OEMs", "examples": ["Industrial OEMs", "Auto suppliers"]}],
        p2c={"Analog/embedded chips": ["Industrial/Auto OEMs"]},
        cycle={"industrial_cycle": 0.55, "auto_cycle": 0.50},
        supp={"supply_chain_risk": 0.30},
        conc={"customer_diversification": 0.25},
        capx={"capex_intensity": 0.55},
        moat={"long_lifecycle_design_ins": 0.75, "catalog_breadth": 0.70},
        bull="Industrial/auto steady demand; pricing durability.",
        bear="Industrial downturn; inventory correction.",
        watch=["Industrial PMI", "Auto production", "Channel inventory"]
    ),
    "ADI": _baseline(
        "ADI",
        "High-performance analog + mixed-signal for industrial/auto/comm.",
        suppliers=[{"name": "Wafer fab partners", "role": "Mix of internal/external manufacturing"}],
        customers=[{"group": "Industrial/Auto/Comm", "examples": ["Industrial OEMs", "Auto OEMs", "Comms infra"]}],
        p2c={"Analog/mixed-signal": ["Industrial/Auto/Comm"]},
        cycle={"industrial_cycle": 0.55, "auto_cycle": 0.45},
        supp={"manufacturing_mix_risk": 0.40},
        conc={"customer_diversification": 0.30},
        capx={"rnd_intensity": 0.55},
        moat={"high_performance_catalog": 0.70},
        bull="Industrial/auto recovery; stable margins.",
        bear="Industrial correction; demand softness.",
        watch=["Industrial backlog", "Inventory levels"]
    ),
    "NXPI": _baseline(
        "NXPI",
        "Auto + industrial semis (MCUs, secure connectivity).",
        suppliers=[{"name": "Foundry partners", "role": "External manufacturing reliance"}],
        customers=[{"group": "Auto OEMs/Tier1", "examples": ["Tier1 suppliers", "Auto OEMs"]}],
        p2c={"Auto MCUs/connectivity": ["Auto OEMs/Tier1"]},
        cycle={"auto_cycle": 0.60},
        supp={"foundry_dependence": 0.55},
        conc={"auto_concentration": 0.60},
        capx={"capex_intensity": 0.45},
        moat={"auto_design_in_stickiness": 0.70},
        bull="Auto content growth; stable platform wins.",
        bear="Auto downturn; supply constraints.",
        watch=["Auto builds", "Design win cadence"]
    ),
    "MCHP": _baseline(
        "MCHP",
        "Microcontrollers/analog for industrial/auto; long design cycles.",
        suppliers=[{"name": "Internal/external manufacturing", "role": "Mixed supply chain"}],
        customers=[{"group": "Industrial/Auto OEMs", "examples": ["Industrial OEMs", "Auto suppliers"]}],
        p2c={"MCUs/Analog": ["Industrial/Auto OEMs"]},
        cycle={"industrial_cycle": 0.60},
        supp={"manufacturing_risk": 0.45},
        conc={"customer_diversification": 0.35},
        capx={"capex_intensity": 0.50},
        moat={"long_design_cycles": 0.65},
        bull="Industrial recovery; stable margins.",
        bear="Inventory correction; demand softness.",
        watch=["Backlog burn", "Channel inventory"]
    ),
    "QCOM": _baseline(
        "QCOM",
        "Wireless SoCs/modems + RF front-end; smartphone-heavy with auto/IoT optionality.",
        suppliers=[{"name": "Foundry partners", "role": "Advanced node dependence"}, {"name": "OSAT/packaging", "role": "Assembly/test ecosystem"}],
        customers=[{"group": "Smartphone OEMs", "examples": ["Samsung-like peers (industry context)", "Xiaomi", "OPPO", "Vivo"]}],
        p2c={"Mobile SoCs/modems": ["Smartphone OEMs"], "Auto/IoT chips": ["Auto OEMs", "IoT OEMs"]},
        cycle={"smartphone_cycle": 0.75},
        supp={"foundry_dependence": 0.65},
        conc={"top_oem_weight": 0.60},
        capx={"rnd_intensity": 0.65},
        moat={"wireless_ip": 0.75},
        bull="Smartphone recovery; auto/IoT growth.",
        bear="Smartphone softness; OEM in-sourcing pressure.",
        watch=["Handset units", "OEM share shifts"]
    ),
    "MRVL": _baseline(
        "MRVL",
        "Networking/DPUs/custom silicon exposure to cloud capex.",
        suppliers=[{"name": "Foundry partners", "role": "Advanced manufacturing reliance"}],
        customers=[{"group": "Cloud/Networking OEMs", "examples": ["Hyperscalers", "Networking OEMs"]}],
        p2c={"Networking silicon": ["Cloud/Networking OEMs"], "Custom silicon": ["Hyperscalers"]},
        cycle={"hyperscaler_capex": 0.70},
        supp={"foundry_dependence": 0.60},
        conc={"designwin_concentration": 0.65},
        capx={"rnd_intensity": 0.60},
        moat={"designwin_stickiness": 0.65},
        bull="Cloud capex expansion; custom silicon ramps.",
        bear="Capex digestion; design wins delay.",
        watch=["Cloud capex", "Custom silicon pipeline"]
    ),
    "ON": _baseline(
        "ON",
        "Power semis/sensors for auto/industrial (EV content driver).",
        suppliers=[{"name": "Internal fabs", "role": "Some vertical integration"}, {"name": "Materials", "role": "SiC substrate/supply chain"}],
        customers=[{"group": "Auto OEMs/Tier1", "examples": ["EV makers", "Tier1 suppliers"]}],
        p2c={"Power modules (SiC/Si)": ["Auto OEMs/Tier1"]},
        cycle={"auto_cycle": 0.60, "industrial_cycle": 0.50},
        supp={"sic_supply_chain": 0.65},
        conc={"auto_concentration": 0.60},
        capx={"capex_intensity": 0.65},
        moat={"power_domain_expertise": 0.60},
        bull="EV content grows; supply tightness supports pricing.",
        bear="EV slowdown; SiC oversupply; pricing pressure.",
        watch=["EV demand", "SiC capacity", "Auto builds"]
    ),
    "SWKS": _baseline(
        "SWKS",
        "RF front-end components leveraged to smartphone units and content per device.",
        suppliers=[{"name": "Foundry/wafer partners", "role": "Manufacturing + packaging ecosystem"}],
        customers=[{"group": "Smartphone OEMs", "examples": ["AAPL", "Android OEMs"]}],
        p2c={"RF front-end modules": ["Smartphone OEMs"]},
        cycle={"smartphone_cycle": 0.80},
        supp={"manufacturing_mix": 0.45},
        conc={"top_customer_weight": 0.80},
        capx={"capex_intensity": 0.45},
        moat={"rf_integration": 0.55},
        bull="Handset recovery + content gains.",
        bear="Customer concentration; content loss; smartphone softness.",
        watch=["Handset units", "Customer concentration", "Content share"]
    ),
    "QRVO": _baseline(
        "QRVO",
        "RF components exposure to handset cycle and customer concentration.",
        suppliers=[{"name": "Manufacturing ecosystem", "role": "Process and packaging dependencies"}],
        customers=[{"group": "Smartphone OEMs", "examples": ["AAPL", "Android OEMs"]}],
        p2c={"RF components": ["Smartphone OEMs"]},
        cycle={"smartphone_cycle": 0.80},
        supp={"process_dependency": 0.50},
        conc={"top_customer_weight": 0.75},
        capx={"capex_intensity": 0.45},
        moat={"rf_ip": 0.55},
        bull="Handset recovery; improved mix.",
        bear="Concentration + handset softness; competitive losses.",
        watch=["OEM share", "Handset cycle"]
    ),
    "WDC": _baseline(
        "WDC",
        "Storage (HDD/SSD) exposure to PC + data center storage demand; SanDisk brand sits within product portfolio.",
        suppliers=[{"name": "Component suppliers", "role": "NAND supply chain / controllers / substrates"}],
        customers=[{"group": "Cloud/Enterprise & OEM", "examples": ["Hyperscalers", "Enterprise storage OEMs", "PC OEMs"]}],
        p2c={"HDD/SSD storage": ["Cloud/Enterprise & OEM"]},
        cycle={"storage_cycle": 0.75, "pc_cycle_sensitivity": 0.55},
        supp={"nand_supply_dependency": 0.55},
        conc={"large_customer_weight": 0.60},
        capx={"capex_intensity": 0.65},
        moat={"scale_in_storage": 0.55},
        bull="Cloud storage demand holds; pricing stabilizes.",
        bear="Storage pricing downcycle; inventory correction.",
        watch=["Storage pricing", "Cloud demand", "Channel inventory"]
    ),
    "STM": _baseline(
        "STM",
        "Industrial/auto semis; mix sensitive to industrial cycle.",
        suppliers=[{"name": "Foundry/internal fabs", "role": "Mixed manufacturing footprint"}],
        customers=[{"group": "Industrial/Auto", "examples": ["Industrial OEMs", "Auto OEMs"]}],
        p2c={"MCUs/Power/Analog": ["Industrial/Auto"]},
        cycle={"industrial_cycle": 0.60, "auto_cycle": 0.50},
        supp={"manufacturing_mix": 0.45},
        conc={"customer_diversification": 0.40},
        capx={"capex_intensity": 0.55},
        moat={"broad_portfolio": 0.60},
        bull="Industrial recovery; stable demand.",
        bear="Industrial slump; inventory correction.",
        watch=["Industrial orders", "Auto builds"]
    ),
    "TER": _baseline(
        "TER",
        "Test equipment leveraged to semiconductor production cycles.",
        suppliers=[{"name": "Component suppliers", "role": "Precision parts"}],
        customers=[{"group": "IDMs/Foundries/OSATs", "examples": ["Chip makers", "OSATs"]}],
        p2c={"Test equipment": ["IDMs/Foundries/OSATs"]},
        cycle={"semi_capex_cycle": 0.65},
        supp={"component_supply": 0.40},
        conc={"customer_concentration": 0.45},
        capx={"rnd_intensity": 0.50},
        moat={"installed_base": 0.55},
        bull="Test demand rises with node complexity and volume.",
        bear="Capex cuts reduce test spend.",
        watch=["Capex cycle", "Utilization"]
    ),
    "MPWR": _baseline(
        "MPWR",
        "Power management ICs with exposure to compute/industrial cycles.",
        suppliers=[{"name": "Foundry partners", "role": "External manufacturing reliance"}],
        customers=[{"group": "OEMs", "examples": ["Compute OEMs", "Industrial OEMs"]}],
        p2c={"Power ICs": ["OEMs"]},
        cycle={"compute_cycle": 0.55, "industrial_cycle": 0.45},
        supp={"foundry_dependence": 0.55},
        conc={"customer_diversification": 0.40},
        capx={"rnd_intensity": 0.50},
        moat={"power_design_expertise": 0.60},
        bull="Content gains + steady demand.",
        bear="Demand slowdown; pricing pressure.",
        watch=["Order trends", "Inventory"]
    ),
    "GFS": _baseline(
        "GFS",
        "Specialty foundry; exposure to industrial/auto/defense and node mix.",
        suppliers=[{"name": "Equipment suppliers", "role": "WFE inputs"}],
        customers=[{"group": "Fabless designers", "examples": ["Auto/industrial chip designers"]}],
        p2c={"Specialty wafers": ["Fabless designers"]},
        cycle={"semi_cycle": 0.55},
        supp={"capex_dependency": 0.70},
        conc={"customer_concentration": 0.55},
        capx={"fab_capex_intensity": 0.85},
        moat={"specialty_process": 0.55},
        bull="Utilization improves; specialty demand steady.",
        bear="Utilization weak; capex drag.",
        watch=["Utilization", "Order backlog"]
    ),
    "ARM": _baseline(
        "ARM",
        "CPU IP licensing/royalties; leveraged to device volume and server adoption.",
        suppliers=[{"name": "Ecosystem partners", "role": "Licensees implement ARM IP"}],
        customers=[{"group": "SoC designers", "examples": ["AAPL", "QCOM", "NVDA adjacencies"]}],
        p2c={"CPU IP": ["SoC designers"]},
        cycle={"device_volume_cycle": 0.60, "server_adoption": 0.50},
        supp={"ecosystem_execution": 0.40},
        conc={"top_licensee_weight": 0.60},
        capx={"rnd_intensity": 0.55},
        moat={"ecosystem_lock_in": 0.75},
        bull="ARM penetration grows in servers/AI edge.",
        bear="Device volume softness; licensee concentration.",
        watch=["Server adoption", "Royalty trends"]
    ),
    "UMC": _baseline(
        "UMC",
        "Mature-node foundry; cyclical utilization and pricing.",
        suppliers=[{"name": "Equipment suppliers", "role": "WFE inputs"}],
        customers=[{"group": "Fabless designers", "examples": ["Industrial/consumer chip designers"]}],
        p2c={"Mature-node wafers": ["Fabless designers"]},
        cycle={"semi_cycle": 0.60},
        supp={"capex_dependency": 0.60},
        conc={"customer_concentration": 0.45},
        capx={"fab_capex_intensity": 0.70},
        moat={"scale": 0.55},
        bull="Utilization tight; stable pricing.",
        bear="Utilization drops; pricing pressure.",
        watch=["Utilization", "Capacity additions"]
    ),
    "COHR": _baseline(
        "COHR",
        "Photonics/laser components exposed to industrial and data comm cycles.",
        suppliers=[{"name": "Component ecosystem", "role": "Optics/materials dependencies"}],
        customers=[{"group": "Industrial/Datacom OEMs", "examples": ["Datacom OEMs", "Industrial OEMs"]}],
        p2c={"Photonics components": ["Industrial/Datacom OEMs"]},
        cycle={"datacom_cycle": 0.55, "industrial_cycle": 0.55},
        supp={"component_dependency": 0.45},
        conc={"customer_concentration": 0.50},
        capx={"rnd_intensity": 0.55},
        moat={"precision_ip": 0.55},
        bull="Datacom builds + industrial recovery.",
        bear="Demand softness; pricing pressure.",
        watch=["Datacom orders", "Industrial demand"]
    ),
    "WOLF": _baseline(
        "WOLF",
        "SiC materials/devices exposure to EV/power cycle and capacity buildout execution.",
        suppliers=[{"name": "Materials/supply chain", "role": "Substrate and manufacturing dependencies"}],
        customers=[{"group": "Auto/Industrial", "examples": ["EV supply chain", "Industrial power customers"]}],
        p2c={"SiC devices/materials": ["Auto/Industrial"]},
        cycle={"ev_cycle": 0.70},
        supp={"execution_risk": 0.70},
        conc={"customer_concentration": 0.55},
        capx={"capex_intensity": 0.90},
        moat={"sic_knowhow": 0.55},
        bull="EV demand supports SiC adoption; capacity ramps cleanly.",
        bear="Execution slips; demand slows; high fixed costs.",
        watch=["Capacity ramp", "EV demand", "Margins"]
    ),
    "IPGP": _baseline(
        "IPGP",
        "Industrial lasers exposure to manufacturing capex cycles.",
        suppliers=[{"name": "Component ecosystem", "role": "Optics/material dependencies"}],
        customers=[{"group": "Industrial OEMs", "examples": ["Manufacturing OEMs"]}],
        p2c={"Industrial lasers": ["Industrial OEMs"]},
        cycle={"industrial_cycle": 0.70},
        supp={"component_dependency": 0.40},
        conc={"customer_diversification": 0.35},
        capx={"rnd_intensity": 0.45},
        moat={"technology_lead": 0.55},
        bull="Industrial recovery boosts demand.",
        bear="Industrial slowdown; orders soften.",
        watch=["Industrial PMI", "Order backlog"]
    ),
    "ACLS": _baseline(
        "ACLS",
        "Ion implantation tools leveraged to WFE cycles and process intensity.",
        suppliers=[{"name": "Component suppliers", "role": "Precision subsystems"}],
        customers=[{"group": "Foundries/IDMs", "examples": ["TSM", "INTC", "GFS"]}],
        p2c={"Ion implant tools": ["Foundries/IDMs"]},
        cycle={"wafer_fab_equipment_cycle": 0.70},
        supp={"component_supply": 0.40},
        conc={"customer_concentration": 0.50},
        capx={"rnd_intensity": 0.50},
        moat={"niche_process_position": 0.55},
        bull="WFE upcycle; process intensity increases demand.",
        bear="WFE downcycle; shipments fall.",
        watch=["WFE cycle", "Backlog"]
    ),
}

# Add baselines into CHAIN if not present
for t, obj in BASELINES.items():
    if t not in CHAIN:
        CHAIN[t] = obj


def _generic(ticker: str) -> Dict[str, Any]:
    return _schema(
        ticker=ticker,
        business_model=[f"{ticker}: generic company chain fallback (not yet covered)."],
        revenue_mix={"notes": "Not covered in Phase B template universe yet."},
        pricing_power="Unknown.",
        suppliers=[],
        customers=[],
        products_to_customers_map={},
        value_chain=[],
        competitive_landscape=[],
        risk_struct={"macro_risks": [], "industry_risks": [], "idiosyncratic_risks": []},
        quant_profile={
            "cycle_exposure": {},
            "supplier_dependency_risk": {},
            "customer_concentration_risk": {},
            "capital_intensity": {},
            "moat_profile": {},
        },
        narrative={
            "one_liner": f"{ticker}: not in institutional coverage list yet.",
            "bull_case": "Coverage not built yet.",
            "bear_case": "Coverage not built yet.",
            "watch_items": [],
        },
        source_note="Generic fallback."
    )


# -----------------------------
# Public API (used by app.py)
# -----------------------------
def build_company_chain(
    ticker: str,
    company: Dict[str, Any] | None = None,
    cluster: str | None = None,
    sector_bucket: str | None = None,
) -> Dict[str, Any]:
    """
    Returns the deterministic institutional company chain object.
    - UI-safe: matches report.html expectations (lists for business_model/value_chain/risk_layer)
    - Quant-first: includes quant_profile + derived scores
    - Narrative: included for ecosystem box (cb.narrative.*)
    """
    t = _u(ticker).upper()
    obj = CHAIN.get(t) or _generic(t)

    # Optional lightweight annotation from runtime inputs (does NOT change quant logic).
    if cluster:
        obj = dict(obj)
        obj["cluster"] = _u(cluster)
    if sector_bucket:
        obj = dict(obj)
        obj["sector_bucket"] = _u(sector_bucket)

    # Add a tiny descriptive header for UI if desired
    if company and isinstance(company, dict):
        # no heavy parsing; just attach spot if present
        spot = company.get("spot") or company.get("price") or None
        if spot is not None:
            try:
                obj = dict(obj)
                obj["spot_note"] = float(spot)
            except Exception:
                pass

    return obj
