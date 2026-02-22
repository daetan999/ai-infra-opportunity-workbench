"""
Reverse DCF Module
==================
Calculate implied market expectations to justify current price.

Instead of "DCF says $130 but stock is $420 - disconnected"
Show: "To justify $420, market expects: X% revenue CAGR, Y% margins, Z% HBM mix"

This is how JPMorgan equity research analyzes valuation gaps.
"""

from typing import Dict, Optional
import math

class ReverseDCF:
    """
    Calculate implied expectations embedded in current stock price.
    
    For memory/semiconductor stocks, focuses on:
    - Revenue growth (driven by bit demand + pricing)
    - Margin expansion (driven by mix shift to HBM)
    - Product mix evolution (DRAM/NAND/HBM)
    """
    
    def __init__(self):
        self.risk_free_rate = 0.05  # 5% risk-free
        self.market_risk_premium = 0.07  # 7% equity premium
    
    def analyze(
        self,
        # Current data
        current_price: float,
        current_revenue: float,
        current_margin: float,
        current_fcf_margin: float,
        shares_outstanding: float,
        
        # DCF model assumptions
        dcf_intrinsic: float,
        dcf_assumptions: Dict,  # {'revenue_cagr': 0.12, 'terminal_growth': 0.02, ...}
        
        # Industry context (for semiconductors)
        current_hbm_mix: Optional[float] = None,  # % of revenue from HBM
        hbm_tam_growth: Optional[float] = None,  # Expected HBM TAM CAGR
        
        # Company specifics
        beta: float = 1.5,
        
    ) -> Dict:
        """
        Reverse engineer what market is pricing in.
        
        Returns dict with:
        - implied_revenue_cagr: What growth is needed
        - implied_margin: What margins are needed
        - implied_hbm_mix: What HBM contribution is needed
        - reasonableness_score: 0-10 scale
        - assessment: Text explanation
        """
        
        # Calculate required WACC
        cost_of_equity = self.risk_free_rate + beta * self.market_risk_premium
        wacc = cost_of_equity  # Simplified (assuming no debt)
        
        # Market cap implied by current price
        market_cap = current_price * shares_outstanding
        
        # Solve for implied revenue CAGR (holding other assumptions constant)
        implied_revenue_cagr = self._solve_revenue_cagr(
            target_market_cap=market_cap,
            current_revenue=current_revenue,
            current_margin=current_fcf_margin,
            wacc=wacc,
            terminal_growth=dcf_assumptions.get('terminal_growth', 0.02),
            projection_years=5,
        )
        
        # Solve for implied margin (holding revenue growth constant)
        implied_margin = self._solve_margin(
            target_market_cap=market_cap,
            current_revenue=current_revenue,
            revenue_cagr=dcf_assumptions.get('revenue_cagr', 0.12),
            wacc=wacc,
            terminal_growth=dcf_assumptions.get('terminal_growth', 0.02),
            projection_years=5,
        )
        
        # For semiconductor: solve for HBM mix (if applicable)
        implied_hbm_mix = None
        if current_hbm_mix is not None and hbm_tam_growth is not None:
            implied_hbm_mix = self._solve_hbm_mix(
                target_market_cap=market_cap,
                current_revenue=current_revenue,
                current_hbm_mix=current_hbm_mix,
                hbm_tam_growth=hbm_tam_growth,
                revenue_cagr=dcf_assumptions.get('revenue_cagr', 0.12),
                wacc=wacc,
            )
        
        # Compare to DCF assumptions
        dcf_revenue_cagr = dcf_assumptions.get('revenue_cagr', 0.12)
        dcf_margin = dcf_assumptions.get('fcf_margin', current_fcf_margin)
        
        revenue_gap_pct = ((implied_revenue_cagr - dcf_revenue_cagr) / dcf_revenue_cagr) * 100 if dcf_revenue_cagr > 0 else 0
        margin_gap_pct = ((implied_margin - dcf_margin) / dcf_margin) * 100 if dcf_margin > 0 else 0
        
        # Assess reasonableness
        reasonableness = self._assess_reasonableness(
            implied_revenue_cagr=implied_revenue_cagr,
            implied_margin=implied_margin,
            implied_hbm_mix=implied_hbm_mix,
            current_margin=current_margin,
            current_hbm_mix=current_hbm_mix,
            hbm_tam_growth=hbm_tam_growth,
        )
        
        # Generate assessment
        assessment = self._generate_assessment(
            implied_revenue_cagr=implied_revenue_cagr,
            implied_margin=implied_margin,
            implied_hbm_mix=implied_hbm_mix,
            dcf_revenue_cagr=dcf_revenue_cagr,
            dcf_margin=dcf_margin,
            current_hbm_mix=current_hbm_mix,
            reasonableness=reasonableness,
        )
        
        return {
            'current_price': current_price,
            'dcf_intrinsic': dcf_intrinsic,
            'price_premium_pct': ((current_price - dcf_intrinsic) / dcf_intrinsic * 100) if dcf_intrinsic > 0 else 0,
            
            'implied_revenue_cagr': round(implied_revenue_cagr * 100, 1),
            'dcf_revenue_cagr': round(dcf_revenue_cagr * 100, 1),
            'revenue_gap_pct': round(revenue_gap_pct, 1),
            
            'implied_margin': round(implied_margin * 100, 1),
            'current_margin': round(current_margin * 100, 1),
            'dcf_margin': round(dcf_margin * 100, 1),
            'margin_gap_pct': round(margin_gap_pct, 1),
            
            'implied_hbm_mix': round(implied_hbm_mix * 100, 1) if implied_hbm_mix else None,
            'current_hbm_mix': round(current_hbm_mix * 100, 1) if current_hbm_mix else None,
            
            'reasonableness_score': reasonableness,
            'reasonableness_01': round(max(0.0, min(1.0, reasonableness / 10.0)), 4),
            'assessment': assessment,
        }
    
    def _solve_revenue_cagr(
        self,
        target_market_cap: float,
        current_revenue: float,
        current_margin: float,
        wacc: float,
        terminal_growth: float,
        projection_years: int = 5,
    ) -> float:
        """
        Solve for revenue CAGR that justifies target market cap.
        
        Uses iterative search (binary search).
        """
        # Binary search for CAGR
        low, high = 0.0, 0.50  # 0% to 50% CAGR
        tolerance = 0.001
        max_iterations = 50
        
        for _ in range(max_iterations):
            mid = (low + high) / 2
            
            # Calculate market cap with this CAGR
            calc_market_cap = self._calculate_market_cap(
                revenue=current_revenue,
                revenue_cagr=mid,
                fcf_margin=current_margin,
                wacc=wacc,
                terminal_growth=terminal_growth,
                years=projection_years,
            )
            
            if abs(calc_market_cap - target_market_cap) / target_market_cap < tolerance:
                return mid
            
            if calc_market_cap < target_market_cap:
                low = mid
            else:
                high = mid
        
        return mid
    
    def _solve_margin(
        self,
        target_market_cap: float,
        current_revenue: float,
        revenue_cagr: float,
        wacc: float,
        terminal_growth: float,
        projection_years: int = 5,
    ) -> float:
        """Solve for FCF margin that justifies target market cap."""
        low, high = 0.0, 0.60  # 0% to 60% margin
        tolerance = 0.001
        max_iterations = 50
        
        for _ in range(max_iterations):
            mid = (low + high) / 2
            
            calc_market_cap = self._calculate_market_cap(
                revenue=current_revenue,
                revenue_cagr=revenue_cagr,
                fcf_margin=mid,
                wacc=wacc,
                terminal_growth=terminal_growth,
                years=projection_years,
            )
            
            if abs(calc_market_cap - target_market_cap) / target_market_cap < tolerance:
                return mid
            
            if calc_market_cap < target_market_cap:
                low = mid
            else:
                high = mid
        
        return mid
    
    def _solve_hbm_mix(
        self,
        target_market_cap: float,
        current_revenue: float,
        current_hbm_mix: float,
        hbm_tam_growth: float,
        revenue_cagr: float,
        wacc: float,
    ) -> float:
        """
        Solve for HBM revenue mix needed.
        
        Assumes HBM has higher margins than traditional DRAM/NAND.
        """
        # For memory: HBM margins ~50%, DRAM/NAND margins ~35%
        hbm_margin = 0.50
        traditional_margin = 0.35
        
        # Solve for what HBM mix gives required blended margin
        # This is simplified - real analysis would model market share dynamics
        
        low, high = 0.0, 1.0
        tolerance = 0.01
        max_iterations = 30
        
        for _ in range(max_iterations):
            mid = (low + high) / 2
            
            # Blended margin = HBM_mix * HBM_margin + (1-HBM_mix) * traditional_margin
            blended_margin = mid * hbm_margin + (1 - mid) * traditional_margin
            
            calc_market_cap = self._calculate_market_cap(
                revenue=current_revenue,
                revenue_cagr=revenue_cagr,
                fcf_margin=blended_margin,
                wacc=wacc,
                terminal_growth=0.02,
                years=5,
            )
            
            if abs(calc_market_cap - target_market_cap) / target_market_cap < tolerance:
                return mid
            
            if calc_market_cap < target_market_cap:
                low = mid
            else:
                high = mid
        
        return mid
    
    def _calculate_market_cap(
        self,
        revenue: float,
        revenue_cagr: float,
        fcf_margin: float,
        wacc: float,
        terminal_growth: float,
        years: int = 5,
    ) -> float:
        """
        Calculate DCF market cap given assumptions.
        
        Simple DCF: PV of FCF + Terminal Value
        """
        fcfs = []
        for year in range(1, years + 1):
            year_revenue = revenue * ((1 + revenue_cagr) ** year)
            year_fcf = year_revenue * fcf_margin
            pv = year_fcf / ((1 + wacc) ** year)
            fcfs.append(pv)
        
        # Terminal value
        terminal_fcf = revenue * ((1 + revenue_cagr) ** years) * fcf_margin * (1 + terminal_growth)
        terminal_value = terminal_fcf / (wacc - terminal_growth)
        pv_terminal = terminal_value / ((1 + wacc) ** years)
        
        total_pv = sum(fcfs) + pv_terminal
        return total_pv
    
    def _assess_reasonableness(
        self,
        implied_revenue_cagr: float,
        implied_margin: float,
        implied_hbm_mix: Optional[float],
        current_margin: float,
        current_hbm_mix: Optional[float],
        hbm_tam_growth: Optional[float],
    ) -> float:
        """
        Assess reasonableness of implied expectations on 0-10 scale.
        
        10 = Very reasonable
        0 = Impossible
        """
        score = 5.0  # Start at neutral
        
        # Revenue CAGR assessment
        if implied_revenue_cagr > 0.40:
            score -= 2.0  # >40% CAGR unrealistic
        elif implied_revenue_cagr > 0.30:
            score -= 1.0  # >30% aggressive
        elif implied_revenue_cagr > 0.20:
            score -= 0.5  # >20% ambitious but possible
        elif implied_revenue_cagr > 0.15:
            score += 0.5  # 15-20% solid
        elif implied_revenue_cagr > 0.10:
            score += 1.0  # 10-15% reasonable
        
        # Margin expansion assessment
        margin_expansion = implied_margin - current_margin
        if margin_expansion > 0.20:
            score -= 2.0  # >20pp expansion unrealistic
        elif margin_expansion > 0.15:
            score -= 1.0  # >15pp difficult
        elif margin_expansion > 0.10:
            score += 0.5  # 10-15pp possible with mix
        elif margin_expansion > 0.05:
            score += 1.0  # 5-10pp reasonable
        
        # HBM mix assessment (if applicable)
        if implied_hbm_mix is not None and current_hbm_mix is not None:
            hbm_increase = implied_hbm_mix - current_hbm_mix
            if hbm_increase > 0.30:
                score -= 1.5  # >30pp share gain very difficult
            elif hbm_increase > 0.20:
                score -= 0.5  # >20pp challenging
            elif hbm_increase > 0.10:
                score += 0.5  # 10-20pp plausible
            
            # Adjust for TAM growth
            if hbm_tam_growth and hbm_tam_growth > 0.50:
                score += 1.0  # High TAM growth supports share gains
        
        return max(0, min(10, score))
    
    def _generate_assessment(
        self,
        implied_revenue_cagr: float,
        implied_margin: float,
        implied_hbm_mix: Optional[float],
        dcf_revenue_cagr: float,
        dcf_margin: float,
        current_hbm_mix: Optional[float],
        reasonableness: float,
    ) -> str:
        """Generate human-readable assessment."""
        assessment = []
        
        # Revenue
        if implied_revenue_cagr > dcf_revenue_cagr * 1.5:
            assessment.append(f"Revenue expectations very aggressive ({implied_revenue_cagr*100:.0f}% vs conservative {dcf_revenue_cagr*100:.0f}%)")
        elif implied_revenue_cagr > dcf_revenue_cagr * 1.2:
            assessment.append(f"Revenue expectations moderately aggressive ({implied_revenue_cagr*100:.0f}% CAGR)")
        else:
            assessment.append(f"Revenue expectations reasonable ({implied_revenue_cagr*100:.0f}% CAGR)")
        
        # Margin
        if implied_margin > dcf_margin * 1.2:
            assessment.append(f"Margin expansion required ({implied_margin*100:.0f}% vs {dcf_margin*100:.0f}%)")
        else:
            assessment.append("Margin assumptions realistic")
        
        # HBM (if applicable)
        if implied_hbm_mix is not None and current_hbm_mix is not None:
            mix_increase = (implied_hbm_mix - current_hbm_mix) * 100
            if mix_increase > 20:
                assessment.append(f"Requires significant HBM share gains (+{mix_increase:.0f}pp)")
            elif mix_increase > 10:
                assessment.append(f"Requires moderate HBM growth (+{mix_increase:.0f}pp)")
        
        # Overall
        if reasonableness >= 7:
            assessment.append("✅ Overall expectations achievable")
        elif reasonableness >= 5:
            assessment.append("⚠️ Expectations ambitious but plausible")
        else:
            assessment.append("🔴 Expectations appear stretched")
        
        return "; ".join(assessment)