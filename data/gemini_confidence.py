"""
Gemini AI-Enhanced Confidence Calculation
Replaces deterministic confidence with AI-powered analysis

Updated for new google.genai package and price guidance
"""

import os
import uuid

# Import Gemini analyst (ensure SINGLE module instance)
try:
    from data.gemini_analyst_v2 import analyze_with_ai, ask_ai_question
    GEMINI_AVAILABLE = True
except ImportError:
    try:
        from .gemini_analyst_v2 import analyze_with_ai, ask_ai_question
        GEMINI_AVAILABLE = True
    except ImportError:
        GEMINI_AVAILABLE = False
        print("WARNING: Gemini AI not available. Falling back to standard confidence.")

# AI conviction schema
try:
    from data.ai_schemas import (
        AIConviction, build_ai_conviction, fallback_ai_conviction,
        ai_conviction_label, compute_disagreement, AIAnalysisResponse,
    )
    AI_SCHEMAS_AVAILABLE = True
except ImportError:
    AI_SCHEMAS_AVAILABLE = False

# Trace cache for debug
try:
    from data.cache import GEMINI_TRACE_CACHE
    TRACE_CACHE_AVAILABLE = True
except (ImportError, AttributeError):
    TRACE_CACHE_AVAILABLE = False
    GEMINI_TRACE_CACHE = None


