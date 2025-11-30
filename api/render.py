"""
HTML rendering utilities for game files.
"""

from typing import List


def render_game_files_html(game: dict, files: List) -> str:
    """Render a beautiful HTML page for game files."""

    # Group files by type
    pdfs = [f for f in files if f.source_type == "pdf"]
    htmls = [f for f in files if f.source_type == "html"]
    links = [f for f in files if f.source_type == "link"]
    others = [f for f in files if f.source_type not in ["pdf", "html", "link"]]

    def render_file_card(file) -> str:
        icon = {
            "pdf": "📄",
            "html": "🌐",
            "link": "🔗",
            "txt": "📝",
            "video": "🎥",
            "other": "📎",
        }.get(file.source_type, "📎")

        title = file.title or "Untitled"
        is_local = file.local_filename is not None
        badge = (
            '<span class="badge badge-local">Downloaded</span>'
            if is_local
            else '<span class="badge badge-external">External Link</span>'
        )

        # Show preview for PDFs
        preview = ""
        if file.source_type == "pdf" and is_local:
            preview = f'<div class="preview"><embed src="{file.link}" type="application/pdf" width="100%" height="200px" /></div>'

        original_source = ""
        if file.url:
            original_source = f'<a href="{file.url}" target="_blank" class="btn btn-secondary">Original Source</a>'

        return f"""
        <div class="file-card">
            <div class="file-icon">{icon}</div>
            <div class="file-content">
                <h3 class="file-title">{title}</h3>
                {badge}
                {preview}
                <div class="file-actions">
                    <a href="{file.link}" target="_blank" class="btn btn-primary">
                        {"View" if is_local else "Open Link"}
                    </a>
                    {original_source}
                </div>
            </div>
        </div>
        """

    def render_section(title: str, files_list: List) -> str:
        if not files_list:
            return ""
        cards = "".join(render_file_card(f) for f in files_list)
        return f"""
        <div class="section">
            <h2 class="section-title">{title}</h2>
            <div class="files-grid">
                {cards}
            </div>
        </div>
        """

    sections_html = ""
    sections_html += render_section("📄 PDF Documents", pdfs)
    sections_html += render_section("🌐 Web Pages", htmls)
    sections_html += render_section("🔗 External Links", links)
    sections_html += render_section("📎 Other Files", others)

    empty_state = (
        '<div class="section"><div class="empty-state"><div class="empty-state-icon">🎲</div>'
        "<p>No files found for this game yet.</p></div></div>"
        if not files
        else ""
    )

    game_name = game["name"]
    description = game.get("description") or "Game Resources & Documentation"

    # Build metadata display
    metadata_html = ""
    metadata_items = []
    if game.get("difficulty_score"):
        difficulty = game["difficulty_score"]
        metadata_items.append(
            f'<span class="metadata-item">⚙️ Difficulty: {difficulty}/5.0</span>'
        )
    if game.get("player_count"):
        player_count = game["player_count"]
        metadata_items.append(
            f'<span class="metadata-item">👥 Players: {player_count}</span>'
        )
    if game.get("bgg_url"):
        bgg_url = game["bgg_url"]
        metadata_items.append(
            f'<a href="{bgg_url}" target="_blank" class="metadata-item metadata-link">🎲 BoardGameGeek</a>'
        )

    if metadata_items:
        metadata_html = f'<div class="game-metadata">{" ".join(metadata_items)}</div>'

    # Embed YouTube video if available
    youtube_embed = ""
    if game.get("tutorial_video_url"):
        video_url = game["tutorial_video_url"]
        # Extract video ID from YouTube URL
        video_id = None
        if "youtube.com/watch?v=" in video_url:
            video_id = video_url.split("watch?v=")[1].split("&")[0]
        elif "youtu.be/" in video_url:
            video_id = video_url.split("youtu.be/")[1].split("?")[0]

        if video_id:
            youtube_embed = f"""
            <div class="youtube-container">
                <iframe
                    width="100%"
                    height="400"
                    src="https://www.youtube.com/embed/{video_id}"
                    frameborder="0"
                    allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                    allowfullscreen>
                </iframe>
            </div>
            """

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{game_name} - OtterBot Files</title>
    <link rel="stylesheet" href="/static/css/styles.css">
</head>
<body>
    <div class="container">
        <div class="header">
            <img src="/assets/images/otterbotlogo.png" alt="OtterBot Logo" class="otter-logo" />
            <h1>{game_name}</h1>
            <p class="subtitle">{description}</p>
            {metadata_html}
        </div>

        {youtube_embed}

        {sections_html}

        {empty_state}
    </div>
</body>
</html>
"""
    return html
