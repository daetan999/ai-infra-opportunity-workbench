# data/adaptive_confidence.py
# ADAPTIVE CONFIDENCE FRAMEWORK
# Adjusts DCF weighting based on view and market gap

from typing import Optional, Dict, List

def calculate_adaptive_dcf_weight(
    dcf_intrinsic: Optional[float],
    spot: float,
    view: str,
) -> Dict[str, any]:
    """
    Calculate adaptive DCF weight and score based on view and valuation gap.
    
    Framework:
        BULLISH view + Large gap (DCF < 0.7 × Spot):
            → Low weight (0.10-0.15) - market pricing premium
            → Neutral score (0.5) - don't penalize
            → Interpretation: "Market pricing growth premium"
        
        BULLISH view + Undervalued (DCF > Spot):
            → Normal weight (0.30)
            → Strong score (1.0) - supports thesis
            → Interpretation: "Fundamentals support bullish view"
        
        BEARISH view + Overvalued (DCF < Spot):
            → High weight (0.40)
            → Strong score (1.0) - reinforces thesis
            → Interpretation: "Fundamentals support bearish view"
        
        NEUTRAL or small gaps:
            → Normal weight (0.30)
            → Standard scoring
    
    Args:
        dcf_intrinsic: DCF intrinsic value (can be None if DCF failed)
        spot: Current stock price
        view: "bullish", "neutral", or "bearish"
    
    Returns:
        {
            "weight": float (0.10-0.40),
            "score": float (0.0-1.0),
            "interpretation": str,
            "gap_pct": float,
            "is_large_gap": bool,
        }
    """
    view = view.lower() if view else "neutral"
    
    # Default if DCF failed
    if dcf_intrinsic is None or dcf_intrinsic <= 0 or spot <= 0:
        return {
            "weight": 0.0,
            "score": 0.5,
            "interpretation": "DCF unavailable - defaulted to neutral",
            "gap_pct": None,
            "is_large_gap": False,
        }
    
    # Calculate gap
    gap_pct = (dcf_intrinsic - spot) / spot
    is_large_gap = abs(gap_pct) > 0.50  # >50% gap
    is_medium_gap = abs(gap_pct) > 0.30  # >30% gap
    
    # ========================================
    # BULLISH VIEW
    # ========================================
    if view == "bullish":
        if dcf_intrinsic > spot * 1.10:
            # DCF > 110% of spot → Undervalued, supports bullish
            weight = 0.30
            score = 1.0
            interpretation = "DCF supports bullish view - fundamentally undervalued"
        
        elif dcf_intrinsic > spot * 0.90:
            # Close to fair value (90-110%)
            weight = 0.30
            score = 0.7
            interpretation = "DCF near fair value - bullish view on growth prospects"
        
        elif is_large_gap:
            # DCF < 70% of spot → Market pricing large premium
            weight = 0.10
            score = 0.5
            interpretation = "Market pricing growth premium above conservative DCF (downside reference)"
        
        elif is_medium_gap:
            # DCF 70-90% of spot → Moderate premium
            weight = 0.20
            score = 0.5
            interpretation = "Market pricing moderate premium above DCF fundamentals"
        
        else:
            # Small gap
            weight = 0.30
            score = 0.6
            interpretation = "DCF slight discount to market - bullish on execution"
    
    # ========================================
    # BEARISH VIEW
    # ========================================
    elif view == "bearish":
        if dcf_intrinsic < spot * 0.70:
            # DCF < 70% of spot → Significantly overvalued, supports bearish
            weight = 0.40  # Higher weight when supporting thesis
            score = 1.0
            interpretation = "DCF supports bearish view - significantly overvalued"
        
        elif dcf_intrinsic < spot * 0.90:
            # DCF 70-90% of spot → Moderately overvalued
            weight = 0.35
            score = 0.8
            interpretation = "DCF indicates overvaluation - supports bearish view"
        
        elif dcf_intrinsic > spot * 1.10:
            # DCF > 110% of spot → Undervalued, conflicts with bearish
            weight = 0.20  # Lower weight when conflicting
            score = 0.2
            interpretation = "DCF suggests undervaluation - conflicts with bearish view"
        
        else:
            # Close to fair value
            weight = 0.30
            score = 0.5
            interpretation = "DCF near fair value - bearish on near-term headwinds"
    
    # ========================================
    # NEUTRAL VIEW (DEFAULT)
    # ========================================
    else:
        if dcf_intrinsic > spot * 1.20:
            # Significantly undervalued
            weight = 0.30
            score = 0.9
            interpretation = "DCF indicates significant undervaluation"
        
        elif dcf_intrinsic > spot * 1.05:
            # Moderately undervalued
            weight = 0.30
            score = 0.7
            interpretation = "DCF indicates moderate undervaluation"
        
        elif dcf_intrinsic < spot * 0.80:
            # Significantly overvalued
            weight = 0.30
            score = 0.3
            interpretation = "DCF indicates significant overvaluation"
        
        elif dcf_intrinsic < spot * 0.95:
            # Moderately overvalued
            weight = 0.30
            score = 0.4
            interpretation = "DCF indicates moderate overvaluation"
        
        else:
            # Fair value (95-105%)
            weight = 0.30
            score = 0.5
            interpretation = "DCF near fair value"
    
    return {
        "weight": weight,
        "score": score,
        "interpretation": interpretation,
        "gap_pct": gap_pct,
        "is_large_gap": is_large_gap,
    }


