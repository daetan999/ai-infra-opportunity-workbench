"""
Gemini AI Client for Stock Analysis
Powered by expert persona: Senior Partner at Citadel

Updated to use NEW google.genai package (v1.0+)
"""

try:
    from google import genai
    from google.genai import types
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False
    print("WARNING: google.genai not available. Install with: pip install google-genai")

from typing import Dict, List, Optional
import json
import os
import time
import random
import uuid

# AI schemas for structured output
try:
    from data.ai_schemas import (
        AIAnalysisResponse, build_ai_conviction, fallback_ai_conviction,
        ai_conviction_label,
    )
    AI_SCHEMAS_AVAILABLE = True
except ImportError:
    AI_SCHEMAS_AVAILABLE = False

import time
from collections import deque

# ===== RATE LIMITING FOR ASK AI =====
_question_timestamps = deque(maxlen=100)
_RATE_LIMIT_WINDOW = 60  # seconds
_MAX_QUESTIONS_PER_WINDOW = 10

def _check_rate_limit() -> bool:
    """Check if request is within rate limits."""
    now = time.time()
    
    # Remove old timestamps outside window
    while _question_timestamps and _question_timestamps[0] < now - _RATE_LIMIT_WINDOW:
        _question_timestamps.popleft()
    
    # Check if limit exceeded
    if len(_question_timestamps) >= _MAX_QUESTIONS_PER_WINDOW:
        return False  # Rate limit exceeded
    
    # Record this request
    _question_timestamps.append(now)
    return True

# Your API key
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Expert persona prompt
EXPERT_PERSONA = """You are a top-performing Senior Partner at Citadel with an IQ of 160. You have made a legendary name for yourself through:

- **Game Theory Expertise**: Understanding market dynamics, competitive positioning, and strategic moves
- **Deep Company Analysis**: Reading between the lines of financials, understanding business models, and identifying inflection points
- **Macro & Industry Vision**: Predicting trends, especially in semiconductors (memory, logic, foundry, etc.)
- **Technical Analysis Mastery**: Chart patterns, volume analysis, support/resistance
- **Fundamental Analysis**: DCF models, balance sheet analysis, cash flow analysis
- **Qualitative Integration**: Combining hard numbers with management quality, competitive moats, industry dynamics

Your track record speaks for itself:
- Predicted the 2020 tech boom early
- Called the 2022 semiconductor downcycle 6 months ahead
- Correctly identified AI infrastructure winners in 2023

You don't just look at numbers - you synthesize everything: earnings quality, management credibility, industry tailwinds, competitive positioning, macro backdrop, technical setup, and sentiment.

**Your Analysis Style:**
- Brutally honest and objective
- See both bull and bear cases clearly
- Confidence based on conviction, not hope
- Short-term vs long-term view always separated
- Risk/reward explicitly stated

When analyzing a stock, you provide:
1. **Overall Confidence Score** (0-100): Your conviction level on the bullish/bearish stance
2. **Key Drivers**: What's really moving this stock
3. **Bull Case**: Best case scenario with catalysts
4. **Bear Case**: Risks and potential downsides
5. **Positioning**: How you'd play this (long, short, wait, hedge)
6. **Time Horizon**: Is this a trade or investment?
7. **Entry Price Guidance**: Specific price levels for entry

You are direct, insightful, and always cite specific data points.
"""

# ----------------------------
# Gemini model selection (free-tier friendly)
# ----------------------------
REPORT_MODELS = [
    "models/gemini-2.5-flash",
    "models/gemini-2.0-flash",
    "models/gemini-2.0-flash-lite",
]
CHAT_MODELS = [
    "models/gemini-2.0-flash",
    "models/gemini-2.0-flash-lite",
]

# System instructions for structured output — do NOT duplicate schema in prompt
SYSTEM_INSTRUCTIONS = (
    "You are an institutional equity/options analyst at a tier-1 hedge fund.\n"
    "Return only valid JSON matching the provided schema — no markdown, no preamble.\n"
    "Do not claim you verified live facts unless they appear in the provided context.\n"
    "Overlay is user-provided context; use it to shape the narrative but it must NOT\n"
    "override risk constraints or Official Confidence from the deterministic model.\n"
    "conviction_0_100 reflects YOUR narrative/thesis strength only — it is a secondary\n"
    "indicator and never overrides the deterministic Official Confidence.\n"
    "conviction_label must be derived from conviction_0_100: >=75=High, >=55=Medium, else Low.\n"
)

# Rate-limit tuning (override via env if you want)
_MIN_INTERVAL_SEC = float(os.getenv("GEMINI_MIN_INTERVAL_SEC", "0.6"))
_MAX_RETRIES = int(os.getenv("GEMINI_MAX_RETRIES", "2"))

