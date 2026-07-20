from __future__ import annotations

from copy import deepcopy

COMPANIES: dict[str, dict] = {
    "NVDA": {
        "name": "NVIDIA",
        "role": "Accelerated-computing platform provider",
        "offerings": ["GPU compute", "CUDA software ecosystem", "AI networking", "Enterprise AI software"],
        "workloads": ["foundation-model training", "high-throughput inference", "simulation", "recommendation systems"],
        "buyers": ["CIO / CTO", "VP Infrastructure", "Head of AI Platform", "Data Center Engineering", "FinOps"],
        "commercial_signals": ["GPU-cluster expansion", "inference cost pressure", "network bottlenecks", "AI factory standardization"],
        "competitors": ["AMD", "custom accelerators", "cloud-native silicon"],
        "constraints": ["capacity planning", "power density", "software portability", "cluster utilization"],
    },
    "AMD": {
        "name": "AMD",
        "role": "CPU and accelerator platform provider",
        "offerings": ["EPYC CPUs", "Instinct accelerators", "ROCm software", "adaptive compute"],
        "workloads": ["AI training", "inference", "HPC", "virtualized enterprise compute"],
        "buyers": ["CTO", "Infrastructure Architecture", "AI Platform", "Procurement", "FinOps"],
        "commercial_signals": ["multi-vendor accelerator strategy", "x86 refresh", "cost-per-token optimization", "open software requirements"],
        "competitors": ["NVIDIA", "Intel", "custom accelerators"],
        "constraints": ["software maturity", "migration effort", "benchmark comparability", "supply availability"],
    },
    "AVGO": {
        "name": "Broadcom",
        "role": "Networking, connectivity, and custom-silicon provider",
        "offerings": ["Ethernet switching", "optical connectivity", "custom accelerators", "infrastructure software"],
        "workloads": ["scale-out AI fabrics", "data-center networking", "custom compute", "private cloud"],
        "buyers": ["Network Engineering", "Data Center Architecture", "CTO", "Silicon Engineering", "Procurement"],
        "commercial_signals": ["east-west traffic growth", "AI fabric redesign", "custom silicon evaluation", "private-cloud consolidation"],
        "competitors": ["NVIDIA networking", "Marvell", "in-house silicon"],
        "constraints": ["interoperability", "latency", "optics cost", "deployment complexity"],
    },
    "TSM": {
        "name": "TSMC",
        "role": "Advanced semiconductor foundry",
        "offerings": ["advanced process nodes", "advanced packaging", "high-volume manufacturing", "design ecosystem"],
        "workloads": ["AI accelerator production", "chiplet integration", "advanced packaging", "yield optimization"],
        "buyers": ["Semiconductor Business Unit", "Supply Chain", "Product Engineering", "Operations", "Executive Leadership"],
        "commercial_signals": ["advanced-node demand", "packaging constraints", "capacity reservations", "yield improvement programs"],
        "competitors": ["Samsung Foundry", "Intel Foundry"],
        "constraints": ["capacity", "geographic concentration", "long lead times", "capital intensity"],
    },
    "ASML": {
        "name": "ASML",
        "role": "Semiconductor lithography systems provider",
        "offerings": ["EUV lithography", "DUV lithography", "metrology software", "service and installed-base support"],
        "workloads": ["advanced-node manufacturing", "process control", "predictive maintenance", "factory optimization"],
        "buyers": ["Fab Operations", "Process Engineering", "Manufacturing IT", "Service Operations", "Executive Leadership"],
        "commercial_signals": ["advanced-node capacity additions", "tool productivity programs", "service automation", "factory data modernization"],
        "competitors": ["alternative lithography suppliers", "process substitution"],
        "constraints": ["tool complexity", "service uptime", "export controls", "specialized talent"],
    },
    "MU": {
        "name": "Micron Technology",
        "role": "Memory and storage provider",
        "offerings": ["high-bandwidth memory", "DRAM", "NAND", "data-center SSDs"],
        "workloads": ["AI training memory", "inference memory", "data-center storage", "edge compute"],
        "buyers": ["AI Systems Architecture", "Data Center Engineering", "Supply Chain", "Product Management", "Procurement"],
        "commercial_signals": ["HBM qualification", "memory bandwidth bottlenecks", "data-center refresh", "supply assurance"],
        "competitors": ["SK hynix", "Samsung Memory"],
        "constraints": ["memory cycles", "qualification timelines", "yield ramp", "supply concentration"],
    },
    "ANET": {
        "name": "Arista Networks",
        "role": "Cloud and AI networking provider",
        "offerings": ["high-speed Ethernet switching", "network operating systems", "observability", "AI cluster networking"],
        "workloads": ["AI training fabrics", "cloud networking", "east-west traffic", "network telemetry"],
        "buyers": ["VP Network", "Cloud Infrastructure", "AI Platform", "SRE", "Procurement"],
        "commercial_signals": ["400G/800G migration", "GPU cluster buildout", "fabric congestion", "network automation"],
        "competitors": ["Cisco", "NVIDIA networking", "white-box networking"],
        "constraints": ["vendor concentration", "operational change", "interoperability", "deployment timing"],
    },
    "SMCI": {
        "name": "Supermicro",
        "role": "Server and rack-scale systems provider",
        "offerings": ["GPU servers", "rack-scale systems", "liquid cooling", "storage platforms"],
        "workloads": ["AI training clusters", "inference farms", "private AI", "HPC"],
        "buyers": ["Data Center Engineering", "AI Infrastructure", "CIO / CTO", "Facilities", "Procurement"],
        "commercial_signals": ["rapid GPU deployment", "rack integration", "liquid-cooling adoption", "time-to-capacity pressure"],
        "competitors": ["Dell", "HPE", "ODM systems"],
        "constraints": ["supply coordination", "quality assurance", "power and cooling", "support coverage"],
    },
    "DELL": {
        "name": "Dell Technologies",
        "role": "Enterprise infrastructure and integrated-systems provider",
        "offerings": ["AI servers", "storage", "networking", "professional services"],
        "workloads": ["private enterprise AI", "RAG platforms", "virtualization", "data modernization"],
        "buyers": ["CIO", "Infrastructure", "Data and AI", "Security", "Procurement"],
        "commercial_signals": ["private AI programs", "data sovereignty", "infrastructure refresh", "platform consolidation"],
        "competitors": ["HPE", "Supermicro", "public cloud"],
        "constraints": ["integration complexity", "budget ownership", "legacy estates", "skills gaps"],
    },
    "VRT": {
        "name": "Vertiv",
        "role": "Data-center power and thermal infrastructure provider",
        "offerings": ["power systems", "liquid cooling", "thermal management", "data-center services"],
        "workloads": ["high-density AI racks", "data-center expansion", "cooling retrofits", "power resilience"],
        "buyers": ["Data Center Operations", "Facilities", "Infrastructure Engineering", "Sustainability", "CFO"],
        "commercial_signals": ["rack density growth", "liquid-cooling pilots", "power constraints", "facility expansion"],
        "competitors": ["Schneider Electric", "Eaton", "in-house facilities design"],
        "constraints": ["site readiness", "deployment lead time", "energy efficiency", "capital planning"],
    },
    "CRWV": {
        "name": "CoreWeave",
        "role": "GPU-focused cloud infrastructure provider",
        "offerings": ["GPU cloud", "managed Kubernetes", "AI storage", "high-performance networking"],
        "workloads": ["model training", "inference", "rendering", "AI-native application scaling"],
        "buyers": ["CTO", "Head of AI", "Platform Engineering", "ML Engineering", "FinOps"],
        "commercial_signals": ["GPU capacity gaps", "time-to-cluster pressure", "cloud diversification", "inference scaling"],
        "competitors": ["hyperscalers", "specialized GPU clouds", "on-prem clusters"],
        "constraints": ["capacity commitments", "workload portability", "unit economics", "enterprise governance"],
    },
}

