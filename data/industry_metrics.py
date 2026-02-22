"""
Industry Metrics Module (Memory/Semiconductor)
===============================================
Provides sector-specific context for semiconductor stocks.

For Memory (DRAM/NAND/HBM):
- HBM TAM growth and market share
- DRAM/NAND pricing trends
- Capex discipline analysis
- Inventory cycle assessment

This is the EDGE - institutional analysts track these metrics religiously.
"""

from typing import Dict, Optional
from datetime import datetime

class IndustryMetrics:
    """
    Semiconductor industry-specific metrics and analysis.
    
    Focuses on Memory sector (DRAM, NAND, HBM) but extensible to other semis.
    """
    
    # Static data (would be API-driven in production)
    # These are realistic 2025-2026 estimates
    MEMORY_DATA = {
        'hbm': {
            'tam_2024': 15.0,  # $15B TAM
            'tam_2027': 50.0,  # $50B TAM
            'cagr': 0.85,  # 85% CAGR
            'market_share': {
                'SK_Hynix': 0.75,
                'Samsung': 0.10,
                'Micron': 0.15,
            },
            'constraints': 'Packaging capacity (CoWoS, HBM test)',
        },
        'dram': {
            'market_size': 100.0,  # $100B market
            'pricing_trend_qoq': 0.12,  # +12% QoQ
            'pricing_trend_yoy': 0.28,  # +28% YoY
            'utilization': 0.85,  # 85% utilization
            'supply_discipline': 'Improving - rational capex',
        },
        'nand': {
            'market_size': 60.0,  # $60B market
            'pricing_trend_qoq': 0.08,  # +8% QoQ
            'pricing_trend_yoy': 0.15,  # +15% YoY
            'utilization': 0.80,  # 80% utilization
            'supply_discipline': 'Moderate - some capacity adds',
        },
        'inventory_cycle': {
            'stage': 'Early Recovery',
            'channel_inventory_weeks': 8,
            'status': 'Destocking complete, demand improving',
        }
    }
    
    CAPEX_DATA = {
        'MU': {
            'fy2025': 8.5,  # $8.5B
            'fy2024': 7.2,
            'focus': 'HBM capacity + node transitions',
        },
        'Samsung': {
            'fy2025': 22.0,  # $22B
            'fy2024': 25.0,
            'focus': 'DRAM/NAND + foundry',
        },
        'SK_Hynix': {
            'fy2025': 12.0,  # $12B
            'fy2024': 10.5,
            'focus': 'HBM leadership + DRAM',
        },
    }
    
    def get_memory_context(
        self,
        ticker: str,
        current_price: float,
        company_info: Optional[Dict] = None,
    ) -> Dict:
        """
        Get comprehensive memory industry context.
        
        Returns dict with:
        - HBM dynamics
        - DRAM/NAND pricing
        - Capex analysis
        - Inventory cycle
        - Competitive positioning
        """
        
        # HBM analysis
        hbm = self.MEMORY_DATA['hbm']
        hbm_analysis = {
            'tam_2024': hbm['tam_2024'],
            'tam_2027': hbm['tam_2027'],
            'cagr_pct': hbm['cagr'] * 100,
            'market_share': hbm['market_share'],
            'ticker_share': hbm['market_share'].get(self._map_ticker_to_company(ticker), 0) * 100,
            'growth_driver': 'AI accelerators (NVIDIA H100/B200, AMD MI300)',
            'constraints': hbm['constraints'],
            'signal': '🔥 Massive TAM expansion benefits all players',
        }
        
        # DRAM pricing
        dram = self.MEMORY_DATA['dram']
        dram_analysis = {
            'market_size_bn': dram['market_size'],
            'pricing_qoq_pct': dram['pricing_trend_qoq'] * 100,
            'pricing_yoy_pct': dram['pricing_trend_yoy'] * 100,
            'utilization_pct': dram['utilization'] * 100,
            'supply_discipline': dram['supply_discipline'],
            'signal': '📈 Pricing power returning' if dram['pricing_trend_qoq'] > 0 else '📉 Pricing under pressure',
        }
        
        # NAND pricing
        nand = self.MEMORY_DATA['nand']
        nand_analysis = {
            'market_size_bn': nand['market_size'],
            'pricing_qoq_pct': nand['pricing_trend_qoq'] * 100,
            'pricing_yoy_pct': nand['pricing_trend_yoy'] * 100,
            'utilization_pct': nand['utilization'] * 100,
            'supply_discipline': nand['supply_discipline'],
        }
        
        # Capex discipline
        capex = self.CAPEX_DATA.get(ticker, {})
        capex_analysis = self._analyze_capex(ticker, capex)
        
        # Inventory cycle
        inventory = self.MEMORY_DATA['inventory_cycle']
        inventory_analysis = {
            'stage': inventory['stage'],
            'channel_inventory_weeks': inventory['channel_inventory_weeks'],
            'status': inventory['status'],
            'signal': self._get_cycle_signal(inventory['stage']),
        }
        
        # Competitive positioning
        positioning = self._analyze_positioning(
            ticker, hbm['market_share'], dram['pricing_trend_qoq']
        )
        
        return {
            'hbm': hbm_analysis,
            'dram': dram_analysis,
            'nand': nand_analysis,
            'capex': capex_analysis,
            'inventory_cycle': inventory_analysis,
            'positioning': positioning,
            'overall_signal': self._get_overall_signal(
                dram['pricing_trend_qoq'],
                inventory['stage'],
                capex.get('fy2025', 0),
            ),
        }
    
    def _map_ticker_to_company(self, ticker: str) -> str:
        """Map ticker to company name for data lookup."""
        mapping = {
            'MU': 'Micron',
            'WDC': 'Western_Digital',
            'STX': 'Seagate',
            '005930.KS': 'Samsung',
            '000660.KS': 'SK_Hynix',
        }
        return mapping.get(ticker, ticker)
    
    def _analyze_capex(self, ticker: str, capex: Dict) -> Dict:
        """Analyze capex discipline relative to peers."""
        if not capex:
            return {
                'ticker_capex_bn': None,
                'positioning': 'Data unavailable',
            }
        
        fy2025 = capex.get('fy2025', 0)
        fy2024 = capex.get('fy2024', fy2025)
        yoy_change_pct = ((fy2025 - fy2024) / fy2024 * 100) if fy2024 > 0 else 0
        
        # Compare to peers
        all_capex = [v.get('fy2025', 0) for v in self.CAPEX_DATA.values()]
        avg_capex = sum(all_capex) / len(all_capex) if all_capex else 0
        
        relative_position = fy2025 / avg_capex if avg_capex > 0 else 1.0
        
        if relative_position < 0.6:
            discipline = 'Very disciplined (supports pricing) ✅'
        elif relative_position < 0.9:
            discipline = 'Disciplined (favorable) 🟢'
        elif relative_position < 1.2:
            discipline = 'In line with peers'
        else:
            discipline = 'Aggressive (risk to pricing) ⚠️'
        
        return {
            'ticker': ticker,
            'fy2025_bn': fy2025,
            'fy2024_bn': fy2024,
            'yoy_change_pct': round(yoy_change_pct, 1),
            'focus': capex.get('focus', 'General capacity'),
            'relative_to_peers': relative_position,
            'discipline_assessment': discipline,
            'peer_comparison': {
                k: v.get('fy2025', 0)
                for k, v in self.CAPEX_DATA.items()
            },
        }
    
    def _get_cycle_signal(self, stage: str) -> str:
        """Get signal based on inventory cycle stage."""
        signals = {
            'Trough': '🟢 Best entry point - bottoming',
            'Early Recovery': '🟢 Positive - demand improving',
            'Mid Recovery': '🟡 Neutral - ongoing recovery',
            'Late Recovery': '🟡 Caution - cycle maturing',
            'Peak': '🔴 Risk - cycle peaking',
            'Early Downturn': '🔴 Negative - softening',
            'Mid Downturn': '🔴 Avoid - in downcycle',
            'Late Downturn': '🟡 Watch - approaching trough',
        }
        return signals.get(stage, 'Unknown')
    
    def _analyze_positioning(
        self,
        ticker: str,
        hbm_shares: Dict,
        dram_pricing_trend: float,
    ) -> Dict:
        """Analyze competitive positioning."""
        company = self._map_ticker_to_company(ticker)
        hbm_share = hbm_shares.get(company, 0) * 100
        
        # Assess HBM positioning
        if hbm_share > 50:
            hbm_position = 'Leader - strong pricing power'
        elif hbm_share > 20:
            hbm_position = 'Growing player - share gains opportunity'
        elif hbm_share > 5:
            hbm_position = 'Emerging participant - execution risk'
        else:
            hbm_position = 'Minimal exposure - missing AI opportunity'
        
        # Overall positioning
        if dram_pricing_trend > 0.10 and hbm_share > 10:
            overall = '🚀 Strong - pricing power + HBM exposure'
        elif dram_pricing_trend > 0.05:
            overall = '🟢 Favorable - pricing improving'
        elif dram_pricing_trend < 0:
            overall = '🔴 Challenging - pricing pressure'
        else:
            overall = '🟡 Neutral - stable pricing'
        
        return {
            'hbm_share_pct': round(hbm_share, 1),
            'hbm_position': hbm_position,
            'overall_position': overall,
        }
    
    def _get_overall_signal(
        self,
        pricing_trend: float,
        cycle_stage: str,
        capex: float,
    ) -> str:
        """Get overall industry signal."""
        signals = []
        
        if pricing_trend > 0.10:
            signals.append('Strong pricing momentum')
        elif pricing_trend > 0:
            signals.append('Pricing improving')
        else:
            signals.append('Pricing pressure')
        
        if cycle_stage in ['Trough', 'Early Recovery']:
            signals.append('favorable cycle stage')
        elif cycle_stage in ['Peak', 'Early Downturn']:
            signals.append('cycle risk')
        
        if capex < 10:
            signals.append('disciplined supply')
        
        # Combine
        positive_count = sum([
            pricing_trend > 0.05,
            cycle_stage in ['Trough', 'Early Recovery', 'Mid Recovery'],
            capex < 12,
        ])
        
        if positive_count >= 3:
            return '🚀 Very Bullish: ' + '; '.join(signals)
        elif positive_count >= 2:
            return '🟢 Bullish: ' + '; '.join(signals)
        elif positive_count >= 1:
            return '🟡 Mixed: ' + '; '.join(signals)
        else:
            return '🔴 Bearish: ' + '; '.join(signals)