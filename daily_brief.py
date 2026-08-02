#!/usr/bin/env python3
"""
Daily Brief: generates a 4-section email (algorithm, GRE words, CS concept,
industry/interview tip) via the Gemini API (free tier), avoiding repeats
using a history file, and sends it over SMTP as a styled HTML email.

Env vars required:
  GEMINI_API_KEY       - Gemini API key (free, from Google AI Studio - no card needed)
  SMTP_HOST            - e.g. smtp.gmail.com
  SMTP_PORT            - e.g. 587
  SMTP_USER            - sending email address
  SMTP_PASS            - app password (NOT your regular password)
  MAIL_TO              - recipient address (can be same as SMTP_USER)
"""

import json
import os
import re
import smtplib
import sys
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import urllib.error
import urllib.request

HISTORY_PATH = Path(__file__).parent / "history.json"
# gemini-2.5-flash was retired for new API keys (Aug 2026). gemini-3.6-flash
# is the current stable Flash model on the free tier. If this ever 404s
# again, check https://ai.google.dev/gemini-api/docs/models for the current
# model list — Google retires versions periodically.
MODEL = "gemini-3.6-flash"
MAX_HISTORY_ITEMS = 60  # per category, to keep prompt size sane


def load_history() -> dict:
    if HISTORY_PATH.exists():
        return json.loads(HISTORY_PATH.read_text())
    return {"algorithms": [], "gre_words": [], "cs_concepts": [], "tips": []}


def save_history(history: dict) -> None:
    for key in history:
        history[key] = history[key][-MAX_HISTORY_ITEMS:]
    HISTORY_PATH.write_text(json.dumps(history, indent=2))


RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "algorithm": {
            "type": "OBJECT",
            "properties": {
                "name": {"type": "STRING", "maxLength": 60},
                "explanation": {"type": "STRING", "maxLength": 500},
                "sample_problem": {"type": "STRING", "maxLength": 400},
                "walkthrough": {"type": "STRING", "maxLength": 700},
            },
            "required": ["name", "explanation", "sample_problem", "walkthrough"],
        },
        "gre_words": {
            "type": "ARRAY",
            "minItems": 3,
            "maxItems": 3,
            "items": {
                "type": "OBJECT",
                "properties": {
                    "word": {"type": "STRING", "maxLength": 30},
                    "definition": {"type": "STRING", "maxLength": 150},
                    "example_sentence": {"type": "STRING", "maxLength": 200},
                },
                "required": ["word", "definition", "example_sentence"],
            },
        },
        "cs_concept": {
            "type": "OBJECT",
            "properties": {
                "name": {"type": "STRING", "maxLength": 60},
                "explanation": {"type": "STRING", "maxLength": 500},
            },
            "required": ["name", "explanation"],
        },
        "industry_tip": {
            "type": "OBJECT",
            "properties": {
                "title": {"type": "STRING", "maxLength": 60},
                "content": {"type": "STRING", "maxLength": 500},
            },
            "required": ["title", "content"],
        },
    },
    "required": ["algorithm", "gre_words", "cs_concept", "industry_tip"],
}


def call_gemini(prompt: str) -> str:
    api_key = os.environ["GEMINI_API_KEY"]
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            # 65,536 is gemini-3.6-flash's real ceiling - it's just a safety
            # net against runaway thinking, not a length target. The actual
            # length guarantee is responseSchema below: maxLength on each
            # field is a hard constraint the model must obey, not just an
            # instruction it's likely to follow.
            "maxOutputTokens": 65536,
            "responseMimeType": "application/json",
            "responseSchema": RESPONSE_SCHEMA,
        },
    }).encode()

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "content-type": "application/json",
            "x-goog-api-key": api_key,
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        # Surface Google's actual error message instead of a bare status code,
        # so misconfigurations (bad key, wrong model name, etc.) are obvious.
        error_body = e.read().decode(errors="replace")
        print(f"Gemini API error {e.code}: {error_body}", file=sys.stderr)
        raise
    return data["candidates"][0]["content"]["parts"][0]["text"]


