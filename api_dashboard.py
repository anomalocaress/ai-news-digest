#!/usr/bin/env python3
"""API Cost Dashboard Generator"""

import json
from pathlib import Path
from api_cost_calculator import get_dashboard_data


def generate_api_dashboard_html() -> str:
    """Generate HTML for API cost dashboard"""

    costs = get_dashboard_data()
    total_jpy = costs.get("total_jpy", 0)
    models = costs.get("models", [])

    # Total cost box
    html = f'''<div class="card">
    <div class="card-title">💰 今月のAPI使用料金</div>
    <div style="margin-bottom: 1.5rem; padding: 1.5rem; background: linear-gradient(135deg, #0f172a, #1e293b); border-radius: 8px; border-left: 4px solid #60a5fa; text-align: center;">
      <div style="font-size: 2.5rem; font-weight: bold; color: #60a5fa;">¥{total_jpy:,}</div>
      <div style="font-size: 0.9rem; color: #94a3b8; margin-top: 0.5rem;">${costs.get('total_usd', 0):.2f} USD</div>
    </div>

    <!-- モデル別料金 -->
    <div style="display: grid; gap: 0.75rem;">'''

    if models:
        for model in models:
            color = model.get("color", "#60a5fa")
            name = model.get("name", "Unknown")
            provider = model.get("provider", "Unknown")
            jpy = model.get("jpy", 0)
            usd = model.get("usd", 0)
            url = model.get("url", "#")

            html += f'''
      <a href="{url}" target="_blank" style="display: flex; align-items: center; justify-content: space-between; padding: 1rem; background: #1e293b; border: 1px solid #334155; border-left: 4px solid {color}; border-radius: 6px; text-decoration: none; color: #e2e8f0; transition: all 0.2s; cursor: pointer;">
        <div>
          <div style="font-weight: 600; color: #e2e8f0; font-size: 0.95rem;">{name}</div>
          <div style="font-size: 0.8rem; color: #94a3b8;">{provider}</div>
        </div>
        <div style="text-align: right;">
          <div style="font-weight: 700; color: {color}; font-size: 1.1rem;">¥{jpy:,}</div>
          <div style="font-size: 0.8rem; color: #64748b;">${usd:.2f} USD</div>
        </div>
      </a>'''
    else:
        html += '''
      <p class="no-data">まだAPI使用データがありません</p>'''

    html += '''
    </div>
  </div>'''

    return html


if __name__ == "__main__":
    print(generate_api_dashboard_html())