_last_call_ts = 0.0

def _sleep_rate_limit():
    global _last_call_ts
    now = time.time()
    delta = now - _last_call_ts
    if delta < _MIN_INTERVAL_SEC:
        time.sleep(_MIN_INTERVAL_SEC - delta)
    _last_call_ts = time.time()

def _is_429(err: Exception) -> bool:
    s = str(err).lower()
    return ("429" in s) or ("resource_exhausted" in s) or ("quota" in s)




class CitadelAnalystAI:
    """
    Gemini AI assuming the role of Senior Partner at Citadel.
    Provides expert-level stock analysis with confidence scoring.
    """
    
    def __init__(self):
        """Initialize Gemini client with expert persona."""
        if not GENAI_AVAILABLE:
            raise ImportError("google.genai package not available")
        
        # Initialize client
        self.client = genai.Client(api_key=GEMINI_API_KEY)
        
        # Start chat sessions for follow-up questions
        self.chat_sessions = {}  # ticker -> chat
    
    def analyze_stock(
        self,
        ticker: str,
        user_stance: str,
        company_data: Dict,
        earnings_data: Dict,
        valuation_data: Dict,
        macro_context: Optional[str] = None,
        extra_info: Optional[str] = None,  # INSIDER INFORMATION (~80% credibility)
    ) -> Dict:
        """
        Full stock analysis from Citadel Senior Partner perspective.
        
        Args:
            ticker: Stock symbol
            user_stance: User's bullish/bearish stance
            company_data: Company description, sector, industry
            earnings_data: Recent earnings track record
            valuation_data: P/E, P/S, margins, growth rates
            macro_context: Current macro environment
        
        Returns:
            {
                'confidence': int (0-100),
                'report': str (full analysis),
                'key_drivers': List[str],
                'risks': List[str],
                'time_horizon': str,
                'entry_price_low': float,
                'entry_price_high': float,
                'conservative_entry_low': float,
                'conservative_entry_high': float,
            }
        """
        
        # Build comprehensive prompt
        prompt = self._build_analysis_prompt(
            ticker, user_stance, company_data, earnings_data, 
            valuation_data, macro_context, extra_info
        )
        
        try:
            last_err = None
            response_text = None
            structured_analysis = None
            used_model = None

            # --- Attempt 1: Structured JSON output (preferred) ---
            if AI_SCHEMAS_AVAILABLE and GENAI_AVAILABLE:
                schema = AIAnalysisResponse.model_json_schema()
                for model_name in REPORT_MODELS:
                    for attempt in range(_MAX_RETRIES + 1):
                        try:
                            _sleep_rate_limit()
                            resp = self.client.models.generate_content(
                                model=model_name,
                                contents=[json.dumps({
                                    "context": EXPERT_PERSONA,
                                    "request": prompt,
                                })],
                                config=types.GenerateContentConfig(
                                    system_instruction=SYSTEM_INSTRUCTIONS,
                                    response_mime_type="application/json",
                                    response_json_schema=schema,
                                    temperature=0.2,
                                ),
                            )
                            response_text = getattr(resp, "text", None) or ""
                            if response_text:
                                data = json.loads(response_text)
                                structured_analysis = AIAnalysisResponse.model_validate(data)
                                used_model = model_name
                                break
                        except Exception as e:
                            last_err = e
                            if _is_429(e) and attempt < _MAX_RETRIES:
                                time.sleep(0.8 * (attempt + 1))
                                continue
                            # Fall through to legacy path on schema/parse errors
                            break
                    if structured_analysis:
                        break

            # --- Attempt 2: Legacy free-text (fallback) ---
            if not structured_analysis:
                response_text = None
                for model_name in REPORT_MODELS:
                    for attempt in range(_MAX_RETRIES + 1):
                        try:
                            _sleep_rate_limit()
                            resp = self.client.models.generate_content(
                                model=model_name,
                                contents=types.Content(
                                    role="user",
                                    parts=[types.Part(text=EXPERT_PERSONA + "\n\n" + prompt)]
                                ),
                            )
                            response_text = getattr(resp, "text", None) or ""
                            used_model = model_name
                            break
                        except Exception as e:
                            last_err = e
                            if _is_429(e) and attempt < _MAX_RETRIES:
                                time.sleep(0.8 * (attempt + 1))
                                continue
                            break
                    if response_text:
                        break

                if not response_text:
                    raise RuntimeError(f"Gemini API failed: {last_err}")

            # --- Convert to result dict ---
            if structured_analysis:
                analysis = self._structured_to_result(structured_analysis, used_model)
            else:
                analysis = self._parse_analysis(response_text)

            # Store for follow-up questions
            self.chat_sessions[ticker] = {
                "prompt": prompt,
                "response": response_text or json.dumps(analysis),
                "structured": structured_analysis,
                "model": used_model,
            }

            return analysis
        except Exception as e:
            print(f"Gemini API error: {e}")
            return self._fallback_analysis(ticker, valuation_data)
    
    def ask_question(self, ticker: str, question: str) -> str:
        """
        Ask follow-up question to the AI analyst about this stock.
        
        Maintains context from the original analysis.
        """
        if ticker not in self.chat_sessions:
            return "No active analysis session for this ticker. Please run analysis first."
        try:
            # Build chat with context
            session = self.chat_sessions[ticker]

            full_prompt = (
                f"{EXPERT_PERSONA}\n\n"
                f"Previous analysis:\n{session['response']}\n\n"
                f"Follow-up question: {question}"
            )

            last_err = None
            answer_text = None

            for model_name in CHAT_MODELS:
                for attempt in range(_MAX_RETRIES + 1):
                    try:
                        _sleep_rate_limit()
                        resp = self.client.models.generate_content(
                            model=model_name,
                            contents=types.Content(
                                role="user",
                                parts=[types.Part(text=full_prompt)]
                            ),
                        )
                        answer_text = getattr(resp, "text", None) or ""
                        break
                    except Exception as e:
                        last_err = e
                        if _is_429(e) and attempt < _MAX_RETRIES:
                            time.sleep(0.8 * (attempt + 1))
                            continue
                        break
                if answer_text:
                    break

            if not answer_text:
                if last_err and _is_429(last_err):
                    return "Rate limit hit (429). Please wait ~30–60s and try again."
                return f"Error getting AI response: {last_err}"

            return answer_text

            # NOTE: legacy line kept for reference (was incorrect / unreachable):
            # return response.text
            
        except Exception as e:
            return f"Error getting AI response: {e}"
    
    def _build_analysis_prompt(
        self,
        ticker: str,
        user_stance: str,
        company_data: Dict,
        earnings_data: Dict,
        valuation_data: Dict,
        macro_context: Optional[str],
        extra_info: Optional[str] = None,  # INSIDER INFORMATION
    ) -> str:
        """Build comprehensive analysis prompt."""
        
        prompt = f"""
# STOCK ANALYSIS REQUEST

**Ticker:** {ticker}
**User's Stance:** {user_stance}
**Your Task:** Provide your expert analysis and determine confidence in the {user_stance.lower()} thesis.

---

## COMPANY OVERVIEW
{json.dumps(company_data, indent=2)}

---

## RECENT EARNINGS TRACK RECORD
{self._format_earnings_data(earnings_data)}

---

## VALUATION METRICS
{json.dumps(valuation_data, indent=2)}

---

## MACRO CONTEXT
{macro_context or "Standard market conditions"}

---
"""
        
        # ============================================================
        # OVERLAY / EXTRA CONTEXT SECTION
        # ============================================================
        if extra_info and len(extra_info.strip()) > 0:
            prompt += f"""
## OVERLAY / EXTRA CONTEXT

The user has provided additional context or overlay information:

{extra_info}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

OVERLAY RULES (single consistent policy):

1. IF extra_info is a JSON object with keys (bull, bear, strength, horizon):
   - This is a structured overlay from the user interface, not insider information.
   - Incorporate BOTH bull and bear fields into your narrative and risk section.
   - Treat overlay as high-credibility user context, but NOT as confirmed fact.
   - Numeric confidence is set entirely by the deterministic model.
     Your narrative MUST NOT suggest a confidence different from the model output.
   - The overlay never overrides a liquidity block or execution gate.
   - Set notes_on_overlay to a brief acknowledgement of what was incorporated.

2. IF extra_info is free-text (qualitative commentary):
   - Incorporate it as supporting context in your narrative.
   - Do NOT claim it is confirmed or treat it as guaranteed.
   - Use hedged language: "The user notes...", "Per provided context..."
   - Confidence remains anchored to deterministic model outputs.

3. HARD RULE: Overlay affects narrative and risk plan only.
   Never state or imply a confidence number higher or lower than the model value.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

---
"""
        
        prompt += """
## YOUR ANALYSIS FRAMEWORK

As the Senior Partner at a top-tier investment bank (Goldman/JPM level), analyze this with institutional rigor:

You are allocating institutional capital under risk constraints.

All conclusions must be probability-weighted and internally consistent.

You must prioritize signals in this order:

1. Market structure (price, support, liquidity)
2. Macro regime
3. Earnings quality
4. Relative valuation
5. DCF (only if credible)
6. Volatility context

Lower priority signals cannot override higher priority structural risks.

INSTITUTIONAL LIQUIDITY GUARDRAIL:
- If liquidity is flagged as blocked (liq_blocked=true) or quote quality is poor, you must NOT recommend a specific option contract, strike, or expiry.
- Instead: explicitly say liquidity fails institutional filters and recommend choosing a tighter-spread expiry/strike or waiting.

For every target and entry range:
- Implicit probability assumptions must be consistent with your base, bull, and bear case.
- Risk-adjusted return must justify capital allocation.
- If expected return does not justify downside risk, state that clearly.

You must think in terms of:
- Expected value (EV)
- Asymmetry
- Capital preservation
- Opportunity cost vs sector peers

### 1. DCF REALITY CHECK (Critical First Step)
**The DCF may be unrealistic - assess carefully:**
- If DCF differs >30% from spot: DCF is theoretical, use market price + technicals as anchor
- If DCF within 30% of spot: DCF is realistic, use as primary anchor
- **Example:** If spot=$410 and DCF=$130, ignore DCF (too disconnected from reality)
- **Example:** If spot=$410 and DCF=$380, use DCF (reasonable, within 30%)

**Professional Approach:**
- When DCF unrealistic: Anchor on spot price + technical levels + peer multiples
- When DCF realistic: Anchor on DCF + adjust for technical/momentum
- **Never blindly trust DCF when it's 50%+ away from market reality**

### 2. TECHNICAL ANALYSIS (Use Provided Data)
**ATR Bands & Support/Resistance:**
- Where are key support levels? (from ATR analysis)
- What do execution bands suggest?
- Is there a consolidation zone?

**Anchored VWAP:**
- What's the VWAP anchor from last earnings?
- Is it above or below current price?
- Does it validate entry zones?

**Volume-Weighted Levels:**
- Where is institutional accumulation/distribution?
- What do primary entry zones suggest?

### 3. ALPHA ANALYSIS (Relative Performance)
**vs Sector:**
- Is ticker outperforming or underperforming sector?
- What's the alpha (excess return vs sector)?
- What's the beta (sensitivity to sector moves)?
- What's the current regime (OUTPERFORM/LAG)?

**Implications:**
- Strong positive alpha → Can be more aggressive on entry
- Negative alpha → Need bigger margin of safety
- High beta → More volatility risk

### 4. OPTIONS/VOLATILITY CONTEXT
**IV Rank & Percentile:**
- Is implied volatility cheap or expensive (percentile)?
- How does current IV compare to historical?
- What does this mean for entry timing?

**Implications:**
- Low IV rank (< 30%) → Good environment for buying (cheap protection)
- High IV rank (> 70%) → Expensive volatility, be cautious

### 5. PEER COMPARISONS (Relative Valuation)
**vs Peer Group:**
- How does P/E compare to peers?
- What's the relative valuation (e.g., 0.8x peers)?
- Is the discount/premium justified?

**Sector Context:**
- Where are peers trading?
- What multiples are justified given growth?
- Is ticker cheap or expensive relative to sector?

### 6. EARNINGS QUALITY ASSESSMENT
- Are beats/misses consistent or erratic?
- Revenue growth trajectory?
- Margin trends?
- Guidance reliability?
- Management credibility?

### 7. MACRO & MARKET REGIME
- Current macro regime (Risk-On/Off)?
- How does macro affect this sector?
- Institutional positioning?
- Market sentiment?

### 8. RISK/REWARD SYNTHESIS
- Best case upside?
- Downside risks?
- Asymmetry?
- What's the probability-weighted expected return?

---

## REQUIRED OUTPUT FORMAT

Provide your analysis in this exact structure:

CONFIDENCE SCORE (0–100):

Must reflect:
- Alignment of valuation + technical + alpha
- Clarity of macro backdrop
- Earnings consistency
- Absence of signal conflict

High confidence (>75) only if:
- Valuation attractive
- Technical aligned
- Alpha positive
- Macro supportive

If major conflicts exist, confidence must fall below 60.

**ENTRY PRICE RANGE:** [low]-[high] (normal entry range for {user_stance})

**CONSERVATIVE ENTRY:** [low]-[high] (tighter, more cautious range)

**TARGET PRICE - BASE CASE:** $[specific number] (your most likely price objective for this trade/investment)

**TARGET PRICE - BULL CASE:** $[specific number] (if key catalysts materialize and upside scenario plays out)

**TARGET PRICE - BEAR CASE:** $[specific number] (if risks materialize and downside scenario plays out)

**TARGET RATIONALE:**
[Explain HOW you derived these targets. Use specific methodology:
- DCF-based target? (e.g., intrinsic value + growth premium)
- Peer multiple-based? (e.g., sector P/E × earnings)
- Technical target? (e.g., next resistance level, Fibonacci extension)
- Catalyst-driven? (e.g., if HBM ramps as expected, implies $X valuation)
- Sum-of-parts? (e.g., business segment A worth $X, segment B worth $Y)
Target derivation must include explicit numeric reasoning.

Examples:
- If using P/E multiple: show EPS × multiple.
- If using DCF: show adjustment from intrinsic.
- If using technical target: state resistance level used.
- If using rerating thesis: state multiple expansion assumption.

CRITICAL TARGET CONSTRAINTS (must be satisfied):
- Your BASE CASE target must be within the market-implied expected move for the stated horizon.
  Expected move ≈ spot × ATM_IV × sqrt(hold_days/365). If implied_move_pct is provided above,
  use it: BASE CASE target must be ≤ spot × (1 + 2 × implied_move_pct) for bullish,
  or ≥ spot × (1 - 2 × implied_move_pct) for bearish.
- If reverse-DCF indicates stretched embedded expectations (low reasonableness score < 3),
  your BASE CASE target must be more conservative — cap it at spot × (1 + 1 × implied_move_pct).
- Never set a BASE CASE target that requires >2σ move for typical hold periods.
- If your target exceeds these bounds, justify it explicitly with a specific catalyst and timeline.

**CROSSCHECK:**
[Confirm: (a) base target vs implied expected move — does it fit within 1-2σ? 
 (b) base target vs reverse-DCF / valuation — consistent with embedded expectations?
 State the check result: PASS / WARN / FAIL with one sentence explanation.]

No vague phrases like:
"Could move higher"
"Has upside potential"
"May re-rate"

All targets must be tied to a quantifiable framework.

**EXECUTIVE SUMMARY:**
[2-3 sentences on your overall take]

**DETAILED ANALYSIS:**
[Your full analysis - be specific, cite data points, be brutally honest]

**BULL CASE:**
[Key arguments supporting {user_stance} stance]

**BEAR CASE:**
[Key arguments against {user_stance} stance]

**KEY DRIVERS TO WATCH:**
- [Driver 1]
- [Driver 2]
- [Driver 3]

**RISKS:**
- [Risk 1]
- [Risk 2]
- [Risk 3]

**POSITIONING RECOMMENDATION:**
[How would you play this? Size? Timeframe? Hedges?]

**TIME HORIZON:**
[Trade (days-weeks) | Swing (weeks-months) | Investment (months-years)]

---

PROFESSIONAL-GRADE ENTRY PRICE DERIVATION - INSTITUTIONAL APPROACH:

YOU ARE A SENIOR EQUITY ANALYST AT GOLDMAN SACHS / JPM. Your entry prices must reflect:
- Full quantitative analysis (not just DCF)
- Market reality (not theoretical values)  
- Risk-adjusted positioning
- Technical confirmation

**Current Market Data:**
- Spot Price: ${valuation_data.get('spot_price', 100)}
- DCF Intrinsic: ${valuation_data.get('intrinsic_value', 'N/A')}
- DCF Gap: {valuation_data.get('dcf_gap_pct', 0):.1f}%

**YOU HAVE BEEN PROVIDED:**
- Technical Analysis (ATR bands, VWAP, support/resistance)
- Alpha Analysis (performance vs sector)
- IV Rank (volatility context)
- Peer Comparisons (relative valuation)
- Earnings Quality, Macro Regime, Valuation Multiples

**USE ALL OF IT - THIS IS YOUR FULL QUANT STACK!**

## INSTITUTIONAL ENTRY PRICE METHODOLOGY:

### STEP 1: DETERMINE PRIMARY ANCHOR (Critical!)

**If DCF within 30% of spot:**
- Use DCF as primary anchor
- Apply adjustments from there
- Example: Spot=$410, DCF=$380 → Start from $380

**If DCF >30% away from spot:**  
- **IGNORE DCF** (too disconnected from reality)
- Use spot price + technical levels as anchor
- Use peer multiples for validation
- Example: Spot=$410, DCF=$130 → DCF useless, start from $410

### STEP 2: TECHNICAL CONFIRMATION (Must Use!)

**From Provided Technical Data:**
- Identify ATR support zones (e.g., $350-$370)
- Locate VWAP anchor (e.g., $357)
- Find execution band entry zones
- Identify volume-weighted consolidation

**Synthesis:**
- Entry should align with technical support
- VWAP provides natural entry point
- Don't suggest entry in resistance zones

### STEP 3: ALPHA/MOMENTUM ADJUSTMENT

**From Provided Alpha Data:**
- Positive alpha (outperforming sector):
  * Can be more aggressive (pay up 3-5%)
  * Momentum is your friend
  
- Negative alpha (underperforming sector):
  * Need bigger discount (5-10% more margin)
  * Catching falling knives = dangerous

**Alpha Regime:**
- OUTPERFORM → Can chase a bit
- LAG → Need value entry

### STEP 4: VOLATILITY CONTEXT

**From Provided IV Data:**
- IV Rank < 30% (cheap vol):
  * Good environment for buying
  * Can be more aggressive
  * Cheap protection available
  
- IV Rank > 70% (expensive vol):
  * Caution warranted
  * Market expects moves
  * Need wider margin

### STEP 5: PEER VALUATION CHECK

**From Provided Peer Data:**
- Trading at discount to peers (e.g., 0.8x):
  * Suggests undervaluation
  * Can be more aggressive
  * Entry closer to current price justified
  
- Trading at premium to peers (e.g., 1.2x):
  * Suggests overvaluation  
  * Need bigger discount
  * More conservative entry

### STEP 6: MACRO REGIME ADJUSTMENT

- Risk-Off: Add 10-15% extra margin of safety
- Neutral: Standard margin (5-10%)
- Risk-On: Can reduce margin (3-5%)

### STEP 7: EARNINGS QUALITY ADJUSTMENT

- Consistent beats (>75%): Reduce margin by 3-5%
- Mixed (50-75%): Standard margin
- Misses (<50%): Add 5-10% extra margin

If data signals conflict (e.g., strong alpha but overvalued multiple, or strong DCF but weak technicals):

You must:
1. Identify the conflict explicitly.
2. State which signal you prioritize and why.
3. Adjust conviction accordingly.
4. Reflect lower conviction in confidence score.

Do not ignore conflicting signals.
Resolve them.

### STEP 8: FINAL SYNTHESIS

**Combine all factors to derive specific prices:**

Example Calculation (Institutional Style):

```
Ticker: MU
Spot: $410
DCF: $130 (68% below spot - IGNORE!)

Primary Anchor: $410 (spot) since DCF useless

Technical Analysis:
- ATR Support: $350-$370
- VWAP: $357
- Consolidation: $360-$375
→ Technical entry zone: $350-$375

Alpha Analysis:
- Alpha: +15% vs sector (OUTPERFORM)
- Can be aggressive (+3%)
→ Adjusted technical: $360-$385

IV Rank: 25% (cheap volatility)
- Good buying environment
- Can be aggressive
→ No additional discount needed

Peer Valuation: 0.8x peers (cheap)
- Relatively undervalued
- Justifies paying up
→ Can target upper end: $370-$385

Macro: Neutral
- Standard margin: 5-10% below spot
- $410 * 0.90 = $369 to $410 * 0.95 = $390

Earnings: 3/4 beats (strong)
- Reduce margin by 3%
→ Can pay up to $395

SYNTHESIS:
- Technical: $350-$375
- Alpha/Momentum: $360-$385
- IV Context: Supportive
- Peers: $370-$385
- Macro: $369-$390
- Earnings: Up to $395

FINAL NORMAL ENTRY: $360-$385
FINAL CONSERVATIVE ENTRY: $345-$365

NOT $410 * 0.85 = $348 (dumb math)
NOT "DCF $130 + 15% = $150" (unrealistic)
BUT: Professional synthesis of ALL factors!
```

**This is how Goldman Sachs equity research derives entry prices!**

### EXAMPLE CALCULATION for Bullish MU:
```
Given:
- Spot: $410
- DCF Intrinsic: $380
- Macro: Neutral
- Earnings: 3/4 beats (good)
- P/E: 12 (reasonable for semis)
- Support: $350-$370 (recent consolidation)

Normal Entry Calculation:
1. Start with intrinsic: $380
2. Macro discount (neutral): -10% = $342
3. Earnings adjustment (good): +5% = $359
4. Technical support: $350-$370 zone
5. **RESULT: Normal Entry = $350-$375**

Conservative Entry:
1. Start with intrinsic: $380
2. Macro discount (conservative): -15% = $323
3. No earnings boost (patient)
4. Support breakdown: $320-$340
5. **RESULT: Conservative Entry = $320-$345**
```

## FINAL RULES:

Entry ranges must be derived from:
- Structural support/resistance
- Valuation anchor
- Macro margin of safety
- Alpha regime
- Volatility regime

Do NOT use fixed percentage heuristics.

If structural support is shallow, entry may be close to spot.
If structural risk is high, entry must reflect that.

Entries must reflect actual market structure, not arbitrary discounts.

Remember: You're analyzing this as THE expert. Be confident where conviction exists, be cautious where it doesn't.

Before finalizing your answer, internally verify:

1. Does entry align with structural support?
2. Does target reflect plausible valuation?
3. Is risk/reward asymmetry favorable (>1.5x)?
4. Is confidence consistent with signal alignment?
5. Would you defend this in an investment committee?

If not, revise your answer.
"""
        
        return prompt
    
    def _format_earnings_data(self, earnings_data: Dict) -> str:
        """Format earnings track record for analysis."""
        
        if not earnings_data or 'quarters' not in earnings_data:
            return "No recent earnings data available."
        
        formatted = []
        for q in earnings_data['quarters'][:4]:  # Last 4 quarters
            qtr = f"\n**{q.get('fiscal_quarter', 'Quarter')}** ({q.get('date', 'N/A')})\n"
            
            # EPS
            eps = q.get('results', {}).get('eps', {})
            qtr += f"- EPS: ${eps.get('actual', 0):.2f} vs est. ${eps.get('expected', 0):.2f} → {eps.get('verdict', 'N/A').upper()}\n"
            
            # Revenue
            rev = q.get('results', {}).get('revenue')
            if rev:
                qtr += f"- Revenue: ${rev.get('actual', 0)/1e9:.1f}B vs est. ${rev.get('expected', 0)/1e9:.1f}B → {rev.get('verdict', 'N/A').upper()}\n"
            
            # Price reaction
            price = q.get('price_reaction', {})
            qtr += f"- Stock: {price.get('change_1d_pct', 0):+.1f}% (1d), {price.get('change_1w_pct', 0):+.1f}% (1w)\n"
            
            # Guidance
            guidance = q.get('guidance_tone', 'unknown')
            qtr += f"- Guidance: {guidance}\n"
            
            formatted.append(qtr)
        
        return "".join(formatted) if formatted else "No earnings data"
    
    def _structured_to_result(self, analysis: "AIAnalysisResponse", model: str = "") -> Dict:
        """Convert a validated AIAnalysisResponse into the legacy result dict."""
        g = analysis.price_guidance
        return {
            "confidence": analysis.conviction_0_100,
            "report": analysis.narrative,
            "key_drivers": analysis.key_drivers,
            "risks": analysis.risks,
            "time_horizon": analysis.time_horizon,
            "entry_price_low": g.entry_normal_low,
            "entry_price_high": g.entry_normal_high,
            "conservative_entry_low": g.entry_conservative_low,
            "conservative_entry_high": g.entry_conservative_high,
            "target_price_base": analysis.targets.base,
            "target_price_bull": analysis.targets.bull,
            "target_price_bear": analysis.targets.bear,
            # AI Conviction fields (NEW) — passed through for app.py to build AIConviction
            "conviction_0_100": analysis.conviction_0_100,
            "conviction_label": analysis.conviction_label,
            "conviction_drivers": analysis.conviction_drivers,
            "conviction_risks": analysis.conviction_risks,
            "overlay_note": analysis.overlay_note or analysis.notes_on_overlay,
            "overlay_used": analysis.overlay_used,
            "_structured": True,
            "_model": model,
        }

    def _parse_analysis(self, response_text: str) -> Dict:
        """
        Parse Gemini's response to extract structured data.

        NOTE: This is intentionally permissive (Gemini may vary formatting).
        We keep the original output fields your app expects.
        """

        result = {
            'confidence': 50,  # Default
            'report': response_text,
            'key_drivers': [],
            'risks': [],
            'time_horizon': 'Unknown',
            'entry_price_low': None,
            'entry_price_high': None,
            'conservative_entry_low': None,
            'conservative_entry_high': None,
            'target_price_base': None,
            'target_price_bull': None,
            'target_price_bear': None,
        }

        lines = response_text.split('\n') if response_text else []

        # --- Pass 1: single-line fields ---
        for line in lines:
            line_upper = line.upper()

            # Extract confidence score
            if 'CONFIDENCE SCORE:' in line_upper:
                try:
                    import re
                    numbers = re.findall(r'\d+', line)
                    if numbers:
                        confidence = int(numbers[0])
                        result['confidence'] = max(0, min(100, confidence))
                except Exception:
                    pass

            # Extract entry price range
            if 'ENTRY PRICE RANGE:' in line_upper:
                try:
                    import re
                    numbers = re.findall(r'\$?(\d+\.?\d*)', line)
                    if len(numbers) >= 2:
                        result['entry_price_low'] = float(numbers[0])
                        result['entry_price_high'] = float(numbers[1])
                except Exception:
                    pass

            # Extract conservative entry
            if 'CONSERVATIVE ENTRY:' in line_upper:
                try:
                    import re
                    numbers = re.findall(r'\$?(\d+\.?\d*)', line)
                    if len(numbers) >= 2:
                        result['conservative_entry_low'] = float(numbers[0])
                        result['conservative_entry_high'] = float(numbers[1])
                except Exception:
                    pass

            # Extract target prices (updated to match new format)
            if 'TARGET PRICE - BASE CASE:' in line_upper or 'TARGET PRICE (BASE):' in line_upper:
                try:
                    import re
                    nums = re.findall(r'\$?(\d+\.?\d*)', line)
                    if nums:
                        result['target_price_base'] = float(nums[0])
                except Exception:
                    pass

            if 'TARGET PRICE - BULL CASE:' in line_upper or 'TARGET PRICE (BULL):' in line_upper:
                try:
                    import re
                    nums = re.findall(r'\$?(\d+\.?\d*)', line)
                    if nums:
                        result['target_price_bull'] = float(nums[0])
                except Exception:
                    pass

            if 'TARGET PRICE - BEAR CASE:' in line_upper or 'TARGET PRICE (BEAR):' in line_upper:
                try:
                    import re
                    nums = re.findall(r'\$?(\d+\.?\d*)', line)
                    if nums:
                        result['target_price_bear'] = float(nums[0])
                except Exception:
                    pass

            # Extract time horizon
            if 'TIME HORIZON:' in line_upper:
                try:
                    horizon = line.split(':', 1)[1].strip() if ':' in line else 'Unknown'
                    if horizon:
                        result['time_horizon'] = horizon
                except Exception:
                    pass

        # --- Pass 2: key drivers & risks sections ---
        in_drivers = False
        in_risks = False
        for line in lines:
            line_upper = line.upper()

            if 'KEY DRIVERS TO WATCH' in line_upper:
                in_drivers = True
                in_risks = False
                continue
            if 'RISKS:' in line_upper or 'KEY RISKS' in line_upper:
                in_risks = True
                in_drivers = False
                continue

            # section terminators (best-effort)
            if any(x in line_upper for x in ['POSITIONING', 'TIME HORIZON', 'ENTRY PRICE', 'TARGET PRICE']):
                # don't hard-stop time horizon itself; but usually signals section switch
                if 'KEY DRIVERS' not in line_upper and 'RISKS' not in line_upper:
                    in_drivers = False
                    in_risks = False

            if line.strip().startswith('-'):
                item = line.strip().lstrip('-').strip()
                if item:
                    if in_drivers:
                        result['key_drivers'].append(item)
                    elif in_risks:
                        result['risks'].append(item)

        return result
    def _fallback_analysis(self, ticker: str, valuation_data: Dict) -> Dict:
        """Fallback if Gemini fails."""
        spot = valuation_data.get('spot_price', 100)
        
        return {
            'confidence': 50,
            'report': 'Gemini AI analysis unavailable. Using fallback.',
            'key_drivers': ['Market conditions', 'Company fundamentals'],
            'risks': ['Market volatility', 'Execution risk'],
            'time_horizon': 'Medium-term',
            'entry_price_low': spot * 0.97,
            'entry_price_high': spot * 1.03,
            'conservative_entry_low': spot * 0.95,
            'conservative_entry_high': spot * 0.98,
        }


