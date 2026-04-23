#!/usr/bin/env python3
"""Recommendation engine based on user preferences"""

import json
from pathlib import Path
from typing import List, Dict
from datetime import datetime

REPO_DIR = Path(__file__).parent
PREFS_FILE = REPO_DIR / "user_preferences.json"


def load_user_preferences():
    """Load user ratings and preferences"""
    if PREFS_FILE.exists():
        try:
            with open(PREFS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {"rated_articles": {}}
    return {"rated_articles": {}}


def analyze_user_preferences(categorized_articles: Dict[str, List[Dict]]) -> Dict:
    """Analyze user preferences from ratings"""
    prefs = load_user_preferences()
    rated_articles = prefs.get("rated_articles", {})

    if not rated_articles:
        return {"preference": "neutral", "preferred_categories": []}

    # Extract preference data
    category_ratings = {}

    for article_id, rating_data in rated_articles.items():
        rating = rating_data.get("rating", 0)

        # Try to identify category from article_id
        # Format: ai-news-YYYY-MM-DD_N
        parts = article_id.split("_")
        if len(parts) >= 2:
            # This is a simplification - would need actual article metadata
            pass

    # Build preference summary
    avg_rating = sum(r.get("rating", 0) for r in rated_articles.values()) / len(rated_articles) if rated_articles else 0

    return {
        "total_rated": len(rated_articles),
        "average_rating": avg_rating,
        "high_interest": avg_rating >= 4,
        "moderate_interest": 3 <= avg_rating < 4,
        "needs_improvement": avg_rating < 3,
        "preferences_captured": len(rated_articles) >= 5  # Enough for personalization
    }


def get_recommended_topics(user_analysis: Dict) -> List[str]:
    """Get topics to recommend based on user analysis"""
    topics = []

    if user_analysis.get("high_interest"):
        topics.extend(["AI research breakthroughs", "Enterprise AI adoption", "Advanced AI tools"])

    if user_analysis.get("moderate_interest"):
        topics.extend(["AI policy developments", "Market analysis", "Tool reviews"])

    if user_analysis.get("needs_improvement"):
        topics = ["General AI updates", "Industry news", "New product launches"]

    return topics


def build_recommendation_prompt(user_analysis: Dict, recommended_topics: List[str]) -> str:
    """Build prompt for Claude to generate recommendations"""

    ratings_summary = f"""
User Preference Analysis:
- Total Articles Rated: {user_analysis.get('total_rated', 0)}
- Average Rating: {user_analysis.get('average_rating', 0):.1f}/5
- Preferences Captured: {'Yes' if user_analysis.get('preferences_captured') else 'No'}

Recommended Topics for This User:
{chr(10).join(f"- {topic}" for topic in recommended_topics)}
"""

    return ratings_summary


def generate_recommendations(user_analysis: Dict) -> Dict:
    """Generate personalized news recommendations"""

    recommendations = {
        "timestamp": datetime.now().isoformat(),
        "personalized": user_analysis.get("preferences_captured", False),
        "topics": get_recommended_topics(user_analysis),
        "summary": build_recommendation_prompt(user_analysis, get_recommended_topics(user_analysis))
    }

    return recommendations


def add_recommendations_to_email(email_html: str, recommendations: Dict) -> str:
    """Add recommendation section to email HTML"""

    if not recommendations.get("personalized"):
        # Not enough data yet
        recommendation_html = """
  <div style="background: #e8f4f8; padding: 15px; border-radius: 8px; margin-bottom: 20px;">
    <h3 style="margin-top: 0; color: #0c5460;">💡 あなたの興味に合わせたニュースをお届けします</h3>
    <p style="margin: 10px 0; color: #0c5460; font-size: 13px;">
      ダッシュボードで記事に星マークをつけることで、あなたの好みを学習します。
      5件以上の評価で、カスタマイズされたニュース推奨が開始されます。
    </p>
  </div>
"""
    else:
        topics = recommendations.get("topics", [])
        topics_html = "<br>".join(f"・{topic}" for topic in topics)

        recommendation_html = f"""
  <div style="background: #dff0d8; padding: 15px; border-radius: 8px; margin-bottom: 20px;">
    <h3 style="margin-top: 0; color: #3c763d;">⭐ あなたへのおすすめ</h3>
    <p style="margin: 10px 0; color: #3c763d; font-size: 13px;">
      あなたの評価パターンから、以下のトピックに興味がありそうです：<br>
      {topics_html}
    </p>
    <p style="margin: 10px 0; color: #3c763d; font-size: 12px;">
      ★ これらのトピックの記事を特別に厳選してお送りします。
    </p>
  </div>
"""

    # Insert recommendations after the header
    insert_point = email_html.find('<p>おはようございます！</p>')
    if insert_point > 0:
        email_html = email_html[:insert_point] + recommendation_html + email_html[insert_point:]

    return email_html


if __name__ == "__main__":
    # Test recommendation engine
    analysis = analyze_user_preferences({})
    print("User Analysis:", analysis)

    recs = generate_recommendations(analysis)
    print("\nRecommendations:", recs)
