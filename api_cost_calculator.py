#!/usr/bin/env python3
"""API Cost Calculator - Calculate costs for all used APIs"""

from datetime import datetime
from pathlib import Path
from typing import Dict, List
import json

# Exchange rate JPY per USD (approximate)
JPY_PER_USD = 150

# API Pricing (as of 2026)
PRICING = {
    "anthropic": {
        "claude-haiku-4-5-20251001": {
            "input_per_mtok": 0.80,  # $0.80 per million input tokens
            "output_per_mtok": 4.00,  # $4 per million output tokens
            "display_name": "Claude Haiku",
            "color": "#8B5CF6"
        },
        "claude-3-5-sonnet-20241022": {
            "input_per_mtok": 3.00,
            "output_per_mtok": 15.00,
            "display_name": "Claude 3.5 Sonnet",
            "color": "#06B6D4"
        },
        "claude-opus-4-1-20250805": {
            "input_per_mtok": 15.00,
            "output_per_mtok": 75.00,
            "display_name": "Claude Opus",
            "color": "#EC4899"
        }
    },
    "google": {
        "texttospeech": {
            "neural2_per_mchars": 16.00,  # $16 per million characters
            "display_name": "Google Cloud Text-to-Speech (Neural2)",
            "color": "#F59E0B"
        }
    },
    "openai": {
        "tts-1-hd": {
            "cost_per_minute": 0.30,  # $0.30 per minute
            "display_name": "OpenAI TTS (tts-1-hd)",
            "color": "#10B981"
        }
    }
}

REPO_DIR = Path(__file__).parent
USAGE_FILE = REPO_DIR / ".api-usage.json"
COSTS_FILE = REPO_DIR / ".api-costs.json"
SUBSCRIPTION_FILE = REPO_DIR / ".claude-subscription.json"


