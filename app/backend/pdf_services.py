from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from typing import Dict, List, Tuple
import math
import copy

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
        try:
            if base_font_name == 'Helvetica':
                pdfmetrics.registerFontFamily('Helvetica', normal='Helvetica', bold='Helvetica-Bold', italic='Helvetica-Oblique', boldItalic='Helvetica-BoldOblique')
            elif base_font_name == 'Times-Roman':
                pdfmetrics.registerFontFamily('Times-Roman', normal='Times-Roman', bold='Times-Bold', italic='Times-Italic', boldItalic='Times-BoldItalic')
            elif base_font_name == 'Courier':
                pdfmetrics.registerFontFamily('Courier', normal='Courier', bold='Courier-Bold', italic='Courier-Oblique', boldItalic='Courier-BoldOblique')
        except Exception as e:
            print(f"Could not register font family {base_font_name}: {e}")

    def setup_custom_styles(self):
        style_vars = self.vars.get("styles", {})
        for name, properties in style_vars.items():
            alignment = ALIGNMENT_MAP.get(str(properties.get("alignment", "left")).lower(), TA_LEFT)
            font_name = properties.get("fontName", self.base_font)
            self.styles.add(ParagraphStyle(
                name=name.capitalize(),
                parent=self.styles['Normal'],
                fontName=font_name,
                fontSize=properties.get("fontsize", 10),
                spaceAfter=properties.get("spaceAfter", 2),
                spaceBefore=properties.get("spaceBefore", 2),
                leftIndent=properties.get("leftIndent", 0),
                bulletIndent=properties.get("bulletIndent", 0),
                alignment=alignment,
                leading=properties.get("fontsize", 10) * 1.2
            ))

    def create_contact_info(self, contact_data):
        parts = []
        if 'location' in contact_data: parts.append(f"{contact_data['location']} (open to relocation)")
        if 'email' in contact_data: parts.append(f'<link href="mailto:{contact_data["email"]}" color="black">{contact_data["email"]}</link>')
        if 'phone' in contact_data: parts.append(contact_data['phone'])
        if 'linkedin' in contact_data: parts.append(f"""<link href="{contact_data["linkedin"]}" color="black">{contact_data["linkedin"].split('www.')[1]}</link>""")
        if 'github' in contact_data: parts.append(f"""<link href="{contact_data["github"]}" color="black">{contact_data["github"].split('://')[1]}</link>""")
        if 'medium' in contact_data: parts.append(f"""<link href="{contact_data["medium"]}" color="black">{contact_data["medium"].split('://')[1]}</link>""")
        return ' • '.join(parts)

    def add_section_header(self, story, title):
        hr_vars = self.vars.get("styles", {}).get("horizontal_line", {})
        story.append(Paragraph(f"<b>{title.upper()}</b>", self.styles['Header']))
        story.append(HRFlowable(width="100%", thickness=hr_vars.get("thickness", 0.5), color=colors.black, spaceBefore=hr_vars.get("spaceBefore", 3), spaceAfter=hr_vars.get("spaceAfter", 3)))

    def create_two_part_line(self, left_text, right_text, left_bold=False, separation_key=None):
        l_text = f"<b>{left_text}</b>" if left_bold else left_text
        r_text = f"<i>{right_text}</i>"
        separation = self.vars.get("spaces", {}).get("horizontal", {}).get(separation_key, 100)
        separator = '&nbsp;' * separation
        return Paragraph(f"{l_text}{separator}{r_text}", self.styles['Subheader'])

    def get_trimmed_skills_list(self, category: str, skills: List[str], style: ParagraphStyle, max_width: float) -> List[str]:
        """
        Calculates the list of skills that fit within the max_width and returns the list.
        """
        base_text = f"<b>{category}:</b> "
        current_skills = list(skills)

        while True:
            if not current_skills:
                # If even the category title doesn't fit, return an empty list.
                p_cat_only = Paragraph(base_text, style)
                w, h = p_cat_only.wrap(max_width, 1000)
                return [] if h > style.leading * 1.5 else [""]

            test_text = base_text + ", ".join(current_skills)
            p = Paragraph(test_text, style)
            w, h = p.wrap(max_width, 1000)

            if h <= style.leading * 1.5: # Using a 1.5 tolerance for single line height
                return current_skills
            else:
                # If it wraps, remove the last skill and try again
                current_skills.pop()
    
    def preprocess_data_for_fitting(self, data: Dict, doc_width: float) -> Dict:
        """
        Preprocesses the resume data, trimming skills from categories that are too long
        to fit on a single line. Returns a deep copy of the modified data.
        """
        processed_data = copy.deepcopy(data)

        if 'skills' in processed_data and processed_data['skills']:
            skills_style = self.styles['Skills']
            padding = 10  # Safety padding in points
            max_width = doc_width - skills_style.leftIndent - skills_style.rightIndent - padding

            for skill_item in processed_data['skills']:
                for category, skills_list in skill_item.items():
                    if isinstance(skills_list, list):
                        # Get the list of skills that will fit on one line
                        trimmed_list = self.get_trimmed_skills_list(category, skills_list, skills_style, max_width)
                        # Update the dictionary with the trimmed list
                        skill_item[category] = trimmed_list
        
        return processed_data

    def generate_pdf_from_data(self, data: Dict, output_file: str):
        doc = SimpleDocTemplate(output_file, pagesize=letter, rightMargin=0.4*inch, leftMargin=0.4*inch, topMargin=0.4*inch, bottomMargin=0.4*inch)
        story = []
        
        v_spaces = self.vars.get("spaces", {}).get("vertical", {})
        section_gap = v_spaces.get("section_gap_inch", 0.01) * inch
        
        # --- Name and Contact ---
        if 'name' in data: story.append(Paragraph(f"<b>{data['name']}</b>", self.styles['Name']))
        if 'contact' in data: story.append(Paragraph(self.create_contact_info(data['contact']), self.styles['Contact']))

        # --- Summary ---
        if 'summary' in data and data['summary']:
            self.add_section_header(story, "Summary")
            story.append(Paragraph(data['summary'], self.styles['Summary']))
            story.append(Spacer(1, section_gap))

        # --- Education ---
        if 'education' in data and data['education']:
            self.add_section_header(story, "Education")
            for i, edu in enumerate(data['education']):
                story.append(self.create_two_part_line(edu['school'].upper(), edu['location'], left_bold=True, separation_key=f"education{i+1}"))
                degree_info = edu['degree'] + (f", GPA: {edu['gpa']}" if 'gpa' in edu else "")
                story.append(self.create_two_part_line(degree_info, edu['dates'], left_bold=False, separation_key=f"degree{i+1}"))
                if 'courses' in edu and edu['courses']: story.append(Paragraph(f"<b>Coursework:</b> {edu['courses']}", self.styles['Coursework']))
                if i < len(data['education']) - 1: story.append(Spacer(1, 0.05*inch))
            story.append(Spacer(1, section_gap))

        # --- Skills ---
        if 'skills' in data and data['skills']:
            self.add_section_header(story, "Technical Skills")
            skills_style = self.styles['Skills']
            for skill_item in data['skills']:
                for category, skills_list in skill_item.items():
                    if skills_list: # Render only if the list is not empty after trimming
                        full_text = f"<b>{category}:</b> " + ", ".join(skills_list)
                        story.append(Paragraph(full_text, skills_style))
            story.append(Spacer(1, section_gap))

        # --- Experience ---
        if 'experience' in data and data['experience']:
            self.add_section_header(story, "Professional Experience")
            for i, job in enumerate(data['experience']):
                story.append(self.create_two_part_line(job['company'].upper(), job['location'], left_bold=True, separation_key=f"company{i+1}"))
                story.append(self.create_two_part_line(job['title'], job['dates'], left_bold=False, separation_key=f"title{i+1}"))
                if 'bullets' in job:
                    for bullet in job['bullets']: story.append(Paragraph(bullet, self.styles['Bulleted_list'], bulletText='•'))
                if i < len(data['experience']) - 1: story.append(Spacer(1, 0.05*inch))
            story.append(Spacer(1, section_gap))

        # --- Projects ---
        if 'projects' in data and data['projects']:
            self.add_section_header(story, "Projects")
            for i, project in enumerate(data['projects']):
                story.append(Paragraph(f"<b>{project['title']}</b>", self.styles['Subheader']))
                if 'bullets' in project:
                    for bullet in project['bullets']: story.append(Paragraph(bullet, self.styles['Bulleted_list'], bulletText='•'))
                if i < len(data['projects']) - 1: story.append(Spacer(1, 0.05*inch))
            story.append(Spacer(1, section_gap))
            
        # --- Certifications ---
        if 'certifications' in data and data['certifications']:
            self.add_section_header(story, "Certifications")
            for cert in data['certifications']:
                story.append(Paragraph(f"<b>{cert['title']}</b> - <i>{cert['issuer']} ({cert['date']})</i>", self.styles['Subheader']))
                if 'description' in cert and cert['description']:
                    for desc_bullet in cert['description']: story.append(Paragraph(desc_bullet, self.styles['Bulleted_list'], bulletText='-'))

        doc.build(story)
        print(f"ATS-optimized resume generated: {output_file}")

