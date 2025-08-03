from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from typing import Dict

class ATSResumePDFGenerator:
    def __init__(self):
        self.styles = getSampleStyleSheet()
        self.setup_custom_styles()

    def setup_custom_styles(self):
        self.styles.add(ParagraphStyle(
            name='NameStyle', 
            parent=self.styles['Normal'], 
            fontSize=16, spaceAfter=7,
            spaceBefore=0,
            alignment=TA_CENTER, 
            fontName='Helvetica-Bold'))
        
        self.styles.add(ParagraphStyle(
            name='ContactStyle',
            parent=self.styles['Normal'],
            fontSize=9, spaceAfter=2,
            alignment=TA_CENTER,
            fontName='Helvetica'))
        
        self.styles.add(ParagraphStyle(
            name='SectionHeader',
            parent=self.styles['Normal'],
            fontSize=11,
            spaceAfter=0,
            spaceBefore=3,
            fontName='Helvetica-Bold'))
        
        self.styles.add(ParagraphStyle(
            name='Coursework',
            parent=self.styles['Normal'],
            fontSize=9,
            spaceAfter=0,
            leftIndent=15,
            fontName='Helvetica'))
        
        self.styles.add(ParagraphStyle(
            name='BulletPoint',
            parent=self.styles['Normal'],
            fontSize=9,
            spaceAfter=0,
            leftIndent=12,
            bulletIndent=0,
            fontName='Helvetica'))
        
        self.styles.add(ParagraphStyle(
            name='ContentStyle',
            parent=self.styles['Normal'],
            fontSize=9,
            spaceAfter=0,
            fontName='Helvetica'))
        
        self.styles.add(ParagraphStyle(
            name='ProjectTitle',
            parent=self.styles['Normal'],
            fontSize=10,
            spaceBefore=1,
            spaceAfter=1,
            fontName='Helvetica'))

    def create_contact_info(self, contact_data):
        """Formats the contact information into a single line."""
        contact_parts = []
        if 'location' in contact_data:
            contact_parts.append(f"{contact_data['location']} (open to relocation)")
        if 'email' in contact_data:
            contact_parts.append(f'<link href="mailto:{contact_data["email"]}" color="blue">{contact_data["email"]}</link>')
        if 'phone' in contact_data:
            contact_parts.append(contact_data['phone'])
        if 'linkedin' in contact_data:
            contact_parts.append(f'<link href="{contact_data["linkedin"]}" color="blue">LinkedIn</link>')
        if 'github' in contact_data:
            contact_parts.append(f'<link href="{contact_data["github"]}" color="blue">Github</link>')
        if 'medium' in contact_data:
            contact_parts.append(f'<link href="{contact_data["medium"]}" color="blue">Medium</link>')
        return ' • '.join(contact_parts)

    def add_section_header(self, story, title):
        # Header
        story.append(Paragraph(f"<b>{title.upper()}</b>", 
                               self.styles['SectionHeader']))

        # Horizontal line
        story.append(HRFlowable(width="100%",
                                thickness=0.5,
                                color=colors.black,
                                spaceBefore=3,
                                spaceAfter=3))

    def create_two_part_line(self, left_text, right_text, left_bold=False,
                             seperation=100):
        """Used for 
            1. Education & Location
            2. Degree & Dates
            3. Company & Location
            4. Title and Dates."""
        
        # Bold on left and Italics on right part
        l_text = f"<b>{left_text}</b>" if left_bold else left_text
        r_text = f"<i>{right_text}</i>"

        # Gap between left and right text
        separator = '&nbsp;' * seperation

        return Paragraph(f"{l_text}{separator}{r_text}", self.styles['ProjectTitle'])

    def generate_pdf_from_data(self, data: Dict, output_file: str):
        """Generates a PDF from the provided resume data."""
        # Margins and page size
        doc = SimpleDocTemplate(output_file, pagesize=letter, rightMargin=0.4*inch, leftMargin=0.4*inch, topMargin=0.4*inch, bottomMargin=0.4*inch)
        story = []
        # Name
        story.append(Paragraph(data['name'], self.styles['NameStyle']))

        # Contact Info
        contact_info = self.create_contact_info(data['contact'])
        story.append(Paragraph(contact_info, self.styles['ContactStyle']))

        # Education
        if 'education' in data:
            self.add_section_header(story, "Education")
            for i, edu in enumerate(data['education']):
                story.append(self.create_two_part_line(edu['school'].upper(),
                                                       edu['location'],
                                                       left_bold=True,
                                                       n=105 if i==0 else 84))
                
                degree_info = edu['degree'] + (f", GPA: {edu['gpa']}" if 'gpa' in edu else "")
                story.append(self.create_two_part_line(degree_info, edu['dates'], left_bold=False, n=106 if i==0 else 81))
                if 'details' in edu:
                    story.append(Paragraph(f"<b>Coursework:</b> {edu['details']}", self.styles['Coursework']))
                story.append(Spacer(0, 4))

        if 'skills' in data:
            self.add_section_header(story, "Technical Skills")
            for category, skills_list in data['skills'].items():
                if isinstance(skills_list, list):
                    skills_str = ", ".join(skills_list)
                    story.append(Paragraph(f"<b>{category}:</b> {skills_str}", self.styles['ContentStyle']))

        if 'experience' in data:
            self.add_section_header(story, "Professional Experience")
            for i, job in enumerate(data['experience']):
                story.append(self.create_two_part_line(job['company'].upper(), job['location'], left_bold=True, n=150))
                story.append(self.create_two_part_line(job['title'], job['dates'], left_bold=False, n=139))
                if 'bullets' in job:
                    for bullet in job['bullets']:
                        story.append(Paragraph(f"• {bullet}", self.styles['BulletPoint']))
                story.append(Spacer(0, 4))

        if 'projects' in data:
            self.add_section_header(story, "Projects")
            for project in data['projects']:
                story.append(Paragraph(f"<b>{project['title']}</b>", self.styles['ProjectTitle']))
                if 'bullets' in project:
                    for bullet in project['bullets']:
                        story.append(Paragraph(f"• {bullet}", self.styles['BulletPoint']))
                story.append(Spacer(0, 4))

        if 'certifications' in data:
            self.add_section_header(story, "Certifications")
            for cert in data['certifications']:
                story.append(Paragraph(f"• {cert}", self.styles['ContentStyle']))

        doc.build(story)
        print(f"ATS-optimized resume generated: {output_file}")