def load_subscription_config() -> Dict:
    """Load Claude subscription configuration"""
    if SUBSCRIPTION_FILE.exists():
        try:
            with open(SUBSCRIPTION_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {
                "subscription_plan": {
                    "name": "Claude Code (Pro)",
                    "monthly_usd": 20.00,
                    "description": "Claude Code Pro monthly subscription"
                }
            }
    return {
        "subscription_plan": {
            "name": "Claude Code (Pro)",
            "monthly_usd": 20.00,
            "description": "Claude Code Pro monthly subscription"
        }
    }


def load_usage_data() -> Dict:
    """Load API usage data"""
    if USAGE_FILE.exists():
        try:
            with open(USAGE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {"anthropic": {}, "google": {}, "openai": {}}
    return {"anthropic": {}, "google": {}, "openai": {}}


def save_usage_data(data: Dict):
    """Save API usage data"""
    with open(USAGE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def record_anthropic_usage(model: str, input_tokens: int, output_tokens: int, purpose: str = "Unknown"):
    """Record Anthropic API usage with purpose/task description"""
    usage = load_usage_data()

    if model not in usage["anthropic"]:
        usage["anthropic"][model] = {
            "input_tokens": 0,
            "output_tokens": 0,
            "calls": 0,
            "purposes": {}
        }

    usage["anthropic"][model]["input_tokens"] += input_tokens
    usage["anthropic"][model]["output_tokens"] += output_tokens
    usage["anthropic"][model]["calls"] += 1

    # Track by purpose/task
    if purpose not in usage["anthropic"][model]["purposes"]:
        usage["anthropic"][model]["purposes"][purpose] = {
            "input_tokens": 0,
            "output_tokens": 0,
            "calls": 0
        }

    usage["anthropic"][model]["purposes"][purpose]["input_tokens"] += input_tokens
    usage["anthropic"][model]["purposes"][purpose]["output_tokens"] += output_tokens
    usage["anthropic"][model]["purposes"][purpose]["calls"] += 1

    save_usage_data(usage)


def record_google_tts_usage(characters: int, purpose: str = "Unknown"):
    """Record Google Cloud TTS usage with purpose/task description"""
    usage = load_usage_data()

    if "texttospeech" not in usage["google"]:
        usage["google"]["texttospeech"] = {
            "characters": 0,
            "calls": 0,
            "purposes": {}
        }

    usage["google"]["texttospeech"]["characters"] += characters
    usage["google"]["texttospeech"]["calls"] += 1

    # Track by purpose/task
    if purpose not in usage["google"]["texttospeech"]["purposes"]:
        usage["google"]["texttospeech"]["purposes"][purpose] = {
            "characters": 0,
            "calls": 0
        }

    usage["google"]["texttospeech"]["purposes"][purpose]["characters"] += characters
    usage["google"]["texttospeech"]["purposes"][purpose]["calls"] += 1

    save_usage_data(usage)


def calculate_costs(usage_data: Dict = None) -> Dict:
    """Calculate total costs for all APIs"""
    if usage_data is None:
        usage_data = load_usage_data()

    costs = {
        "timestamp": datetime.now().isoformat(),
        "by_model": {},
        "by_provider": {},
        "total_usd": 0.0,
        "total_jpy": 0.0
    }

    # Anthropic costs
    anthropic_total = 0.0
    for model, data in usage_data.get("anthropic", {}).items():
        input_tokens = data.get("input_tokens", 0)
        output_tokens = data.get("output_tokens", 0)

        pricing = PRICING["anthropic"].get(model, {})
        if not pricing:
            continue

        input_cost = (input_tokens / 1_000_000) * pricing["input_per_mtok"]
        output_cost = (output_tokens / 1_000_000) * pricing["output_per_mtok"]
        total_cost = input_cost + output_cost

        costs["by_model"][model] = {
            "provider": "Anthropic",
            "display_name": pricing["display_name"],
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "usd": round(total_cost, 4),
            "jpy": round(total_cost * JPY_PER_USD, 0),
            "color": pricing.get("color", "#60a5fa")
        }

        anthropic_total += total_cost

    if anthropic_total > 0:
        costs["by_provider"]["Anthropic (Claude)"] = {
            "usd": round(anthropic_total, 4),
            "jpy": round(anthropic_total * JPY_PER_USD, 0)
        }
        costs["total_usd"] += anthropic_total

    # Google Cloud TTS costs
    google_total = 0.0
    for service, data in usage_data.get("google", {}).items():
        characters = data.get("characters", 0)

        pricing = PRICING["google"].get(service, {})
        if not pricing:
            continue

        service_cost = (characters / 1_000_000) * pricing["neural2_per_mchars"]

        costs["by_model"][service] = {
            "provider": "Google Cloud",
            "display_name": pricing["display_name"],
            "characters": characters,
            "usd": round(service_cost, 4),
            "jpy": round(service_cost * JPY_PER_USD, 0),
            "color": pricing.get("color", "#F59E0B")
        }

        google_total += service_cost

    if google_total > 0:
        costs["by_provider"]["Google Cloud"] = {
            "usd": round(google_total, 4),
            "jpy": round(google_total * JPY_PER_USD, 0)
        }
        costs["total_usd"] += google_total

    costs["total_jpy"] = round(costs["total_usd"] * JPY_PER_USD, 0)

    return costs


def save_costs(costs: Dict):
    """Save calculated costs to file"""
    with open(COSTS_FILE, "w", encoding="utf-8") as f:
        json.dump(costs, f, ensure_ascii=False, indent=2)


def get_current_costs() -> Dict:
    """Get current calculated costs"""
    if COSTS_FILE.exists():
        try:
            with open(COSTS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass

    # Calculate fresh
    costs = calculate_costs()
    save_costs(costs)
    return costs


def get_dashboard_data() -> Dict:
    """Get data formatted for dashboard display with subscription and API usage separated"""
    costs = get_current_costs()
    subscription = load_subscription_config()

    subscription_plan = subscription.get("subscription_plan", {})
    subscription_usd = subscription_plan.get("monthly_usd", 0.0)
    subscription_jpy = round(subscription_usd * JPY_PER_USD, 0)

    api_usage_usd = costs["total_usd"]
    api_usage_jpy = costs["total_jpy"]

    total_usd = subscription_usd + api_usage_usd
    total_jpy = subscription_jpy + api_usage_jpy

    dashboard = {
        "total_jpy": total_jpy,
        "total_usd": total_usd,
        "subscription": {
            "name": subscription_plan.get("name", "Claude Subscription"),
            "description": subscription_plan.get("description", "Claude subscription"),
            "usd": round(subscription_usd, 2),
            "jpy": subscription_jpy
        },
        "api_usage": {
            "total_usd": round(api_usage_usd, 4),
            "total_jpy": api_usage_jpy,
            "models": []
        }
    }

    # Add models under API usage with purposes
    usage_data = load_usage_data()

    for model_id, cost_data in costs.get("by_model", {}).items():
        provider = cost_data.get("provider", "Unknown")
        display_name = cost_data.get("display_name", model_id)

        model_info = {
            "id": model_id,
            "name": display_name,
            "provider": provider,
            "jpy": cost_data.get("jpy", 0),
            "usd": cost_data.get("usd", 0),
            "color": cost_data.get("color", "#60a5fa"),
            "url": get_billing_url(provider),
            "purposes": []
        }

        # Add purpose breakdown for Anthropic models
        if provider == "Anthropic" and model_id in usage_data.get("anthropic", {}):
            model_usage = usage_data["anthropic"][model_id]
            for purpose, purpose_data in model_usage.get("purposes", {}).items():
                input_toks = purpose_data.get("input_tokens", 0)
                output_toks = purpose_data.get("output_tokens", 0)
                purpose_cost = (input_toks / 1_000_000) * PRICING["anthropic"][model_id]["input_per_mtok"]
                purpose_cost += (output_toks / 1_000_000) * PRICING["anthropic"][model_id]["output_per_mtok"]

                model_info["purposes"].append({
                    "name": purpose,
                    "calls": purpose_data.get("calls", 0),
                    "input_tokens": input_toks,
                    "output_tokens": output_toks,
                    "usd": round(purpose_cost, 4),
                    "jpy": round(purpose_cost * JPY_PER_USD, 0)
                })

        # Add purpose breakdown for Google services
        if provider == "Google Cloud" and model_id == "texttospeech" and "texttospeech" in usage_data.get("google", {}):
            tts_usage = usage_data["google"]["texttospeech"]
            for purpose, purpose_data in tts_usage.get("purposes", {}).items():
                chars = purpose_data.get("characters", 0)
                purpose_cost = (chars / 1_000_000) * PRICING["google"]["texttospeech"]["neural2_per_mchars"]

                model_info["purposes"].append({
                    "name": purpose,
                    "calls": purpose_data.get("calls", 0),
                    "characters": chars,
                    "usd": round(purpose_cost, 4),
                    "jpy": round(purpose_cost * JPY_PER_USD, 0)
                })

        dashboard["api_usage"]["models"].append(model_info)

    # Sort by cost (highest first)
    dashboard["api_usage"]["models"].sort(key=lambda x: x["jpy"], reverse=True)

    return dashboard


def get_billing_url(provider: str) -> str:
    """Get the official billing page URL for a provider"""
    urls = {
        "Anthropic": "https://console.anthropic.com/settings/usage",
        "Google Cloud": "https://console.cloud.google.com/billing",
        "OpenAI": "https://platform.openai.com/account/billing/overview"
    }
    return urls.get(provider, "#")


if __name__ == "__main__":
    # Test
    costs = get_current_costs()
    print(json.dumps(costs, indent=2, ensure_ascii=False))

    print("\n=== Dashboard Data ===")
    dashboard = get_dashboard_data()
    print(json.dumps(dashboard, indent=2, ensure_ascii=False))