class CoverLetterPDFGenerator:
    def __init__(self, variables: Dict):
        self.vars = variables
        self.styles = getSampleStyleSheet()
        self.base_font = self.vars.get("font_settings", {}).get("base_font_name", "Helvetica")
        
        self.register_font_family(self.base_font)
        self.setup_custom_styles()

    def register_font_family(self, base_font_name: str):
        try:
            if base_font_name == 'Helvetica':
                pdfmetrics.registerFontFamily('Helvetica', normal='Helvetica', bold='Helvetica-Bold', italic='Helvetica-Oblique', boldItalic='Helvetica-BoldOblique')
            elif base_font_name == 'Times-Roman':
                pdfmetrics.registerFontFamily('Times-Roman', normal='Times-Roman', bold='Times-Bold', italic='Times-Italic', boldItalic='Times-BoldItalic')
            elif base_font_name == 'Courier':
                pdfmetrics.registerFontFamily('Courier', normal='Courier', bold='Courier-Bold', italic='Courier-Oblique', boldItalic='Courier-BoldOblique')
        except Exception as e:
            print(f"Could not register font family {base_font_name}: {e}")

    def setup_custom_styles(self):
        self.styles.add(ParagraphStyle(name='CoverLetterBody', parent=self.styles['Normal'], fontName=self.base_font, fontSize=11, leading=14, spaceAfter=12))
        self.styles.add(ParagraphStyle(name='Signature', parent=self.styles['Normal'], fontName=self.base_font, fontSize=11))
        self.styles.add(ParagraphStyle(name='CoverLetterContact', parent=self.styles['Normal'], fontName=self.base_font, fontSize=9, leading=12, alignment=TA_LEFT))

    def generate_pdf(self, body_text: str, contact_info: Dict, output_file: str):
        doc = SimpleDocTemplate(output_file, pagesize=letter, rightMargin=inch, leftMargin=inch, topMargin=inch, bottomMargin=inch)
        story = []
        
        paragraphs = body_text.strip().split('\\n\\n')
        for para_text in paragraphs:
            story.append(Paragraph(para_text.replace('\\n', '<br/>'), self.styles['CoverLetterBody']))
        
        story.append(Spacer(1, 0.25 * inch))
        story.append(Paragraph("Yours sincerely,", self.styles['CoverLetterBody']))
        story.append(Spacer(1, 0.2 * inch))
        story.append(Paragraph("Sri Manikesh Makam", self.styles['Signature']))
        story.append(Spacer(1, 0.1 * inch))

        contact_parts = []
        if 'email' in contact_info: contact_parts.append(f'<link href="mailto:{contact_info["email"]}" color="blue">{contact_info["email"]}</link>')
        if 'phone' in contact_info: contact_parts.append(f'<link href="tel:{contact_info["phone"]}" color="blue">{contact_info["phone"]}</link>')
        if 'linkedin' in contact_info: contact_parts.append(f'<link href="{contact_info["linkedin"]}" color="blue">LinkedIn</link>')
        if 'github' in contact_info: contact_parts.append(f'<link href="{contact_info["github"]}" color="blue">Github</link>')
        if 'medium' in contact_info: contact_parts.append(f'<link href="{contact_info["medium"]}" color="blue">Medium</link>')
        
        contact_line = ' | '.join(contact_parts)
        story.append(Paragraph(contact_line, self.styles['CoverLetterContact']))

        doc.build(story)
        print(f"Cover letter generated: {output_file}")