def build_prompt(history: dict) -> str:
    return f"""Generate today's "Daily Brief" email content for a software engineer
prepping for interviews and building general knowledge. Return ONLY valid JSON,
no markdown fences, no preamble, matching exactly this schema:

{{
  "algorithm": {{
    "name": "string - algorithm name",
    "explanation": "string - clear explanation, 3-5 sentences",
    "sample_problem": "string - a concrete sample problem",
    "walkthrough": "string - how the algorithm solves the sample problem, step by step"
  }},
  "gre_words": [
    {{"word": "string", "definition": "string", "example_sentence": "string"}},
    ... (exactly 3 words)
  ],
  "cs_concept": {{
    "name": "string - concept name",
    "explanation": "string - clear explanation, 3-5 sentences"
  }},
  "industry_tip": {{
    "title": "string - short title",
    "content": "string - 3-5 sentences of practical interview or industry insight"
  }}
}}

Do NOT reuse any of the following, which have already been sent:
- Algorithms already used: {history['algorithms'] or 'none yet'}
- GRE words already used: {history['gre_words'] or 'none yet'}
- CS concepts already used: {history['cs_concepts'] or 'none yet'}
- Tips/topics already used: {history['tips'] or 'none yet'}

Pick genuinely different, non-obvious items each time. Vary difficulty and topic area
(don't just cycle through sorting algorithms, for instance - mix in graphs, DP, greedy,
string algorithms, math/number theory, system design pieces, etc.)."""


def parse_response(text: str) -> dict:
    # Strip accidental code fences if the model adds them anyway
    cleaned = re.sub(r"^```json\s*|\s*```$", "", text.strip())
    return json.loads(cleaned)


def render_email_text(content: dict) -> str:
    """Plain-text fallback, for email clients that don't render HTML."""
    algo = content["algorithm"]
    words = content["gre_words"]
    concept = content["cs_concept"]
    tip = content["industry_tip"]

    words_block = "\n\n".join(
        f"  • {w['word']} — {w['definition']}\n    \"{w['example_sentence']}\""
        for w in words
    )

    return f"""Good morning! Here's your Daily Brief for {datetime.now().strftime('%A, %B %d, %Y')}.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ALGORITHM: {algo['name']}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{algo['explanation']}

Sample problem:
{algo['sample_problem']}

Walkthrough:
{algo['walkthrough']}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
GRE WORDS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{words_block}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CS CONCEPT: {concept['name']}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{concept['explanation']}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
INDUSTRY / INTERVIEW TIP: {tip['title']}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{tip['content']}
"""