def compute_confidence_with_ai(
    ticker: str,
    user_stance: str,  # "bullish" or "bearish"
    spot_price: float,
    intrinsic_value: float,
    macro_regime: str,
    earnings_data: dict,
    valuation_data: dict,
    company_info: dict,
    macro_context: str = None,
    # FULL QUANT STACK:
    technical_data: dict = None,  # ATR, VWAP, exec bands, support/resistance
    alpha_data: dict = None,      # Alpha vs sector, regime
    iv_data: dict = None,          # IV rank, percentile, term structure
    peer_data: dict = None,        # Peer comparisons, relative valuation
    extra_info: str = None,        # INSIDER INFORMATION (~80% credibility)
) -> dict:
    """
    Gemini AI-Enhanced Confidence Calculation.
    
    Returns confidence + AI report + PRICE GUIDANCE
    
    Args:
        ticker: Stock symbol
        user_stance: "bullish" or "bearish"
        spot_price: Current stock price
        intrinsic_value: DCF intrinsic value
        macro_regime: Current macro environment
        earnings_data: Recent earnings track record
        valuation_data: P/E, P/S, margins, etc.
        company_info: Description, sector, industry
        macro_context: Optional macro events context
    
    Returns:
        {
            'confidence': int (0-100),
            'ai_report': str,
            'key_drivers': List[str],
            'risks': List[str],
            'time_horizon': str,
            'entry_price_low': float,
            'entry_price_high': float,
            'entry_price_avg': float,
            'conservative_entry_low': float,
            'conservative_entry_high': float,
            'conservative_entry_avg': float,
            'reasoning': dict,
            'gemini_used': bool
        }
    """
    
    # Initialize score variables (needed for template compatibility in both code paths)
    dcf_score = 0.5  # Neutral default
    macro_score = 0.5  # Neutral default
    earnings_score = 0.5  # Neutral default
    
    # Calculate actual scores for fallback use
    try:
        # DCF score
        if intrinsic_value and spot_price and spot_price > 0:
            gap = (intrinsic_value - spot_price) / spot_price
            dcf_score = max(0.0, min(1.0, (gap + 0.30) / 0.60))
        
        # Macro score
        macro_mapping = {
            'Risk Off': 0.3, 'RISK_OFF': 0.3,
            'Neutral': 0.5, 'NEUTRAL': 0.5,
            'Risk On': 0.7, 'RISK_ON': 0.7
        }
        macro_score = macro_mapping.get(macro_regime, 0.5)
        
        # Earnings score
        if earnings_data and isinstance(earnings_data, dict):
            quarters = earnings_data.get('quarters', [])
            if quarters and len(quarters) >= 2:
                beats = sum(1 for q in quarters if q.get('beat', False))
                earnings_score = beats / len(quarters)
    except Exception:
        pass  # Use default neutral values
    
    if not GEMINI_AVAILABLE:
        return _fallback_confidence(
            spot_price, intrinsic_value, macro_regime, earnings_data
        )
    
    try:
        # Prepare company data
        company_data = {
            'name': company_info.get('name', ticker),
            'sector': company_info.get('sector', 'Unknown'),
            'industry': company_info.get('industry', 'Unknown'),
            'description': company_info.get('description', '')[:500],
        }
        
        # Prepare valuation data with spot price
        val_data = {
            'spot_price': spot_price,  # CRITICAL: Include spot price
            'intrinsic_value': intrinsic_value,
            'dcf_gap_pct': ((intrinsic_value - spot_price) / spot_price * 100) if spot_price > 0 else 0,
            'pe_ratio': valuation_data.get('pe_ratio'),
            'ps_ratio': valuation_data.get('ps_ratio'),
            'profit_margin': valuation_data.get('profit_margin'),
            'revenue_growth': valuation_data.get('revenue_growth'),
            'eps_growth': valuation_data.get('eps_growth'),
        }
        
        # Assess DCF reliability (critical for weighting)
        dcf_gap_abs = abs((intrinsic_value - spot_price) / spot_price) if (intrinsic_value and spot_price > 0) else 0
        dcf_reliable = dcf_gap_abs < 0.30  # DCF within 30% of spot = reliable
        
        # Prepare comprehensive context with ALL analytical data
        full_context = f"""
Macro regime: {macro_regime}. {macro_context or ''}

CRITICAL: DCF Analysis
- DCF Intrinsic: ${intrinsic_value if intrinsic_value else 'N/A'}
- Current Spot: ${spot_price}
- Gap: {dcf_gap_abs*100:.1f}%
- DCF Reliability: {'HIGH - use as anchor' if dcf_reliable else 'LOW - DCF too far from reality, use market price + technicals as primary'}

Technical Analysis (ATR, VWAP, Support/Resistance):
{technical_data if technical_data else 'Not available'}

Alpha Analysis (vs Sector Performance):
{alpha_data if alpha_data else 'Not available'}

Options/Volatility Context (IV Rank):
{iv_data if iv_data else 'Not available'}

Peer Comparisons (Relative Valuation):
{peer_data if peer_data else 'Not available'}
"""
        
        # Call Gemini AI with FULL analytical context + INSIDER INFO
        ai_analysis = analyze_with_ai(
            ticker=ticker,
            user_stance=user_stance,
            company_data=company_data,
            earnings_data=earnings_data,
            valuation_data=val_data,
            macro_context=full_context,
            extra_info=extra_info  # Insider information (~80% credibility)
        )
        
        # Extract confidence score and price guidance
        confidence = ai_analysis.get('confidence', 50)
        
        # Get price ranges from AI
        entry_low = ai_analysis.get('entry_price_low')
        entry_high = ai_analysis.get('entry_price_high')
        cons_low = ai_analysis.get('conservative_entry_low')
        cons_high = ai_analysis.get('conservative_entry_high')
        
        # Validate AI entry prices make sense for the stance
        # For BULLISH: entry should be BELOW spot (buy dips)
        # For BEARISH: entry should be ABOVE spot (short rallies)
        if user_stance.lower() == 'bullish':
            # Entry should be below current price
            if entry_low and entry_low > spot_price * 1.05:  # Entry more than 5% above spot? Wrong!
                print(f"WARNING: AI suggested bullish entry ${entry_low} above spot ${spot_price}. Using fallback.")
                entry_low = None
            if entry_high and entry_high > spot_price * 1.05:
                print(f"WARNING: AI suggested bullish entry ${entry_high} above spot ${spot_price}. Using fallback.")
                entry_high = None
            # Fallback: Use intrinsic value if available
            if intrinsic_value and intrinsic_value > 0:
                # Entry near intrinsic with macro-based discount
                margin = 0.20 if macro_regime == 'Risk Off' else 0.15 if macro_regime == 'Neutral' else 0.10
                base_entry = intrinsic_value * (1 - margin * 0.5)
                if not entry_low: entry_low = base_entry * 0.95
                if not entry_high: entry_high = min(base_entry * 1.05, spot_price * 0.92)
                if not cons_low: cons_low = intrinsic_value * (1 - (margin + 0.10) * 0.5) * 0.95
                if not cons_high: cons_high = intrinsic_value * (1 - (margin + 0.10) * 0.5) * 1.05
            else:
                # No DCF, use spot-based with macro discount
                margin = 0.20 if macro_regime == 'Risk Off' else 0.15 if macro_regime == 'Neutral' else 0.10
                if not entry_low: entry_low = spot_price * (1 - margin - 0.05)
                if not entry_high: entry_high = spot_price * (1 - margin + 0.02)
                if not cons_low: cons_low = spot_price * (1 - margin - 0.10)
                if not cons_high: cons_high = spot_price * (1 - margin - 0.03)
        else:  # bearish or neutral
            # For bearish, entry should be above spot (short on rallies)
            # For neutral, use reasonable range around spot
            if not entry_low: entry_low = spot_price * 0.90
            if not entry_high: entry_high = spot_price * 1.05
            if not cons_low: cons_low = spot_price * 0.92
            if not cons_high: cons_high = spot_price * 0.98
        
        # Calculate averages
        entry_avg = (entry_low + entry_high) / 2 if (entry_low and entry_high) else spot_price
        cons_avg = (cons_low + cons_high) / 2 if (cons_low and cons_high) else spot_price * 0.95
        
        # Build detailed reasoning
        reasoning = {
            'gemini_confidence': confidence,
            'dcf_gap_pct': val_data['dcf_gap_pct'],
            'macro_regime': macro_regime,
            'earnings_beat_rate': _get_beat_rate(earnings_data),
            'ai_key_drivers': ai_analysis.get('key_drivers', []),
            'ai_risks': ai_analysis.get('risks', []),
        }
        
        # Build AIConviction from structured output fields
        trace_id = str(uuid.uuid4())[:8] if AI_SCHEMAS_AVAILABLE else None
        ai_conviction_obj = None
        if AI_SCHEMAS_AVAILABLE:
            try:
                # Check if analysis came from structured output
                if ai_analysis.get("_structured"):
                    # Build a mock AIAnalysisResponse-like object for build_ai_conviction
                    class _MockAIResp:
                        conviction_0_100 = ai_analysis.get("conviction_0_100", confidence)
                        conviction_label = ai_analysis.get("conviction_label", "Medium")
                        conviction_drivers = ai_analysis.get("conviction_drivers", ai_analysis.get("key_drivers", []))
                        conviction_risks = ai_analysis.get("conviction_risks", ai_analysis.get("risks", []))
                        overlay_note = ai_analysis.get("overlay_note")
                        notes_on_overlay = ai_analysis.get("notes_on_overlay")
                    ai_conviction_obj = build_ai_conviction(
                        _MockAIResp(),
                        # NOTE: official_confidence is intentionally 0 here.
                        # Disagreement is recomputed in _build_ai_conviction_safe (app.py)
                        # against the real Option A deterministic score. The value set
                        # here is overwritten and never reaches the template.
                        official_confidence=0,
                        model_name=ai_analysis.get("_model", "gemini-2.5-flash"),
                        trace_id=trace_id,
                    )
                    # Store trace
                    if TRACE_CACHE_AVAILABLE and GEMINI_TRACE_CACHE:
                        GEMINI_TRACE_CACHE.set(trace_id, {
                            "ts": __import__("time").time(),
                            "ticker": ticker,
                            "conviction": ai_conviction_obj.score_0_100,
                        })
                else:
                    # Legacy parsed output — build basic conviction
                    score = confidence
                    label = ai_conviction_label(score)
                    ai_conviction_obj = AIConviction(
                        available=True,
                        score_0_100=score,
                        label=label,
                        drivers=ai_analysis.get("key_drivers", [])[:5],
                        risks=ai_analysis.get("risks", [])[:5],
                        model="gemini-legacy",
                        trace_id=trace_id,
                    )
            except Exception as _ce:
                print(f"AIConviction build error: {_ce}")
                ai_conviction_obj = fallback_ai_conviction()
        else:
            ai_conviction_obj = None

        return {
            'available': True,  # Flag for template to show AI section
            'confidence': confidence,
            'total': confidence,  # Template compatibility
            'ai_report': ai_analysis.get('report', 'Analysis unavailable'),
            'key_drivers': ai_analysis.get('key_drivers', []),
            'risks': ai_analysis.get('risks', []),
            'time_horizon': ai_analysis.get('time_horizon', 'Unknown'),

            # Price guidance
            'entry_price_low': entry_low if entry_low is not None else spot_price * 0.97,
            'entry_price_high': entry_high if entry_high is not None else spot_price * 1.03,
            'entry_price_avg': entry_avg if entry_avg else spot_price,
            'conservative_entry_low': cons_low if cons_low is not None else spot_price * 0.95,
            'conservative_entry_high': cons_high if cons_high is not None else spot_price * 1.02,
            'conservative_entry_avg': cons_avg if cons_avg else spot_price * 0.98,
            'target_price_base': ai_analysis.get('target_price_base'),
            'target_price_bull': ai_analysis.get('target_price_bull'),
            'target_price_bear': ai_analysis.get('target_price_bear'),

            # AI Conviction (secondary — NEVER drives risk controls)
            'ai_conviction': ai_conviction_obj,

            # Note: weights/contrib NOT emitted here — Official Confidence owns those.
            # Only provide the raw score for template compatibility.
            'raw': confidence / 100.0,

            'reasoning': reasoning,
            'gemini_used': True,
            '_trace_id': trace_id,
        }
    
    except Exception as e:
        print(f"Gemini AI error: {e}")
        import traceback
        traceback.print_exc()
        # Fallback on error
        return _fallback_confidence(
            spot_price, intrinsic_value, macro_regime, earnings_data
        )


