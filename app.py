import json
import re
from html import escape
from urllib.parse import quote_plus
from urllib.request import Request, urlopen

from flask import Flask, request

app = Flask(__name__)


def _extract_text_from_runs(runs):
    if not runs:
        return ""
    return "".join(item.get("text", "") for item in runs if isinstance(item, dict))


def youtube_search(query: str, max_results: int = 10):
    if not query:
        return {"items": [], "error": None}

    search_url = f"https://www.youtube.com/results?search_query={quote_plus(query)}"
    req = Request(search_url, headers={"User-Agent": "Mozilla/5.0"})

    try:
        html = urlopen(req, timeout=20).read().decode("utf-8", errors="ignore")
    except Exception as exc:
        return {"items": [], "error": f"Could not load YouTube results: {exc}"}

    matches = [
        re.search(r"ytInitialData\s*=\s*({.+?})\s*;\s*</script>", html, re.S),
        re.search(r"var\s+ytInitialData\s*=\s*({.+?})\s*;\s*</script>", html, re.S),
    ]

    data_match = next((match for match in matches if match), None)
    if not data_match:
        return {"items": [], "error": "YouTube search page format changed; unable to parse results."}

    try:
        data = json.loads(data_match.group(1))
    except json.JSONDecodeError as exc:
        return {"items": [], "error": f"Could not decode search data: {exc}"}

    results = []
    seen = set()

    def walk(node):
        if isinstance(node, dict):
            renderer = node.get("videoRenderer")
            if renderer:
                video_id = renderer.get("videoId")
                if not video_id:
                    return
                title_runs = renderer.get("title", {}).get("runs", [])
                channel_runs = renderer.get("longBylineText", {}).get("runs", [])
                thumbnail_candidates = renderer.get("thumbnail", {}).get("thumbnails", [])
                thumb = ""
                if thumbnail_candidates:
                    thumb = max(thumbnail_candidates, key=lambda item: item.get("width", 0) * item.get("height", 0)).get("url", "")

                title = _extract_text_from_runs(title_runs) or "Untitled video"
                channel = _extract_text_from_runs(channel_runs) or "Unknown channel"
                if video_id not in seen:
                    seen.add(video_id)
                    results.append({
                        "id": video_id,
                        "title": title,
                        "channel": channel,
                        "thumbnail": thumb,
                    })
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(data)

    return {"items": results[:max_results], "error": None}


def build_page(query: str, selected_id: str = ""):
    videos = []
    error_message = ""

    if query:
        search_result = youtube_search(query)
        if search_result.get("error"):
            error_message = search_result["error"]
        else:
            videos = search_result.get("items", [])

    result_cards = []
    for video in videos:
        href = f"/?query={quote_plus(query)}&video_id={video['id']}"
        result_cards.append(
            f"""
            <a class="video-card" href="{href}">
                <img src="{escape(video['thumbnail'])}" alt="{escape(video['title'])}">
                <div class="video-copy">
                    <strong>{escape(video['title'])}</strong><br>
                    <span>{escape(video['channel'])}</span>
                </div>
            </a>
            """
        )

    player_html = ""
    if selected_id:
        player_html = f"""
        <div class="player">
            <iframe
                width="100%"
                height="420"
                src="https://www.youtube.com/embed/{escape(selected_id, quote=True)}?autoplay=1"
                title="YouTube video player"
                frameborder="0"
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
                referrerpolicy="strict-origin-when-cross-origin"
                allowfullscreen>
            </iframe>
        </div>
        """

    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>YouTube Search</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                margin: 0;
                background: #121212;
                color: #f5f5f5;
            }}
            .page {{
                max-width: 1200px;
                margin: 0 auto;
                padding: 24px;
            }}
            form {{
                display: flex;
                gap: 12px;
                margin-bottom: 24px;
            }}
            input {{
                flex: 1;
                padding: 12px 14px;
                border: none;
                border-radius: 10px;
            }}
            button {{
                padding: 12px 18px;
                border: none;
                border-radius: 10px;
                background: #ff0000;
                color: white;
                font-weight: bold;
                cursor: pointer;
            }}
            .layout {{
                display: grid;
                grid-template-columns: 1.2fr 2fr;
                gap: 24px;
            }}
            .sidebar {{
                background: #1e1e1e;
                padding: 16px;
                border-radius: 12px;
            }}
            .video-card {{
                display: flex;
                gap: 12px;
                color: #fff;
                text-decoration: none;
                background: #272727;
                border-radius: 10px;
                padding: 10px;
                margin-bottom: 12px;
            }}
            .video-card img {{
                width: 168px;
                height: 94px;
                border-radius: 8px;
                object-fit: cover;
            }}
            .video-copy {{
                display: flex;
                flex-direction: column;
                justify-content: center;
            }}
            .player {{
                background: #000;
                border-radius: 12px;
                overflow: hidden;
                margin-bottom: 20px;
            }}
            .error {{
                color: #ff8a8a;
                margin-bottom: 18px;
            }}
            @media (max-width: 900px) {{
                .layout {{
                    grid-template-columns: 1fr;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="page">
            <h1>YouTube Search</h1>

            <form method="GET" action="/">
                <input type="text" name="query" value="{escape(query)}" placeholder="Search YouTube videos">
                <button type="submit">Search</button>
            </form>

            {f'<div class="error">{escape(error_message)}</div>' if error_message else ''}

            <div class="layout">
                <div class="sidebar">
                    <h2>Results</h2>
                    {''.join(result_cards) if result_cards else '<p>No results yet.</p>'}
                </div>

                <div>
                    {player_html if selected_id else '<p>Select a video to play it here.</p>'}
                </div>
            </div>
        </div>
    </body>
    </html>
    """


@app.route("/", methods=["GET", "POST"])
def home():
    query = (request.form.get("query") or request.args.get("query") or "").strip()
    selected_id = request.args.get("video_id", "")
    return build_page(query, selected_id)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