def _esc(s: str) -> str:
    """Minimal HTML-escaping so model output can't break the markup."""
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def render_email_html(content: dict) -> str:
    algo = content["algorithm"]
    words = content["gre_words"]
    concept = content["cs_concept"]
    tip = content["industry_tip"]
    date_str = datetime.now().strftime("%A, %B %d").upper()

    # Palette: dark navy header, single accent color per section (newsletter-style tags)
    NAVY = "#0f1729"
    INK = "#161a2b"
    MUTED = "#6b7280"
    BORDER = "#e8e9ee"
    BG = "#f4f4f8"

    def tag(label: str, color: str) -> str:
        return (
            f'<span style="display:inline-block; background:{color}1a; color:{color}; '
            f'font-size:11px; font-weight:700; letter-spacing:0.08em; text-transform:uppercase; '
            f'padding:4px 10px; border-radius:20px;">{label}</span>'
        )

    words_html = "".join(
        f"""
        <tr>
          <td style="padding:14px 0; border-top:1px solid {BORDER};">
            <div style="font-weight:700; color:{INK}; font-size:15px; margin-bottom:3px;">
              {_esc(w['word'])}
              <span style="font-weight:400; color:{MUTED}; font-size:14px;"> · {_esc(w['definition'])}</span>
            </div>
            <div style="color:{MUTED}; font-size:13.5px; font-style:italic;">
              "{_esc(w['example_sentence'])}"
            </div>
          </td>
        </tr>"""
        for w in words
    )

    def card(tag_label: str, tag_color: str, title: str, inner_html: str) -> str:
        return f"""
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
               style="background:#ffffff; border:1px solid {BORDER}; border-radius:14px;
                      margin-bottom:20px; overflow:hidden;">
          <tr>
            <td style="padding:22px 26px 24px 26px;">
              <div style="margin-bottom:10px;">{tag(tag_label, tag_color)}</div>
              <div style="font-size:19px; font-weight:800; color:{INK}; line-height:1.3; margin-bottom:12px;">
                {_esc(title)}
              </div>
              {inner_html}
            </td>
          </tr>
        </table>"""

    algo_html = f"""
        <div style="color:#3d4152; font-size:14.5px; line-height:1.65; margin-bottom:16px;">
          {_esc(algo['explanation'])}
        </div>
        <div style="background:{BG}; border-radius:10px; padding:16px 18px; margin-bottom:12px;">
          <div style="font-weight:700; color:{INK}; font-size:12px; letter-spacing:0.04em;
                      text-transform:uppercase; margin-bottom:6px;">Problem</div>
          <div style="color:#3d4152; font-size:14px; line-height:1.6;">{_esc(algo['sample_problem'])}</div>
        </div>
        <div style="background:{BG}; border-radius:10px; padding:16px 18px;">
          <div style="font-weight:700; color:{INK}; font-size:12px; letter-spacing:0.04em;
                      text-transform:uppercase; margin-bottom:6px;">Walkthrough</div>
          <div style="color:#3d4152; font-size:14px; line-height:1.6;">{_esc(algo['walkthrough'])}</div>
        </div>"""

    words_card = f"""
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
          {words_html}
        </table>"""

    concept_html = f"""
        <div style="color:#3d4152; font-size:14.5px; line-height:1.65;">
          {_esc(concept['explanation'])}
        </div>"""

    tip_html = f"""
        <div style="color:#3d4152; font-size:14.5px; line-height:1.65;">
          {_esc(tip['content'])}
        </div>"""

    return f"""\
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin:0; padding:0; background:{BG}; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{BG};">
    <tr>
      <td align="center" style="padding:0 0 32px 0;">
        <table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px; width:100%;">

          <!-- Header -->
          <tr>
            <td style="background:{NAVY}; border-radius:16px 16px 0 0; padding:28px 28px 24px 28px;">
              <div style="color:#8b93a7; font-size:11px; font-weight:700; letter-spacing:0.12em;
                          text-transform:uppercase; margin-bottom:6px;">{date_str}</div>
              <div style="color:#ffffff; font-size:24px; font-weight:800; letter-spacing:-0.01em;">
                The Daily Brief
              </div>
              <div style="color:#8b93a7; font-size:13px; margin-top:4px;">
                One algorithm, three words, one concept, one tip.
              </div>
            </td>
          </tr>

          <!-- Body -->
          <tr>
            <td style="background:{BG}; padding:24px 16px 0 16px;">
              {card("Algorithm", "#4361ee", algo['name'], algo_html)}
              {card("GRE Words", "#f77f00", "3 words worth knowing", words_card)}
              {card("CS Concept", "#2a9d8f", concept['name'], concept_html)}
              {card("Interview Tip", "#e63946", tip['title'], tip_html)}
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="padding:4px 24px 8px 24px; text-align:center;">
              <div style="color:#9ca3af; font-size:12px;">
                Sent automatically every morning at 9 · Never repeats a topic
              </div>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def send_email(text_body: str, html_body: str) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🌅 Daily Brief — {datetime.now().strftime('%b %d, %Y')}"
    msg["From"] = os.environ["SMTP_USER"]
    msg["To"] = os.environ["MAIL_TO"]

    # Attach plain-text first, HTML second - email clients use the LAST
    # part they understand, so HTML wins where supported, and clients that
    # can't render HTML fall back to the plain-text version automatically.
    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP(os.environ["SMTP_HOST"], int(os.environ["SMTP_PORT"])) as server:
        server.starttls()
        server.login(os.environ["SMTP_USER"], os.environ["SMTP_PASS"])
        server.send_message(msg)


def main():
    history = load_history()
    prompt = build_prompt(history)

    raw = call_gemini(prompt)
    try:
        content = parse_response(raw)
    except json.JSONDecodeError:
        print("Failed to parse model response as JSON:", raw, file=sys.stderr)
        raise

    text_body = render_email_text(content)
    html_body = render_email_html(content)
    send_email(text_body, html_body)

    # Update history so tomorrow's run avoids repeats
    history["algorithms"].append(content["algorithm"]["name"])
    history["gre_words"].extend(w["word"] for w in content["gre_words"])
    history["cs_concepts"].append(content["cs_concept"]["name"])
    history["tips"].append(content["industry_tip"]["title"])
    save_history(history)

    print("Sent successfully.")


if __name__ == "__main__":
    main()
