from .static.review_html import HTML as _HTML  # small trick to keep it single-file

def render_review(rid: str) -> str:
    return _HTML.replace("{{RID}}", rid)
