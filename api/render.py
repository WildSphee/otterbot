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
        </div>

        {sections_html}

        {empty_state}
    </div>
</body>
</html>
"""
    return html
