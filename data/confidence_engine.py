"""
Institutional-Grade Confidence Engine
=====================================
JPMorgan-level transparent weighted scoring model.
All weights must sum to 100%. No fake confidence scores.
"""

from typing import Dict, Optional, Tuple
import math

class ConfidenceEngine:
    """
    Professional confidence scoring with transparent factor breakdown.
    
    Factors (must sum to 100%):
    - Liquidity Quality: 20%
    - IV vs HV Mispricing: 15%
    - Skew Alignment: 10%
    - DCF Mispricing Magnitude: 20%
    - Macro Regime: 10%
    - Industry Cycle Regime: 10%
    - Technical Alignment: 15%
    """
    
    # Factor weights (must sum to 1.0)
    WEIGHTS = {
        'liquidity_quality': 0.20,
        'iv_vs_hv_mispricing': 0.15,
        'skew_alignment': 0.10,
        'dcf_mispricing_magnitude': 0.20,
        'macro_regime': 0.10,
        'industry_cycle_regime': 0.10,
        'technical_alignment': 0.15,
    }
    
    def __init__(self):
        # Validate weights sum to 1.0
        total = sum(self.WEIGHTS.values())
        assert abs(total - 1.0) < 0.001, f"Weights must sum to 1.0, got {total}"
    
    def compute_confidence(
        self,
        # Mode selection (P0-4: stock vs options)
        mode: str = "options",  # "stock" or "options"
        stock_options_diagnostics: Optional[Dict] = None,  # For stock mode with chain available
        
        # Liquidity data
        spread_pct: Optional[float] = None,
        liquidity_grade: Optional[str] = None,
        oi_total: Optional[float] = None,
        vol_total: Optional[float] = None,
        
        # Volatility data
        iv_rank: Optional[float] = None,
        iv_hv_ratio: Optional[float] = None,
        atm_iv: Optional[float] = None,
        hv20: Optional[float] = None,
        
        # Skew data
        put_skew: Optional[float] = None,
        call_skew: Optional[float] = None,
        skew_shape: Optional[str] = None,
        
        # DCF data
        dcf_intrinsic: Optional[float] = None,
        spot_price: float = 100.0,
        dcf_gap_pct: Optional[float] = None,
        
        # Macro data
        macro_regime: Optional[str] = None,
        
        # Industry data
        industry_cycle: Optional[str] = None,
        
        # Technical data
        atr_bands: Optional[Dict] = None,
        vwap_anchor: Optional[float] = None,
        support_levels: Optional[list] = None,
        
    ) -> Dict:
        """
        Compute confidence score with full transparency.
        
        Returns dict with:
        - total_confidence: 0-100 score
        - factor_scores: individual scores
        - factor_contributions: weighted contributions
        - missing_factors: list of unavailable factors
        - grade: A/B/C/D/F
        """
        
        scores = {}
        contributions = {}
        missing = []
        
        # ============================================================
        # P0-4b FIX: In stock mode, use options-derived diagnostics if available
        # ============================================================
        if mode == "stock" and stock_options_diagnostics and stock_options_diagnostics.get("available"):
            print("📊 Using options-derived diagnostics in stock mode")
            
            # Extract diagnostics
            auto_expiry = stock_options_diagnostics.get('auto_expiry')
            iv_rank_diag = stock_options_diagnostics.get('iv_rank')
            put_call = stock_options_diagnostics.get('put_call')
            atm_iv_diag = stock_options_diagnostics.get('atm_iv')
            implied_vs_forecast = stock_options_diagnostics.get('implied_vs_forecast')
            
            # Override missing values with diagnostics
            if auto_expiry and not spread_pct:
                spread_pct = auto_expiry.get('metrics', {}).get('median_spread')
                liquidity_grade = auto_expiry.get('liq_grade')
                print(f"  ✓ Liquidity from auto_expiry: grade={liquidity_grade}, spread={spread_pct}")
            
            if iv_rank_diag is not None and iv_rank is None:
                iv_rank = iv_rank_diag
                print(f"  ✓ IV rank from diagnostics: {iv_rank}")
            
            if atm_iv_diag is not None and atm_iv is None:
                atm_iv = atm_iv_diag
                print(f"  ✓ ATM IV from diagnostics: {atm_iv}")
            
            if put_call:
                # Could extract put/call metrics but keep simple for now
                pass
        
        # 1. Liquidity Quality (20%)
        liq_score, liq_missing = self._score_liquidity(
            spread_pct, liquidity_grade, oi_total, vol_total
        )
        scores['liquidity_quality'] = liq_score
        contributions['liquidity_quality'] = liq_score * self.WEIGHTS['liquidity_quality']
        if liq_missing:
            missing.extend(liq_missing)
        
        # 2. IV vs HV Mispricing (15%)
        iv_score, iv_missing = self._score_iv_mispricing(
            iv_rank, iv_hv_ratio, atm_iv, hv20
        )
        scores['iv_vs_hv_mispricing'] = iv_score
        contributions['iv_vs_hv_mispricing'] = iv_score * self.WEIGHTS['iv_vs_hv_mispricing']
        if iv_missing:
            missing.extend(iv_missing)
        
        # 3. Skew Alignment (10%)
        skew_score, skew_missing = self._score_skew(
            put_skew, call_skew, skew_shape
        )
        scores['skew_alignment'] = skew_score
        contributions['skew_alignment'] = skew_score * self.WEIGHTS['skew_alignment']
        if skew_missing:
            missing.extend(skew_missing)
        
        # 4. DCF Mispricing Magnitude (20%)
        dcf_score, dcf_missing = self._score_dcf_mispricing(
            dcf_intrinsic, spot_price, dcf_gap_pct
        )
        scores['dcf_mispricing_magnitude'] = dcf_score
        contributions['dcf_mispricing_magnitude'] = dcf_score * self.WEIGHTS['dcf_mispricing_magnitude']
        if dcf_missing:
            missing.extend(dcf_missing)
        
        # 5. Macro Regime (10%)
        macro_score, macro_missing = self._score_macro(macro_regime)
        scores['macro_regime'] = macro_score
        contributions['macro_regime'] = macro_score * self.WEIGHTS['macro_regime']
        if macro_missing:
            missing.extend(macro_missing)
        
        # 6. Industry Cycle Regime (10%)
        industry_score, industry_missing = self._score_industry(industry_cycle)
        scores['industry_cycle_regime'] = industry_score
        contributions['industry_cycle_regime'] = industry_score * self.WEIGHTS['industry_cycle_regime']
        if industry_missing:
            missing.extend(industry_missing)
        
        # 7. Technical Alignment (15%)
        tech_score, tech_missing = self._score_technical(
            atr_bands, vwap_anchor, support_levels, spot_price
        )
        scores['technical_alignment'] = tech_score
        contributions['technical_alignment'] = tech_score * self.WEIGHTS['technical_alignment']
        if tech_missing:
            missing.extend(tech_missing)
        
        # Calculate total
        total_contribution = sum(contributions.values())
        total_confidence = total_contribution * 100  # Convert to 0-100 scale
        
        # Assign grade
        grade = self._assign_grade(total_confidence, len(missing))
        
        # ============================================================
        # P0-5 FIX: Assert no duplicate factor keys, deduplicate if found
        # ============================================================
        seen_factors = set()
        deduped_scores = {}
        deduped_contributions = {}
        
        for factor_name in scores.keys():
            factor_key = factor_name.lower().strip()
            
            if factor_key in seen_factors:
                print(f"⚠️ ASSERTION FAILED: Duplicate factor '{factor_name}' detected!")
                print(f"   Keeping first occurrence, skipping duplicate")
                continue
            
            seen_factors.add(factor_key)
            deduped_scores[factor_name] = scores[factor_name]
            deduped_contributions[factor_name] = contributions[factor_name]
        
        # Use deduplicated versions
        scores = deduped_scores
        contributions = deduped_contributions
        
        # Assert uniqueness
        assert len(scores) == len(set(k.lower() for k in scores.keys())), \
            f"Duplicate factors detected after deduplication!"
        
        return {
            'total_confidence': round(total_confidence, 1),
            'grade': grade,
            'factor_scores': scores,
            'factor_contributions': contributions,
            'factor_weights': self.WEIGHTS,
            'missing_factors': list(set(missing)),
            'explanation': self._generate_explanation(scores, contributions, missing),
        }
    
    def _score_liquidity(self, spread_pct, grade, oi, vol) -> Tuple[float, list]:
        """Score liquidity quality (0-1 scale)."""
        missing = []
        
        if not any([spread_pct, grade, oi, vol]):
            missing.append('liquidity')
            return 0.5, missing  # Neutral if missing
        
        score = 0.0
        count = 0
        
        # Spread score (tighter = better)
        if spread_pct is not None:
            if spread_pct <= 0.02:
                score += 1.0
            elif spread_pct <= 0.05:
                score += 0.8
            elif spread_pct <= 0.10:
                score += 0.5
            else:
                score += 0.2
            count += 1
        
        # Grade score
        if grade:
            grade_scores = {'A': 1.0, 'B': 0.75, 'C': 0.5, 'D': 0.25, 'F': 0.0}
            score += grade_scores.get(grade, 0.5)
            count += 1
        
        # OI score (higher = better)
        if oi is not None:
            if oi > 10000:
                score += 1.0
            elif oi > 5000:
                score += 0.8
            elif oi > 1000:
                score += 0.5
            else:
                score += 0.3
            count += 1
        
        # Volume score
        if vol is not None:
            if vol > 5000:
                score += 1.0
            elif vol > 1000:
                score += 0.8
            elif vol > 500:
                score += 0.5
            else:
                score += 0.3
            count += 1
        
        final_score = score / count if count > 0 else 0.5
        return final_score, missing
    
    def _score_iv_mispricing(self, iv_rank, iv_hv_ratio, atm_iv, hv20) -> Tuple[float, list]:
        """Score IV vs HV mispricing signal (0-1 scale)."""
        missing = []
        
        if iv_hv_ratio is None and (atm_iv is None or hv20 is None):
            missing.append('iv_mispricing')
            return 0.5, missing
        
        # Calculate ratio if not provided
        if iv_hv_ratio is None and atm_iv and hv20:
            iv_hv_ratio = atm_iv / hv20 if hv20 > 0 else 1.0
        
        # Score based on IV/HV ratio
        # < 0.85: Underpriced (good for buying) = high score
        # 0.85-1.15: Fair = medium score
        # > 1.15: Overpriced (bad for buying) = low score
        if iv_hv_ratio < 0.80:
            score = 0.95  # Very underpriced
        elif iv_hv_ratio < 0.90:
            score = 0.85  # Underpriced
        elif iv_hv_ratio < 1.10:
            score = 0.65  # Fair
        elif iv_hv_ratio < 1.20:
            score = 0.45  # Slightly overpriced
        else:
            score = 0.25  # Overpriced
        
        # Adjust for IV rank
        if iv_rank is not None:
            if iv_rank < 30:
                score = min(score + 0.15, 1.0)  # Low IV = buy opportunity
            elif iv_rank > 70:
                score = max(score - 0.15, 0.0)  # High IV = sell opportunity
        
        return score, missing
    
    def _score_skew(self, put_skew, call_skew, shape) -> Tuple[float, list]:
        """Score skew alignment (0-1 scale)."""
        missing = []
        
        if not any([put_skew, call_skew, shape]):
            missing.append('skew')
            return 0.5, missing
        
        # For bullish stance: want cheap calls, expensive puts
        # Put skew > 0 and call skew < 0 = favorable
        score = 0.5  # Neutral base
        
        if put_skew is not None and call_skew is not None:
            # Ideal: put skew positive (expensive puts), call skew negative (cheap calls)
            if put_skew > 0.05 and call_skew < -0.02:
                score = 0.9  # Very favorable
            elif put_skew > 0.03:
                score = 0.75  # Favorable
            elif abs(put_skew) < 0.02 and abs(call_skew) < 0.02:
                score = 0.6  # Flat (neutral)
            else:
                score = 0.4  # Unfavorable
        
        return score, missing
    
    def _score_dcf_mispricing(self, dcf, spot, gap_pct) -> Tuple[float, list]:
        """Score DCF mispricing magnitude (0-1 scale)."""
        missing = []
        
        if dcf is None or dcf <= 0:
            missing.append('dcf')
            return 0.5, missing
        
        # Calculate gap if not provided
        if gap_pct is None:
            gap_pct = ((spot - dcf) / dcf) * 100
        
        # Score based on gap magnitude and direction
        # For bullish: negative gap (undervalued) = high score
        # Large gap (>30%) = unreliable DCF = medium score
        gap_abs = abs(gap_pct)
        
        if gap_abs > 50:
            score = 0.5  # DCF too disconnected from reality
        elif gap_pct < -20:  # 20%+ undervalued
            score = 0.85
        elif gap_pct < -10:  # 10-20% undervalued
            score = 0.75
        elif gap_pct < 0:  # Slightly undervalued
            score = 0.65
        elif gap_pct < 10:  # Slightly overvalued
            score = 0.55
        elif gap_pct < 20:  # Moderately overvalued
            score = 0.4
        else:  # Significantly overvalued
            score = 0.25
        
        return score, missing
    
    def _score_macro(self, regime) -> Tuple[float, list]:
        """Score macro regime (0-1 scale)."""
        missing = []
        
        if not regime:
            missing.append('macro_regime')
            return 0.5, missing
        
        regime_scores = {
            'Risk On': 0.85,
            'Risk-On': 0.85,
            'Neutral': 0.6,
            'Risk Off': 0.35,
            'Risk-Off': 0.35,
        }
        
        score = regime_scores.get(regime, 0.5)
        return score, missing
    
    def _score_industry(self, cycle) -> Tuple[float, list]:
        """Score industry cycle (0-1 scale)."""
        missing = []
        
        if not cycle:
            missing.append('industry_cycle')
            return 0.5, missing
        
        cycle_scores = {
            'Early Recovery': 0.85,
            'Mid Recovery': 0.75,
            'Late Recovery': 0.65,
            'Peak': 0.55,
            'Early Downturn': 0.4,
            'Mid Downturn': 0.3,
            'Late Downturn': 0.35,
            'Trough': 0.75,  # Good entry point
        }
        
        score = cycle_scores.get(cycle, 0.5)
        return score, missing
    
    def _score_technical(self, atr_bands, vwap, supports, spot) -> Tuple[float, list]:
        """Score technical alignment (0-1 scale)."""
        missing = []
        
        if not any([atr_bands, vwap, supports]):
            missing.append('technical')
            return 0.5, missing
        
        score = 0.0
        count = 0
        
        # ATR band alignment
        if atr_bands and spot:
            if 'primary' in atr_bands:
                low, high = atr_bands['primary']
                if low <= spot <= high:
                    score += 0.8  # Within primary band
                elif spot < low:
                    score += 0.6  # Below band (good entry)
                else:
                    score += 0.4  # Above band (extended)
                count += 1

        # Defensive: allow vwap to be dict (e.g., anchored_vwap payload)
        if isinstance(vwap, dict):
            vwap_val = None
            for k in ("vwap", "anchored_vwap", "value", "price"):
                if vwap.get(k) is not None:
                    try:
                        vwap_val = float(vwap.get(k))
                        break
                    except Exception:
                        pass
            vwap = vwap_val
        
        # VWAP alignment
        if vwap and spot:
            if spot > vwap * 1.05:
                score += 0.6  # Above VWAP (strong)
            elif spot > vwap:
                score += 0.7  # Slightly above (good)
            elif spot > vwap * 0.95:
                score += 0.8  # At VWAP (ideal)
            else:
                score += 0.5  # Below VWAP (weak)
            count += 1
        
        # Support level alignment
        if supports and spot:
            nearest_support = min(supports, key=lambda x: abs(x - spot))
            distance = (spot - nearest_support) / spot
            if distance < 0.02:
                score += 0.9  # At support (good entry)
            elif distance < 0.05:
                score += 0.7  # Near support
            else:
                score += 0.5  # Away from support
            count += 1
        
        final_score = score / count if count > 0 else 0.5
        return final_score, missing
    
    def _assign_grade(self, confidence, num_missing) -> str:
        """Assign letter grade based on confidence and completeness."""
        # Penalize for missing data
        penalty = num_missing * 5  # 5 points per missing factor
        adjusted = confidence - penalty
        
        # EXPERT FIX: Updated grade mapping (70% = B-)
        if adjusted >= 90:
            return 'A+'
        elif adjusted >= 85:
            return 'A'
        elif adjusted >= 80:
            return 'A-'
        elif adjusted >= 75:
            return 'B+'
        elif adjusted >= 70:
            return 'B'
        elif adjusted >= 65:
            return 'B-'  # FIX: Was 'C' before
        elif adjusted >= 60:
            return 'C+'
        elif adjusted >= 55:
            return 'C'
        elif adjusted >= 50:
            return 'C-'
        elif adjusted >= 45:
            return 'D'
        else:
            return 'F'
    
    def _generate_explanation(self, scores, contributions, missing) -> str:
        """Generate human-readable explanation."""
        top_factors = sorted(
            contributions.items(),
            key=lambda x: x[1],
            reverse=True
        )[:3]
        
        explanation = "Confidence driven by: "
        explanation += ", ".join([
            f"{factor.replace('_', ' ').title()} ({contrib*100:.1f} pts)"
            for factor, contrib in top_factors
        ])
        
        if missing:
            explanation += f". Missing: {', '.join(missing)}"
        
        return explanation