SOLUTION_MOTIONS: dict[str, dict] = {
    "gpu_compute": {
        "label": "GPU Compute & Accelerated Platforms",
        "technical_focus": ["utilization", "throughput", "latency", "scheduler efficiency", "model portability"],
        "business_metrics": ["cost per training run", "cost per million tokens", "time to deploy capacity", "revenue per GPU hour"],
    },
    "cloud_ai": {
        "label": "Cloud AI Platform",
        "technical_focus": ["elasticity", "governance", "managed services", "data locality", "service reliability"],
        "business_metrics": ["time to production", "platform operating cost", "developer productivity", "workload conversion rate"],
    },
    "networking": {
        "label": "AI Networking & Interconnect",
        "technical_focus": ["fabric utilization", "east-west bandwidth", "collective performance", "packet loss", "observability"],
        "business_metrics": ["GPU idle time", "job completion time", "cluster scaling efficiency", "network cost per accelerator"],
    },
    "data_center": {
        "label": "Data Center Power, Cooling & Systems",
        "technical_focus": ["rack density", "power availability", "cooling efficiency", "deployment readiness", "resilience"],
        "business_metrics": ["time to capacity", "PUE", "facility cost per MW", "downtime exposure"],
    },
    "mlops": {
        "label": "MLOps & Inference Operations",
        "technical_focus": ["deployment automation", "model serving", "observability", "drift response", "cost allocation"],
        "business_metrics": ["release lead time", "inference unit cost", "incident recovery time", "model adoption"],
    },
}


def list_companies() -> list[dict]:
    return [
        {"ticker": ticker, "name": data["name"], "role": data["role"]}
        for ticker, data in sorted(COMPANIES.items(), key=lambda item: item[1]["name"])
    ]


def get_company(ticker: str) -> dict | None:
    record = COMPANIES.get(ticker.upper().strip())
    return deepcopy(record) if record else None


def get_solution_motion(key: str) -> dict | None:
    record = SOLUTION_MOTIONS.get(key)
    return deepcopy(record) if record else None
