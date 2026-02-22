"""
Trade Dashboard Data Generator
===============================
Creates professional Trade Dashboard metrics for top of report.

Components:
1. Position Overview (spot, target, R/R)
2. Volatility Context (IV rank, implied moves)
3. Liquidity & Quality metrics
"""

from typing import Dict, Optional

class TradeDashboard:
    """Generate Trade Dashboard summary metrics."""
    
    def generate_dashboard(
        self,
        # Position data
        spot: float,
        target_price: float,
        entry_normal_avg: float,
        entry_conservative_avg: float,

        # Volatility data
        iv_rank: float,
        iv_percentile: float,
        implied_move_30d: float,
        hv20_expected: float,
        iv_hv_ratio: float,

        # Liquidity data
        liquidity_grade: str,
        expiry_quality_score: float,
        spread_pct: float,

        # Confidence — Official Confidence (deterministic, drives risk controls)
        confidence: float,

        # AI Conviction — secondary, narrative only, optional
        ai_conviction=None,

    ) -> Dict:
        """
        Generate complete dashboard metrics.
        
        Returns dict with all formatted values ready for display.
        """
        
        # Position Overview calculations
        upside_to_target_pct = ((target_price - spot) / spot) * 100
        downside_to_normal_pct = ((entry_normal_avg - spot) / spot) * 100
        downside_to_cons_pct = ((entry_conservative_avg - spot) / spot) * 100
        
        # R/R calculations
        current_upside = target_price - spot
        current_downside = spot - entry_conservative_avg
        current_rr = current_upside / current_downside if current_downside > 0 else 0
        
        entry_upside = target_price - entry_normal_avg
        entry_downside = entry_normal_avg - entry_conservative_avg
        entry_rr = entry_upside / entry_downside if entry_downside > 0 else 0
        
        # IV assessment
        if iv_hv_ratio < 0.90:
            iv_signal = "Underpricing signal 🟢"
        elif iv_hv_ratio < 1.10:
            iv_signal = "Fair pricing"
        else:
            iv_signal = "Overpricing signal 🔴"
        
        # IV rank assessment
        if iv_rank < 30:
            iv_rank_label = "Low (Good for buying)"
        elif iv_rank < 70:
            iv_rank_label = "Moderate"
        else:
            iv_rank_label = "High (Good for selling)"
        
        # Liquidity assessment
        if spread_pct <= 0.02:
            spread_label = "Excellent"
        elif spread_pct <= 0.05:
            spread_label = "Good"
        elif spread_pct <= 0.10:
            spread_label = "Acceptable"
        else:
            spread_label = "Wide (caution)"
        
        return {
            # Position Overview
            'spot': round(spot, 2),
            'target': round(target_price, 2),
            'upside_to_target_pct': round(upside_to_target_pct, 1),
            'entry_normal_avg': round(entry_normal_avg, 2),
            'entry_conservative_avg': round(entry_conservative_avg, 2),
            'downside_to_normal_pct': round(downside_to_normal_pct, 1),
            'downside_to_cons_pct': round(downside_to_cons_pct, 1),
            'current_rr': round(current_rr, 2),
            'entry_rr': round(entry_rr, 2),
            'rr_favorable': entry_rr > current_rr,
            
            # Volatility Context
            'iv_rank': round(iv_rank, 1),
            'iv_rank_label': iv_rank_label,
            'iv_percentile': round(iv_percentile, 1),
            'implied_move_30d': round(implied_move_30d, 1),
            'hv20_expected': round(hv20_expected, 1),
            'iv_hv_ratio': round(iv_hv_ratio, 2),
            'iv_signal': iv_signal,
            
            # Liquidity & Quality
            'liquidity_grade': liquidity_grade,
            'expiry_quality_score': round(expiry_quality_score, 3),
            'spread_pct': round(spread_pct, 2),
            'spread_label': spread_label,
            
            # Overall
            'confidence': round(confidence, 1),

            # AI Conviction secondary display (if available)
            # ai_conviction is an AIConviction object or None
            'ai_conviction_available': (
                ai_conviction is not None
                and getattr(ai_conviction, 'available', False)
            ),
            'ai_conviction_score': (
                getattr(ai_conviction, 'score_0_100', None)
                if ai_conviction and getattr(ai_conviction, 'available', False)
                else None
            ),
            'ai_conviction_label': (
                getattr(ai_conviction, 'label', None)
                if ai_conviction and getattr(ai_conviction, 'available', False)
                else None
            ),
        }