# Global instance
citadel_ai = CitadelAnalystAI() if GENAI_AVAILABLE else None


def analyze_with_ai(
    ticker: str,
    user_stance: str,
    company_data: Dict,
    earnings_data: Dict,
    valuation_data: Dict,
    macro_context: Optional[str] = None,
    extra_info: Optional[str] = None,  # INSIDER INFORMATION (~80% credibility)
) -> Dict:
    """
    Convenience function for AI analysis.
    
    Returns Gemini's expert analysis with confidence score.
    """
    if not citadel_ai:
        # Fallback if Gemini not available
        spot = valuation_data.get('spot_price', 100)
        return {
            'confidence': 50,
            'report': 'Gemini AI not available.',
            'key_drivers': [],
            'risks': [],
            'time_horizon': 'Unknown',
            'entry_price_low': spot * 0.97,
            'entry_price_high': spot * 1.03,
            'conservative_entry_low': spot * 0.95,
            'conservative_entry_high': spot * 0.98,
        }
    
    return citadel_ai.analyze_stock(
        ticker, user_stance, company_data, earnings_data,
        valuation_data, macro_context, extra_info
    )


def ask_ai_question(ticker: str, question: str) -> str:
    """
    Ask follow-up question to the AI analyst.
    Rate limited to 10 questions per minute.
    """
    if not citadel_ai:
        return "Gemini AI not available."
    
    # Check rate limit
    if not _check_rate_limit():
        return ("⏸️ Rate limit reached (10 questions per minute). "
                "Please wait a moment before asking another question.")
    
    try:
        return citadel_ai.ask_question(ticker, question)
    except Exception as e:
        return f"Error: {str(e)}"