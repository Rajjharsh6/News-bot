from html import escape
def split(text,limit=3900):
    parts=[]
    while len(text)>limit:
        cut=text.rfind('\n',0,limit)
        if cut<limit//2: cut=limit
        parts.append(text[:cut]); text=text[cut:].lstrip()
    if text: parts.append(text)
    return parts
def render(e,analysis=''):
    title=escape(e['title']); source=escape(e['source']); category=escape(e['category'].upper()); pub=escape(e['published'] or 'Not provided')
    score=e['score']; level='🔴 CRITICAL' if score>=9 else '🟠 HIGH' if score>=7 else '🔵 UPDATE'
    text=f'{level} | US MARKET INTELLIGENCE\n\n<b>{title}</b>\n\nSource: {source}\nCategory: {category}\nImportance: {score}/10\nPublished: {pub}\n'
    if e['url']: text+=f'\n<a href="{escape(e["url"],quote=True)}">Open original source</a>\n'
    if e['content']: text+='\n<b>Source content:</b>\n'+escape(e['content'][:2200])+'\n'
    if analysis: text+='\n<b>Groq context (AI-generated):</b>\n'+escape(analysis[:2500])
    return text
