#!/usr/bin/env python3
"""Send AI News Digest email from draft"""

import sys
from pathlib import Path
from datetime import datetime

# This script needs to be called from the dashboard or CLI to send the email
# It will use the Gmail MCP through Claude Code

def get_latest_email_draft():
    """Find the latest email draft file"""
    repo_dir = Path(__file__).parent
    email_files = sorted(repo_dir.glob(".email-draft-*.html"), reverse=True)
    if email_files:
        return email_files[0]
    return None


def send_email(html_file: Path):
    """Send email with HTML content

    Note: This requires Claude Code's Gmail MCP integration.
    The email will be created as a draft and needs to be sent manually,
    or integrated with automated workflow.
    """
    with open(html_file, "r", encoding="utf-8") as f:
        html_content = f.read()

    date_str = html_file.stem.replace(".email-draft-", "")

    # Email metadata
    recipient = "fujisaki@teraco-labo.com"
    subject = f"AI News Digest {date_str.replace('-', '年').replace('年', '年').replace('-', '月')}日"

    print(f"📧 Email ready to send:")
    print(f"  To: {recipient}")
    print(f"  Subject: {subject}")
    print(f"  Content: {len(html_content)} bytes")
    print(f"\n💡 Use Claude Code Gmail MCP to send this email:")
    print(f"   mcp__7e996956-edfd-478b-b27f-8f5b2e01a482__create_draft")

    return {
        "to": recipient,
        "subject": subject,
        "htmlBody": html_content
    }


if __name__ == "__main__":
    email_file = get_latest_email_draft()
    if email_file:
        email_data = send_email(email_file)
        print(f"\n✓ Ready to send email from {email_file.name}")
    else:
        print("❌ No email draft found. Run generate_news.py first.")
        sys.exit(1)
