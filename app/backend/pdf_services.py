from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.pdfbase import pdfmetrics
from typing import Dict

ALIGNMENT_MAP = {
    "left": TA_LEFT,
    "center": TA_CENTER,
    "right": TA_RIGHT
}

class ATSResumePDFGenerator:
    def __init__(self, variables: Dict):
        self.vars = variables
        self.styles = getSampleStyleSheet()
        self.base_font = self.vars.get("font_settings", {}).get("base_font_name", "Helvetica")
        
        self.register_font_family(self.base_font)
        self.setup_custom_styles()

    def register_font_family(self, base_font_name: str):
        """
        Registers a standard Type 1 font family with its variants using the correct names.
        """
        if base_font_name == 'Helvetica':
            pdfmetrics.registerFontFamily('Helvetica', normal='Helvetica', bold='Helvetica-Bold', italic='Helvetica-Oblique', boldItalic='Helvetica-BoldOblique')
        elif base_font_name == 'Times-Roman':
            pdfmetrics.registerFontFamily('Times-Roman', normal='Times-Roman', bold='Times-Bold', italic='Times-Italic', boldItalic='Times-BoldItalic')
        elif base_font_name == 'Courier':
            pdfmetrics.registerFontFamily('Courier', normal='Courier', bold='Courier-Bold', italic='Courier-Oblique', boldItalic='Courier-BoldOblique')

    def setup_custom_styles(self):
        """Dynamically create styles from the variables dictionary."""
        style_vars = self.vars.get("styles", {})
        for name, properties in style_vars.items():
            alignment = ALIGNMENT_MAP.get(str(properties.get("alignment", "left")).lower(), TA_LEFT)
            
            self.styles.add(ParagraphStyle(
                name=name.capitalize(),
                parent=self.styles['Normal'],
                fontName=self.base_font,
                fontSize=properties.get("fontsize", 10),
                spaceAfter=properties.get("spaceAfter", 2),
                spaceBefore=properties.get("spaceBefore", 2),
                leftIndent=properties.get("leftIndent", 0),
                bulletIndent=properties.get("bulletIndent", 0),
                alignment=alignment
            ))

    def create_contact_info(self, contact_data):
        contact_parts = []
        if 'location' in contact_data: contact_parts.append(f"{contact_data['location']} (open to relocation)")
        if 'email' in contact_data: contact_parts.append(f'<link href="mailto:{contact_data["email"]}" color="black">{contact_data["email"]}</link>')
        if 'phone' in contact_data: contact_parts.append(contact_data['phone'])
        if 'linkedin' in contact_data: contact_parts.append(f"""<link href="{contact_data["linkedin"]}" color="black">{contact_data["linkedin"].split('www.')[1]}</link>""")
        if 'github' in contact_data: contact_parts.append(f"""<link href="{contact_data["github"]}" color="black">{contact_data["github"].split('://')[1]}</link>""")
        if 'medium' in contact_data: contact_parts.append(f"""<link href="{contact_data["medium"]}" color="black">{contact_data["medium"].split('://')[1]}</link>""")
        return ' • '.join(contact_parts)

    def add_section_header(self, story, title):
        hr_vars = self.vars.get("styles", {}).get("horizontal_line", {})
        story.append(Paragraph(f"<b>{title.upper()}</b>", self.styles['Header']))
        story.append(HRFlowable(
            width="100%",
            thickness=hr_vars.get("thickness", 0.5),
            color=colors.black,
            spaceBefore=hr_vars.get("spaceBefore", 3),
            spaceAfter=hr_vars.get("spaceAfter", 3)
        ))

    def create_two_part_line(self, left_text, right_text, left_bold=False, separation_key=None):
        l_text = f"<b>{left_text}</b>" if left_bold else left_text
        r_text = f"<i>{right_text}</i>"
        separation = self.vars.get("spaces", {}).get("horizontal", {}).get(separation_key, 100)
        separator = '&nbsp;' * separation
        return Paragraph(f"{l_text}{separator}{r_text}", self.styles['Subheader'])

    def generate_pdf_from_data(self, data: Dict, output_file: str):
        doc = SimpleDocTemplate(output_file, pagesize=letter, rightMargin=0.4*inch, leftMargin=0.4*inch, topMargin=0.4*inch, bottomMargin=0.4*inch)
        story = []
        
        v_spaces = self.vars.get("spaces", {}).get("vertical", {})
        section_gap = v_spaces.get("section_gap_inch", 0.1) * inch
        
        story.append(Paragraph(f"<b>{data['name']}</b>", self.styles['Name']))
        story.append(Paragraph(self.create_contact_info(data['contact']), self.styles['Contact']))

        if 'summary' in data and data['summary']:
            self.add_section_header(story, "Summary")
            # Use the new 'Summary' style
            story.append(Paragraph(data['summary'], self.styles['Summary']))
            story.append(Spacer(1, section_gap))

        if 'education' in data and data['education']:
            self.add_section_header(story, "Education")
            for i, edu in enumerate(data['education']):
                story.append(self.create_two_part_line(edu['school'].upper(), edu['location'], left_bold=True, separation_key=f"education{i+1}"))
                degree_info = edu['degree'] + (f", GPA: {edu['gpa']}" if 'gpa' in edu else "")
                story.append(self.create_two_part_line(degree_info, edu['dates'], left_bold=False, separation_key=f"degree{i+1}"))
                if 'details' in edu:
                    story.append(Paragraph(f"<b>Coursework:</b> {edu['details']}", self.styles['Coursework']))
                if i < len(data['education']) - 1:
                    story.append(Spacer(1, section_gap))
            story.append(Spacer(1, section_gap))

        if 'skills' in data and data['skills']:
            self.add_section_header(story, "Technical Skills")
            for category, skills_value in data['skills'].items():
                skills_text = ""
                if isinstance(skills_value, list):
                    skills_text = ', '.join(str(s) for s in skills_value)
                elif isinstance(skills_value, str):
                    skills_text = skills_value
                
                if skills_text:
                    # Use the new dedicated 'Skills' style
                    story.append(Paragraph(f"• <b>{category}:</b> {skills_text}", self.styles['Skills']))
            story.append(Spacer(1, section_gap))

        if 'experience' in data and data['experience']:
            self.add_section_header(story, "Professional Experience")
            for i, job in enumerate(data['experience']):
                story.append(self.create_two_part_line(job['company'].upper(), job['location'], left_bold=True, separation_key=f"company{i+1}"))
                story.append(self.create_two_part_line(job['title'], job['dates'], left_bold=False, separation_key=f"title{i+1}"))
                if 'bullets' in job:
                    for bullet in job['bullets']:
                        story.append(Paragraph(f"• {bullet}", self.styles['Bulleted_list']))
                story.append(Spacer(1, section_gap))

        if 'projects' in data and data['projects']:
            self.add_section_header(story, "Projects")
            for project in data['projects']:
                story.append(Paragraph(f"<b>{project['title']}</b>", self.styles['Subheader']))
                if 'bullets' in project:
                    for bullet in project['bullets']:
                        story.append(Paragraph(f"• {bullet}", self.styles['Bulleted_list']))
                story.append(Spacer(1, section_gap))

        doc.build(story)
        print(f"ATS-optimized resume generated: {output_file}")
