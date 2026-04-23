# API Cost Dashboard Configuration

## Overview

The API cost dashboard now clearly distinguishes between two separate cost categories:

1. **Claude月額料金 (Claude Monthly Subscription)** - Monthly/subscription fees
2. **API使用料金 (API Usage Costs)** - Pay-per-call costs from actual API usage

## Configuration Files

### 1. `.claude-subscription.json` - Monthly Subscription Configuration

This file stores your Claude subscription costs (Claude Code Pro, Claude subscription, etc.)

**Location**: `/Users/shuichifujisaki/Documents/Claude/ai-news-repo/.claude-subscription.json`

**Default Content**:
```json
{
  "subscription_plan": {
    "name": "Claude Code (Pro)",
    "monthly_usd": 20.00,
    "description": "Claude Code Pro monthly subscription"
  }
}
```

**How to Customize**:
- Edit the `monthly_usd` value to match your actual monthly subscription cost
- Update `name` to match your subscription plan
- The cost is automatically converted to JPY (¥) using the exchange rate: 1 USD = 150 JPY

**Example for different plans**:
```json
{
  "subscription_plan": {
    "name": "Claude Pro (Chat)",
    "monthly_usd": 20.00,
    "description": "Claude Pro monthly chat subscription"
  }
}
```

### 2. `.api-usage.json` - API Token Usage Tracking

This file tracks all API token consumption for accurate pay-per-call billing calculations.

**Location**: `/Users/shuichifujisaki/Documents/Claude/ai-news-repo/.api-usage.json`

**Structure**:
```json
{
  "anthropic": {
    "claude-haiku-4-5-20251001": {
      "input_tokens": 150000,
      "output_tokens": 75000,
      "calls": 45
    },
    "claude-3-5-sonnet-20241022": {
      "input_tokens": 500000,
      "output_tokens": 250000,
      "calls": 80
    },
    "claude-opus-4-1-20250805": {
      "input_tokens": 100000,
      "output_tokens": 50000,
      "calls": 15
    }
  },
  "google": {
    "texttospeech": {
      "characters": 150000,
      "calls": 30
    }
  },
  "openai": {}
}
```

**How to track usage**:
- For Claude API calls: Use `api_cost_calculator.record_anthropic_usage(model, input_tokens, output_tokens)`
- For Google Cloud TTS: Use `api_cost_calculator.record_google_tts_usage(characters)`
- Data is automatically persisted to this file

## Pricing Reference (2026)

### Claude API Pricing
- **Claude Haiku**: $0.80 input / $4.00 output per million tokens
- **Claude 3.5 Sonnet**: $3.00 input / $15.00 output per million tokens
- **Claude Opus**: $15.00 input / $75.00 output per million tokens

### Google Cloud Text-to-Speech
- **Neural2**: $16.00 per million characters

### Exchange Rate
- **1 USD = 150 JPY** (configurable in `api_cost_calculator.py`)

## Dashboard Display

The dashboard now shows:

```
💰 今月のコスト内訳

Total: ¥X,XXX ($Y.YY)

📌 Claude月額料金
Claude Code (Pro) | ¥3,000 ($20.00)

⚙️ API使用料金
実際の利用料金 | ¥1,998 ($13.32)

Claude 3.5 Sonnet      | ¥788 ($5.25)
Claude Opus            | ¥788 ($5.25)
Google Cloud TTS       | ¥360 ($2.40)
Claude Haiku           | ¥63 ($0.42)
```

## Python API Functions

### Recording Usage

```python
from api_cost_calculator import record_anthropic_usage, record_google_tts_usage

# Record Claude API usage
record_anthropic_usage(
    model="claude-3-5-sonnet-20241022",
    input_tokens=50000,
    output_tokens=25000
)

# Record Google TTS usage
record_google_tts_usage(characters=100000)
```

### Getting Costs

```python
from api_cost_calculator import get_dashboard_data

# Get formatted data for dashboard display
costs = get_dashboard_data()

# Output structure:
# {
#   "total_jpy": 4998.0,
#   "total_usd": 33.32,
#   "subscription": {
#     "name": "Claude Code (Pro)",
#     "usd": 20.0,
#     "jpy": 3000.0
#   },
#   "api_usage": {
#     "total_usd": 13.32,
#     "total_jpy": 1998.0,
#     "models": [...]
#   }
# }
```

## Integration with Dashboard

The API cost dashboard is automatically integrated into the main dashboard at `http://localhost:8920` and displays both categories with visual distinction:

- **Subscription costs** appear in purple (📌)
- **API usage costs** appear in blue (⚙️)
- Model names are clickable and link to official billing pages

## Monthly Cost Verification

To verify your costs:
1. **Claude subscription**: Check your Claude account billing settings
2. **API usage**: Visit the official billing consoles:
   - Anthropic: https://console.anthropic.com/settings/usage
   - Google Cloud: https://console.cloud.google.com/billing
   - OpenAI: https://platform.openai.com/account/billing/overview

## Notes

- All costs are converted to JPY automatically for easier Japanese language display
- The dashboard updates when you refresh the page
- Historical data is preserved in `.api-usage.json` for trending analysis
- Exchange rate can be modified in `api_cost_calculator.py` (JPY_PER_USD constant)
