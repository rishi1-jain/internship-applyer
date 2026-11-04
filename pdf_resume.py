"""ATS-readable PDF rendering; only the saved, reviewed resume text is rendered."""
from io import BytesIO
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, KeepTogether

SECTIONS = {'education','technical skills','experience','projects','leadership & achievements','skills','summary','certifications','awards','research','publications','leadership','work experience'}

def make_pdf(text):
    out = BytesIO()
    doc = SimpleDocTemplate(out, pagesize=letter, leftMargin=36, rightMargin=36, topMargin=30, bottomMargin=30, title='Resume', author='')
    normal = ParagraphStyle('body', fontName='Helvetica', fontSize=9, leading=10.8, spaceAfter=1, textColor=colors.HexColor('#202020'))
    name = ParagraphStyle('name', parent=normal, fontName='Helvetica-Bold', fontSize=20, leading=24, alignment=TA_CENTER, spaceAfter=5)
    heading = ParagraphStyle('section', parent=normal, fontName='Helvetica-Bold', fontSize=10, leading=13, spaceBefore=7, spaceAfter=3, keepWithNext=True)
    entry = ParagraphStyle('entry', parent=normal, fontName='Helvetica-Bold', spaceBefore=5, keepWithNext=True)
    bullet = ParagraphStyle('bullet', parent=normal, leftIndent=9, firstLineIndent=-7, spaceAfter=1)
    story=[]
    first=True
    for line in text.splitlines():
        line=line.strip()
        if not line:
            story.append(Spacer(1,3));continue
        line=line.replace('\u2011','-').replace('\u2013','-').replace('\u2014','-')
        style = name if first else heading if line.lower() in SECTIONS else bullet if line.startswith(('• ', '- ', '* ')) else entry if ' | ' in line and '@' not in line and 'github.com' not in line else normal
        story.append(Paragraph(escape(line),style))
        first=False
    doc.build(story)
    return out.getvalue()
