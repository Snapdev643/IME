import sqlite3
import os
import datetime
import html
import shutil

# --- CONFIG ---
DB_PATH = input("Enter the path to your database file (usually starts with '3d0d7'): ").strip()
BACKUP_DIR = input("Enter the path to your iMessage backup directory: ").strip()
EXPORT_DIR = 'imessage_export'
ATTACHMENTS_DIR = os.path.join(EXPORT_DIR, 'attachments')
HTML_PATH = os.path.join(EXPORT_DIR, 'imessages.html')

os.makedirs(ATTACHMENTS_DIR, exist_ok=True)

# --- CONNECT TO DB ---
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# --- Lookup Tables ---
cursor.execute("""
SELECT
    c.ROWID as chat_id,
    IFNULL(h.id, 'Unknown') as handle_id
FROM chat c
LEFT JOIN chat_handle_join chj ON chj.chat_id = c.ROWID
LEFT JOIN handle h ON h.ROWID = chj.handle_id
""")
chat_lookup = {row[0]: row[1] for row in cursor.fetchall()}

# --- Attachments Mapping ---
cursor.execute("""
SELECT
    ma.message_id,
    a.filename,
    a.mime_type,
    a.transfer_name,
    a.guid
FROM message_attachment_join ma
JOIN attachment a ON a.ROWID = ma.attachment_id
""")
attachments_map = {}
for msg_id, filename, mime, name, guid in cursor.fetchall():
    if msg_id not in attachments_map:
        attachments_map[msg_id] = []
    attachments_map[msg_id].append({
        "filename": filename,
        "mime_type": mime,
        "name": name,
        "guid": guid
    })

# --- Messages ---
cursor.execute("""
SELECT
    m.ROWID,
    m.date,
    m.is_from_me,
    m.text,
    cmj.chat_id,
    h.id as handle_id
FROM message m
LEFT JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
LEFT JOIN handle h ON h.ROWID = m.handle_id
WHERE m.text IS NOT NULL OR m.ROWID IN (
    SELECT message_id FROM message_attachment_join
)
ORDER BY cmj.chat_id, m.date
""")

conversations = {}

for row in cursor.fetchall():
    msg_id, date, is_from_me, text, chat_id, handle_id = row
    if chat_id is None:
        chat_id = -1
    contact = chat_lookup.get(chat_id, handle_id or 'Unknown')
    if contact not in conversations:
        conversations[contact] = []

    try:
        ts = datetime.datetime(2001, 1, 1) + datetime.timedelta(seconds=date / 1e9 if date > 1e12 else date)
        timestamp = ts.strftime("%Y-%m-%d %H:%M:%S")
    except:
        timestamp = str(date)

    text = (text or "").replace("[OBJ]", "(Attachment)")
    text = html.escape(text)

    # Add attachments if any
    imgs = []
    for att in attachments_map.get(msg_id, []):
        if att["filename"]:
            relative_path = att["filename"]
            src_path = os.path.join(BACKUP_DIR, relative_path[:2], relative_path)
            dest_path = os.path.join(ATTACHMENTS_DIR, relative_path)
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            try:
                shutil.copy2(src_path, dest_path)
                imgs.append(os.path.relpath(dest_path, EXPORT_DIR).replace("\\", "/"))
            except:
                pass  # File might be missing from backup

    conversations[contact].append({
        "from_me": bool(is_from_me),
        "text": text,
        "timestamp": timestamp,
        "images": imgs
    })

# --- HTML TEMPLATE SETUP ---
html_sections = []
tabs_html = ""
content_html = ""

for idx, (contact, messages) in enumerate(conversations.items()):
    contact_id = f"tab{idx}"
    tabs_html += f'<button class="tablink" onclick="openTab(event, \'{contact_id}\')">{html.escape(contact)}</button>\n'
    section = f'<div id="{contact_id}" class="tabcontent">\n<h2>Chat with {html.escape(contact)}</h2>\n'

    for msg in messages:
        bubble_class = "from-me" if msg["from_me"] else "from-them"
        bubble_html = f'<div class="bubble {bubble_class}">{msg["text"]}</div>'
        timestamp_html = f'<div class="timestamp">{msg["timestamp"]}</div>'

        image_html = ""
        for img_path in msg["images"]:
            if img_path.lower().endswith(('.jpg', '.jpeg', '.png', '.gif')):
                image_html += f'<div class="image"><img src="{img_path}" alt="image" /></div>'

        section += f'<div class="container">{bubble_html}{image_html}{timestamp_html}</div>\n'

    section += '</div>'
    html_sections.append(section)

# --- FINAL HTML ---
html_template = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>iMessage Export</title>
<style>
body {{
    font-family: -apple-system, BlinkMacSystemFont, sans-serif;
    margin: 0;
    background: #f5f5f5;
}}
.tabbar {{
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    background: #1e1e1e;
    overflow-x: auto;
    white-space: nowrap;
    z-index: 100;
}}
.tablink {{
    background: #1e1e1e;
    color: white;
    padding: 10px 20px;
    border: none;
    cursor: pointer;
    display: inline-block;
}}
.tablink:hover {{
    background: #333;
}}
.tabcontent {{
    display: none;
    padding: 80px 20px 20px;
}}
.container {{
    margin: 8px 0;
    overflow: hidden;
}}
.bubble {{
    max-width: 60%;
    padding: 10px 14px;
    border-radius: 20px;
    display: inline-block;
    word-wrap: break-word;
    line-height: 1.4;
    margin: 2px 10px;
}}
.from-me {{
    background-color: #34c759;
    color: white;
    float: right;
    clear: both;
}}
.from-them {{
    background-color: #e5e5ea;
    color: black;
    float: left;
    clear: both;
}}
.timestamp {{
    text-align: center;
    font-size: 0.75em;
    color: #999;
    clear: both;
    margin-bottom: 10px;
}}
.image {{
    text-align: center;
    margin: 5px 0;
}}
.image img {{
    max-width: 300px;
    max-height: 300px;
    border-radius: 12px;
}}
</style>
</head>
<body>

<div class="tabbar">
{tabs_html}
</div>

{''.join(html_sections)}

<script>
function openTab(evt, tabId) {{
    var i, tabcontent, tablinks;
    tabcontent = document.getElementsByClassName("tabcontent");
    for (i = 0; i < tabcontent.length; i++) {{
        tabcontent[i].style.display = "none";
    }}
    tablinks = document.getElementsByClassName("tablink");
    for (i = 0; i < tablinks.length; i++) {{
        tablinks[i].style.backgroundColor = "#1e1e1e";
    }}
    document.getElementById(tabId).style.display = "block";
    evt.currentTarget.style.backgroundColor = "#555";
}}
document.addEventListener("DOMContentLoaded", function() {{
    document.querySelector(".tablink").click();
}});
</script>

</body>
</html>
"""

# --- WRITE HTML FILE ---
os.makedirs(EXPORT_DIR, exist_ok=True)
with open(HTML_PATH, 'w', encoding='utf-8') as f:
    f.write(html_template)

print(f"File exported to {HTML_PATH}.")
