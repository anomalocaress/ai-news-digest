#!/usr/bin/env python3
"""Test email sending functionality."""

import os
import sys
from datetime import datetime
from pathlib import Path

# Try to load .env file manually
env_file = Path(".env")
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ[key.strip()] = value.strip()

def test_email_send():
    """Test email sending configuration and connectivity."""

    print("=" * 60)
    print("🔍 Email Configuration Test")
    print("=" * 60)

    # Check environment variables
    print("\n1️⃣  Checking environment variables...")
    gmail_address = os.getenv("GMAIL_ADDRESS")
    gmail_password = os.getenv("GMAIL_APP_PASSWORD")

    if not gmail_address:
        print("   ❌ GMAIL_ADDRESS not set")
        print("   → Set in .env file or environment variable")
    else:
        print(f"   ✓ GMAIL_ADDRESS: {gmail_address}")

    if not gmail_password:
        print("   ❌ GMAIL_APP_PASSWORD not set")
        print("   → Get from: https://myaccount.google.com/security")
    else:
        # Show masked password
        masked = gmail_password.replace(" ", "").replace(gmail_password[0], "*")[0:10]
        print(f"   ✓ GMAIL_APP_PASSWORD: {masked}...")

    if not (gmail_address and gmail_password):
        print("\n❌ Missing credentials. Cannot test email sending.")
        print("\nSetup steps:")
        print("1. Get Google App Password:")
        print("   - Go to https://myaccount.google.com/security")
        print("   - Enable 2-Step Verification if not enabled")
        print("   - Select App passwords → Mail → Windows Computer")
        print("   - Copy the generated password (format: xxxx xxxx xxxx xxxx)")
        print("\n2. Create .env file:")
        print("   echo 'GMAIL_ADDRESS=your-email@gmail.com' > .env")
        print("   echo 'GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx' >> .env")
        return False

    # Test SMTP connectivity
    print("\n2️⃣  Testing SMTP connectivity...")
    try:
        import smtplib
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=5) as server:
            print("   ✓ Connected to smtp.gmail.com:465")

            # Test authentication
            server.login(gmail_address, gmail_password)
            print(f"   ✓ Authentication successful for {gmail_address}")

        return True

    except smtplib.SMTPAuthenticationError as e:
        print(f"   ❌ Authentication failed: {e}")
        print("   → Check GMAIL_APP_PASSWORD is correct (with spaces)")
        return False
    except smtplib.SMTPException as e:
        print(f"   ❌ SMTP error: {e}")
        return False
    except Exception as e:
        print(f"   ❌ Connection error: {e}")
        return False


def send_test_email():
    """Send a test email to verify configuration."""

    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    import smtplib

    gmail_address = os.getenv("GMAIL_ADDRESS")
    gmail_password = os.getenv("GMAIL_APP_PASSWORD")
    email_to = "fujisaki@teraco-labo.com"

    print("\n3️⃣  Sending test email...")

    try:
        # Create test email
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "🧪 Test Email - AI News Digest System"
        msg["From"] = gmail_address
        msg["To"] = email_to

        html_content = """
        <html>
          <body style="font-family: sans-serif; line-height: 1.6; color: #333;">
            <h2>AIニュースダイジェスト - テストメール</h2>
            <p>このメールは自動配信システムのテストです。</p>

            <h3>✓ メール送信機能が正常に動作しています</h3>

            <p><strong>送信日時:</strong> """ + datetime.now().strftime("%Y年%m月%d日 %H:%M:%S") + """</p>

            <hr style="margin: 20px 0; border: none; border-top: 1px solid #ddd;">

            <h3>次のステップ</h3>
            <ol>
              <li>GitHub リポジトリの Settings → Secrets and variables</li>
              <li>以下の 2 つを追加:
                <ul>
                  <li><code>GMAIL_ADDRESS</code></li>
                  <li><code>GMAIL_APP_PASSWORD</code></li>
                </ul>
              </li>
              <li>明日朝 6:00 (JST) に自動実行開始</li>
            </ol>

            <p style="color: #666; font-size: 0.9em; margin-top: 20px;">
              This is an automated email from AI News Digest system.
            </p>
          </body>
        </html>
        """

        msg.attach(MIMEText(html_content, "html", "utf-8"))

        # Send email
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10) as server:
            server.sendmail(gmail_address, [email_to], msg.as_string())

        print(f"   ✓ Test email sent to: {email_to}")
        return True

    except Exception as e:
        print(f"   ❌ Failed to send email: {e}")
        return False


if __name__ == "__main__":
    success = test_email_send()

    if success:
        if len(sys.argv) > 1 and sys.argv[1] == "--send-test":
            print()
            send_test_email()
        else:
            print("\n✅ Email configuration is valid!")
            print("\n💡 To send a test email:")
            print("   python3 test_email.py --send-test")
    else:
        print("\n❌ Email configuration incomplete or invalid")
        sys.exit(1)