def _generate_company_moat_context(
    ticker: str,
    growth_tier: str,
    dcf_result: Optional[Dict],
    company_snapshot: Optional[Dict] = None,
) -> List[str]:
    """
    Generate company-specific moat explanations for gap context.
    
    Uses ticker, growth tier, and company data to create relevant
    bullet points explaining why market might pay a premium.
    
    Args:
        ticker: Stock ticker (e.g., "NVDA", "INTC")
        growth_tier: "high", "moderate", or "mature"
        dcf_result: DCF result dict (contains view info)
        company_snapshot: Company data (optional)
    
    Returns:
        List of bullet point strings
    """
    ticker = ticker.upper()
    moats = []
    
    # Company-specific moat mapping (semiconductor focus)
    COMPANY_MOATS = {
        "NVDA": [
            "AI accelerator market leadership (80%+ data center GPU share)",
            "CUDA software ecosystem moat (high switching costs)",
            "Strategic value in constrained AI chip supply",
            "Secular AI tailwind (10+ year growth runway)",
        ],
        "AMD": [
            "Server CPU market share gains (EPYC momentum)",
            "Data center exposure (fastest-growing segment)",
            "Process technology leadership (advanced nodes)",
            "x86 duopoly position",
        ],
        "INTC": [
            "x86 architecture installed base (legacy moat)",
            "Foundry transition potential (IDM 2.0 strategy)",
            "Government support (CHIPS Act, strategic asset)",
            "Turnaround optionality (new leadership, process recovery)",
        ],
        "MU": [
            "Memory market oligopoly (consolidated industry)",
            "HBM exposure (AI memory demand)",
            "Cyclical recovery potential (memory pricing)",
            "Technology leadership in DRAM/NAND",
        ],
        "QCOM": [
            "Mobile modem leadership (essential patents)",
            "Automotive design wins (long-term contracts)",
            "Licensing revenue stability (recurring income)",
            "Snapdragon brand strength",
        ],
        "AVGO": [
            "Diversified semiconductor portfolio",
            "Software revenue (CA acquisition)",
            "Networking infrastructure exposure",
            "Strong FCF generation",
        ],
        "TSM": [
            "Leading-edge foundry monopoly (sub-5nm)",
            "Customer stickiness (design-in relationships)",
            "Geographic strategic value (Taiwan Semiconductor)",
            "Technology roadmap leadership",
        ],
        "ASML": [
            "EUV lithography monopoly (no competitors)",
            "Critical enabler for advanced nodes",
            "Long-term supply agreements (visibility)",
            "Impossible-to-replicate technology",
        ],
        "MCHP": [
            "Embedded controller niche (sticky designs)",
            "Long product lifecycles (10+ years)",
            "Direct sales model (customer relationships)",
            "Stable automotive/industrial exposure",
        ],
        "TXN": [
            "Analog semiconductor leadership",
            "Diversified end-market exposure",
            "Manufacturing scale advantages",
            "Long product lifecycles",
        ],
        "ON": [
            "Automotive semiconductor exposure",
            "Power management leadership",
            "Industrial diversification",
            "SiC technology position",
        ],
    }
    
    # Try company-specific moats first
    if ticker in COMPANY_MOATS:
        moats = COMPANY_MOATS[ticker]
    else:
        # Generic moats based on growth tier
        if growth_tier == "high":
            moats = [
                "Market leadership in high-growth semiconductor segment",
                "Technology differentiation and competitive moat",
                "Secular tailwind in target end-markets",
                "Execution track record and margin expansion",
            ]
        elif growth_tier == "moderate":
            moats = [
                "Established market position",
                "Diversified revenue streams",
                "Operating leverage opportunities",
                "Strategic positioning in key markets",
            ]
        else:  # mature
            moats = [
                "Stable cash flow generation",
                "Dividend yield and capital return",
                "Market share defensibility",
                "Operational efficiency focus",
            ]
    
    # Add view context if available
    if dcf_result:
        view_used = dcf_result.get("view_used", "").lower()
        if view_used == "bullish":
            # Emphasize growth in bullish view
            moats.append("Bullish view reflects above-consensus growth expectations")
        elif view_used == "bearish":
            # Add cautionary note in bearish view
            moats.append("Bearish view questions sustainability of premium")
    
    return moats