def _get_beat_rate(earnings_data: dict) -> float:
    """Calculate earnings beat rate from earnings data."""
    if not earnings_data or 'quarters' not in earnings_data:
        return 0.5
    
    quarters = earnings_data.get('quarters', [])
    if not quarters:
        return 0.5
    
    beats = sum(1 for q in quarters 
                if q.get('results', {}).get('eps', {}).get('verdict') == 'beat')
    
    return beats / len(quarters) if quarters else 0.5


def _fallback_confidence(
    spot_price: float,
    intrinsic_value: float,
    macro_regime: str,
    earnings_data: dict
) -> dict:
    """
    Smart fallback confidence if Gemini unavailable.
    Uses DCF, macro, and earnings to derive intelligent entry prices.
    """
    
    # DCF contribution
    if intrinsic_value and spot_price > 0:
        dcf_gap = (intrinsic_value - spot_price) / spot_price
        if dcf_gap <= -0.30:
            dcf_score = 0
        elif dcf_gap >= 0.30:
            dcf_score = 100
        else:
            dcf_score = ((dcf_gap + 0.30) / 0.60) * 100
    else:
        dcf_score = 50
    
    # Macro contribution
    macro_map = {
        'Risk Off': 30,
        'Neutral': 50,
        'Risk On': 70
    }
    macro_score = macro_map.get(macro_regime, 50)
    
    # Earnings contribution
    beat_rate = _get_beat_rate(earnings_data)
    earnings_score = beat_rate * 100
    
    # Weighted average
    confidence = int(dcf_score * 0.5 + macro_score * 0.25 + earnings_score * 0.25)
    confidence = max(0, min(100, confidence))
    
    # SMART FALLBACK ENTRY PRICES - Use analytical factors!
    
    # Step 1: Determine margin of safety based on macro
    if macro_regime == 'Risk Off':
        margin_of_safety = 0.20  # 20% discount
    elif macro_regime == 'Risk On':
        margin_of_safety = 0.10  # 10% discount
    else:  # Neutral
        margin_of_safety = 0.15  # 15% discount
    
    # Step 2: Adjust for earnings quality
    if beat_rate >= 0.75:  # Strong earnings
        margin_of_safety -= 0.03  # Can be more aggressive
    elif beat_rate <= 0.25:  # Weak earnings
        margin_of_safety += 0.05  # Need bigger discount
    
    # Step 3: Calculate entry based on DCF intrinsic or spot
    if intrinsic_value and intrinsic_value > 0:
        # Use intrinsic value as anchor
        base_entry = intrinsic_value * (1 - margin_of_safety * 0.7)
        # But don't go above spot - entry should be below current
        base_entry = min(base_entry, spot_price * 0.92)
    else:
        # No DCF, use spot with margin
        base_entry = spot_price * (1 - margin_of_safety)
    
    # Normal entry range (wider range for flexibility)
    entry_low = base_entry * 0.95  # Slightly below base
    entry_high = base_entry * 1.05  # Slightly above base
    
    # Conservative entry (more patient, bigger discount)
    cons_margin = margin_of_safety + 0.10  # Extra 10% discount
    if intrinsic_value and intrinsic_value > 0:
        cons_base = intrinsic_value * (1 - cons_margin * 0.7)
        cons_base = min(cons_base, spot_price * 0.85)
    else:
        cons_base = spot_price * (1 - cons_margin)
    
    cons_low = cons_base * 0.95
    cons_high = cons_base * 1.05
    
    # Ensure entry makes sense (below spot for buying)
    entry_high = min(entry_high, spot_price * 0.95)  # Never above 95% of spot
    cons_high = min(cons_high, spot_price * 0.90)    # Never above 90% of spot
    
    return {
        'available': False,  # No AI available
        'confidence': confidence,
        'total': confidence,  # Template compatibility
        'ai_report': 'Gemini AI analysis unavailable. Using formula-based confidence.',
        'key_drivers': ['DCF valuation', 'Macro regime', 'Earnings consistency'],
        'risks': ['Limited AI analysis', 'Formula-based only'],
        'time_horizon': 'Medium-term',
        
        # Price guidance
        'entry_price_low': entry_low,
        'entry_price_high': entry_high,
        'entry_price_avg': (entry_low + entry_high) / 2,
        'conservative_entry_low': cons_low,
        'conservative_entry_high': cons_high,
        'conservative_entry_avg': (cons_low + cons_high) / 2,
        'target_price_base': None,
        'target_price_bull': None,
        'target_price_bear': None,

        
        # Template compatibility - breakdown with real scores (no dummy zero weights)
        'breakdown': {
            'dcf': dcf_score,
            'macro': macro_score,
            'industry': 0.5,
            'company': 0.5,
            'vol': 0.5,
            'earnings': earnings_score,
            'liquidity': 0.5,
            'alpha': 0.5,
        },
        'raw': confidence / 100.0,  # Normalized to 0-1
        
        'reasoning': {
            'dcf_score': dcf_score,
            'macro_score': macro_score,
            'earnings_score': earnings_score,
        },
        'gemini_used': False,
    }


def ask_ai_about_stock(ticker: str, question: str) -> str:
    """
    Ask follow-up question to AI about the stock.
    
    Args:
        ticker: Stock symbol
        question: User's question
    
    Returns:
        AI's answer
    """
    if not GEMINI_AVAILABLE:
        return "Gemini AI not available for Q&A."
    
    try:
        return ask_ai_question(ticker, question)
    except Exception as e:
        return f"Error getting AI response: {e}"