def format_dcf_display_context(
    dcf_result: Optional[Dict],
    spot: float,
    view: str,
    adaptive_dcf: Dict,
    company_snapshot: Optional[Dict] = None,
) -> Dict[str, str]:
    """
    Format DCF information for display with proper context.
    
    Returns display-ready strings explaining the DCF vs market gap.
    """
    if not dcf_result or not dcf_result.get('intrinsic'):
        return {
            "dcf_label": "DCF Valuation",
            "dcf_value": "Not available",
            "dcf_context": "DCF calculation unavailable",
            "gap_explanation": "",
            "gap_moats": [],
            "market_label": "Current Price",
            "market_value": f"${spot:.2f}",
        }
    
    intrinsic = dcf_result.get('intrinsic')
    gap_pct = adaptive_dcf.get('gap_pct', 0) * 100
    
    # Get company-specific moats
    ticker = dcf_result.get('debug', {}).get('ticker', 'UNKNOWN')
    growth_tier = dcf_result.get('growth_tier', 'moderate')
    moats = _generate_company_moat_context(ticker, growth_tier, dcf_result, company_snapshot)
    
    # Format values
    dcf_value = f"${intrinsic:.2f}"
    market_value = f"${spot:.2f}"
    
    # Context based on gap
    if adaptive_dcf.get('is_large_gap'):
        if intrinsic < spot:
            # Market pricing premium
            dcf_label = "Conservative Fundamental Anchor"
            dcf_context = f"Based on {dcf_result.get('assumption_note', 'conservative assumptions')}"
            
            # Main explanation
            gap_explanation = f"Market pricing {abs(gap_pct):.0f}% premium above fundamental anchor. This reflects:"
        else:
            # Deeply undervalued
            dcf_label = "DCF Intrinsic Value"
            dcf_context = "Significant upside to fundamental value"
            gap_explanation = f"Trading {abs(gap_pct):.0f}% below intrinsic value - potential value opportunity if:"
    else:
        # Normal gap
        dcf_label = "DCF Intrinsic Value"
        if abs(gap_pct) < 10:
            dcf_context = "Near fair value"
            gap_explanation = f"Trading close to fundamental value ({gap_pct:+.1f}%)."
            moats = []  # Don't show moats for fair value
        elif intrinsic > spot:
            dcf_context = "Moderate undervaluation"
            gap_explanation = f"Trading {abs(gap_pct):.0f}% below intrinsic value - potential upside if:"
        else:
            dcf_context = "Moderate overvaluation"
            gap_explanation = f"Trading {abs(gap_pct):.0f}% above intrinsic value - premium reflects:"
    
    return {
        "dcf_label": dcf_label,
        "dcf_value": dcf_value,
        "dcf_context": dcf_context,
        "gap_explanation": gap_explanation,
        "gap_moats": moats,  # List of bullet points
        "market_label": "Current Market Price",
        "market_value": market_value,
        "view_context": f"{view.capitalize()} view" if view != "neutral" else "Neutral analysis",
    }




# ========================================
# EXAMPLE USAGE
# ========================================

if __name__ == "__main__":
    print("\n" + "="*70)
    print("ADAPTIVE DCF WEIGHTING DEMONSTRATION")
    print("="*70 + "\n")
    
    # Test cases
    scenarios = [
        ("NVDA Bullish", 77, 180, "bullish"),
        ("NVDA Bearish", 77, 180, "bearish"),
        ("NVDA Neutral", 77, 180, "neutral"),
        ("MU Bullish (fair)", 95, 100, "bullish"),
        ("INTC Bearish (overvalued)", 35, 50, "bearish"),
        ("AMD Bullish (undervalued)", 180, 140, "bullish"),
    ]
    
    for name, dcf, spot, view in scenarios:
        print(f"{name}:")
        print(f"  DCF: ${dcf:.2f}, Spot: ${spot:.2f}, View: {view}")
        
        result = calculate_adaptive_dcf_weight(dcf, spot, view)
        
        print(f"  → Weight: {result['weight']:.2f} (vs 0.30 default)")
        print(f"  → Score: {result['score']:.2f}")
        print(f"  → Gap: {result['gap_pct']*100:+.1f}%")
        print(f"  → Interpretation: {result['interpretation']}")
        print()
    
    print("="*70 + "\n")
