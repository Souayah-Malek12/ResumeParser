from fastapi import FastAPI, File, UploadFile
from fastapi.responses import JSONResponse
import spacy
import re
import fitz  # PyMuPDF
from PIL import Image
import shutil
from pathlib import Path
import requests

app = FastAPI()

# Load spaCy model
nlp = spacy.load("./model/nlp_ner_model")

def extract_text_from_pdf(pdf_path):
    """Extract text from PDF file using PyMuPDF"""
    text = ""
    doc = fitz.open(pdf_path)
    for page in doc:
        text += page.get_text()
    doc.close()
    return text

def extract_text_from_image(image_path):
    """Extract text from image using OCR.space API"""
    try:
        with open(image_path, 'rb') as f:
            response = requests.post(
                'https://api.ocr.space/parse/image',
                files={'file': f},
                data={
                    'apikey': '98b036885a88957', 
                    'language': 'eng',
                    'isOverlayRequired': False
                },
                timeout=30
            )
        
        if response.status_code == 200:
            result = response.json()
            if result.get('ParsedResults') and len(result['ParsedResults']) > 0:
                text = result['ParsedResults'][0].get('ParsedText', '')
                # Return empty string if no meaningful text extracted
                if text and len(text.strip()) > 10:
                    return text
        
        return ""
        
    except Exception as e:
        # Return empty string instead of error message to prevent it from being processed
        return ""

def extract_text_from_file(file_path):
    """Extract text from various file formats"""
    file_path = Path(file_path)
    
    if file_path.suffix.lower() == '.pdf':
        return extract_text_from_pdf(str(file_path))
    elif file_path.suffix.lower() in ['.png', '.jpg', '.jpeg', '.tiff', '.bmp']:
        return extract_text_from_image(str(file_path))
    elif file_path.suffix.lower() == '.txt':
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    else:
        return "Unsupported file format"

def extract_name_from_email(emails):
    """Extract name from email address"""
    if not emails:
        return None
    
    email = emails[0] if isinstance(emails, list) else emails
    username = email.split('@')[0].lower()
    
    # Clean username: remove numbers, dots, underscores, hyphens
    username = re.sub(r'[\d_\-\.]+', ' ', username)
    name_parts = [part.strip() for part in username.split() if len(part) > 1]
    
    # Filter out common non-name patterns
    filtered_parts = []
    skip_patterns = ['info', 'admin', 'contact', 'support', 'sales', 'hr', 'team', 'mail', 'email']
    
    for part in name_parts:
        if part not in skip_patterns and len(part) > 1:
            filtered_parts.append(part.capitalize())
    
    if len(filtered_parts) >= 2:
        return ' '.join(filtered_parts)
    elif len(filtered_parts) == 1 and len(filtered_parts[0]) > 2:
        return filtered_parts[0]
    
    return None

def process_resume_file(file_path):
    """Process resume file and extract structured data"""
    resume_txt = extract_text_from_file(file_path)
    structured_data = {}
    
    # Process with spaCy NER
    doc = nlp(resume_txt)
    
    # Extract entities from NER
    for ent in doc.ents:
        label = ent.label_.strip().title()
        text_val = ent.text.strip().replace("\n", " ").replace("  ", " ")
        
        # Filter out noise and irrelevant entities
        if (len(text_val) < 3 or text_val.isdigit() or 
            any(word in text_val.lower() for word in ['inc', 'llc', 'corp', 'ltd', 'consultant', 
                'associate', 'representative', 'ambassador', 'design', 'sales', 'target', 
                'phone', 'address', 'jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 
                'sep', 'oct', 'nov', 'dec', 'january', 'february', 'march', 'april', 'june', 
                'july', 'august', 'september', 'october', 'november', 'december']) or
            re.search(r'\b(phone|number|address|full|target|inc|llc|corp|ltd|consultant|associate|representative|ambassador|design|sales|engaged|represented|periscope|iron|range|spa|brand|graphic)\b', text_val, re.IGNORECASE)):
            continue
        
        # Handle skills extraction
        if label.lower() == "skills":
            skills = [s.strip() for s in re.split(r"[:,]", text_val) if s.strip()]
            text_val = skills
        
        # Store person/name entities
        if label in ["Person", "Name"] and "Name" not in structured_data:
            structured_data["Name"] = text_val
        elif label in ["Skills"] and not any(word in text_val.lower() for word in ['target', 'phone', 'address', 'state']):
            if label in structured_data:
                if isinstance(structured_data[label], list):
                    if isinstance(text_val, list):
                        structured_data[label].extend(text_val)
                    else:
                        structured_data[label].append(text_val)
                else:
                    structured_data[label] = [structured_data[label], text_val]
            else:
                structured_data[label] = text_val
    
    # Extract emails using regex
    emails = re.findall(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', resume_txt)
    if emails:
        structured_data["Email"] = emails if len(emails) > 1 else emails[0]
        
        # Extract name from email if no name found yet
        if "Name" not in structured_data:
            email_name = extract_name_from_email(emails)
            if email_name:
                structured_data["Name"] = email_name
    
    # Extract phone numbers
    phone_patterns = [
        r'\+?\d{1,3}[-.\s]?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}',
        r'\+?\d{1,3}[-.\s]?\d{2,4}[-.\s]?\d{2,4}[-.\s]?\d{2,4}',
        r'\b\d{10,15}\b'
    ]
    phones = []
    for pattern in phone_patterns:
        phones.extend(re.findall(pattern, resume_txt))
    if phones:
        structured_data["Phone"] = list(set(phones)) if len(phones) > 1 else phones[0]
    
    # Extract years
    years = re.findall(r'\b(19|20)\d{2}\b', resume_txt)
    if years:
        structured_data["Years"] = sorted(list(set(years)))
    
    # Extract languages
    languages = re.findall(r'\b(English|French|Arabic|German|Spanish|Italian|Portuguese|Russian|Chinese|Japanese|Korean|Hindi|Dutch|Swedish|Norwegian|Danish)\b', resume_txt, re.IGNORECASE)
    if languages:
        structured_data["Languages"] = list(set([lang.title() for lang in languages]))
    
    # Extract degrees
    degree_patterns = [
        r'\b(Bachelor(?:\s+of\s+\w+)?|Master(?:\s+of\s+\w+)?|PhD|Doctorate|B\.?Tech|M\.?Tech|B\.?E\.?|M\.?E\.?|B\.?A\.?|M\.?A\.?|B\.?S\.?|M\.?S\.?|MBA)\b(?:\s+in\s+[\w\s,]+)?',
        r'\b(B\.?Tech|M\.?Tech|B\.?E\.?|M\.?E\.?)\s*,?\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)'
    ]
    degrees = []
    for pattern in degree_patterns:
        matches = re.findall(pattern, resume_txt, re.IGNORECASE)
        if matches:
            for match in matches:
                if isinstance(match, tuple):
                    degree_text = ' '.join(filter(None, match))
                else:
                    degree_text = match
                degrees.append(degree_text.strip())
    if degrees:
        structured_data["Degree"] = degrees if len(degrees) > 1 else degrees[0]
    
    # Extract education institutions
    education_keywords = re.findall(r'\b(University|College|Institute|School)\s+of\s+[\w\s]+|[\w\s]+\s+(University|College|Institute)\b', resume_txt, re.IGNORECASE)
    if education_keywords:
        edu_list = []
        for match in education_keywords:
            if isinstance(match, tuple):
                edu_text = ' '.join(filter(None, match))
            else:
                edu_text = match
            edu_list.append(edu_text.strip().title())
        structured_data["Education"] = list(set(edu_list))
    
    # Extract technical skills
    tech_skills = re.findall(r'\b(Python|Java|JavaScript|C\+\+|SQL|HTML|CSS|React|Angular|Node\.js|Django|Flask|AWS|Docker|Kubernetes|Git|Machine Learning|AI|Data Science|Pandas|NumPy|TensorFlow|PyTorch|Scikit-learn|OpenCV|Matplotlib|Seaborn|Jupyter|Anaconda|Linux|Windows|MacOS|MongoDB|PostgreSQL|MySQL|Redis|Elasticsearch|Apache|Nginx|Jenkins|Terraform|Ansible|Spark|Hadoop|Kafka|RabbitMQ|GraphQL|REST|API|Microservices|DevOps|CI/CD|Agile|Scrum|JIRA|Confluence|Slack|Teams|Zoom|Excel|PowerPoint|Word|Photoshop|Illustrator|Figma|Sketch|InDesign|Premiere|After Effects|Blender|Unity|Unreal|C#|C|Go|Rust|Swift|Kotlin|Dart|Flutter|React Native|Vue|Svelte|Bootstrap|Tailwind|SASS|LESS|Webpack|Vite|Babel|ESLint|Prettier|Jest|Cypress|Selenium|Postman|Insomnia|Swagger|GraphiQL|Prisma|Sequelize|Mongoose|Knex|Express|FastAPI|Spring|Laravel|Ruby on Rails|Phoenix|Gin|Echo|Fiber|Actix|Warp|Rocket|Axum)\b', resume_txt, re.IGNORECASE)
    if tech_skills:
        if "Skills" in structured_data:
            if isinstance(structured_data["Skills"], list):
                structured_data["Skills"].extend([skill.title() for skill in tech_skills])
            else:
                structured_data["Skills"] = [structured_data["Skills"]] + [skill.title() for skill in tech_skills]
        else:
            structured_data["Skills"] = [skill.title() for skill in tech_skills]
        
        # Deduplicate skills
        if isinstance(structured_data["Skills"], list):
            structured_data["Skills"] = list(set([skill for skill in structured_data["Skills"] if len(skill) > 1]))
    
    # Extract locations with improved filtering
    location_patterns = [
        r'\b([A-Z][a-z]{2,},\s*[A-Z]{2})\b',
        r'\b([A-Z][a-z]{2,}\s+[A-Z][a-z]{2,},\s*[A-Z]{2})\b'
    ]
    
    major_cities = ['New York', 'Los Angeles', 'Chicago', 'Houston', 'Phoenix', 'Philadelphia', 
                   'San Antonio', 'San Diego', 'Dallas', 'San Jose', 'Austin', 'Jacksonville', 
                   'San Francisco', 'Indianapolis', 'Columbus', 'Fort Worth', 'Charlotte', 
                   'Seattle', 'Denver', 'Washington', 'Boston', 'Nashville', 'Baltimore', 
                   'Portland', 'Oklahoma City', 'Las Vegas', 'Detroit', 'Memphis', 'Louisville', 
                   'Milwaukee', 'Albuquerque', 'Tucson', 'Fresno', 'Sacramento', 'Kansas City', 
                   'Atlanta', 'Miami', 'Colorado Springs', 'Raleigh', 'Virginia Beach', 'Omaha', 
                   'Oakland', 'Minneapolis', 'Tulsa', 'Arlington', 'Tampa', 'New Orleans']
    
    locations = []
    
    # Extract using patterns
    for pattern in location_patterns:
        matches = re.findall(pattern, resume_txt)
        locations.extend(matches)
    
    # Extract major cities with context validation
    for city in major_cities:
        city_pattern = rf'\b{re.escape(city)}\b(?:\s*,\s*[A-Z]{{2}})?\b'
        matches = re.findall(city_pattern, resume_txt)
        if matches:
            for match in matches:
                # Check context around the match
                context_start = max(0, resume_txt.find(match) - 50)
                context_end = min(len(resume_txt), resume_txt.find(match) + len(match) + 50)
                context = resume_txt[context_start:context_end].lower()
                
                # Skip if context contains business-related keywords
                if not any(keyword in context for keyword in ['inc', 'llc', 'corp', 'company', 
                          'consultant', 'associate', 'representative', 'target', 'periscope', 
                          'design', 'sales', 'ambassador']):
                    locations.append(match)
    
    # Apply comprehensive blacklist filtering
    location_blacklist = ['Target Inc', 'Phone Number', 'Representative', 'Associate', 'State', 
                         'Sales', 'John Doe', 'Consultant', 'Engaged University', 'Fashion', 
                         'College', 'Design', 'Represented Periscope', 'Full Address', 
                         'Iron Range', 'Spa', 'Brand', 'Ambassador', 'Graphic Design', 
                         'Data Science', 'Machine Learning', 'Computer Science', 
                         'Software Engineering', 'Web Development', 'Mobile Development', 
                         'Bachelor', 'Master', 'University', 'Institute', 'School', 'Education']
    
    locations = [loc.strip() for loc in locations if loc.strip() and len(loc.strip()) > 2 and 
                not any(blacklisted.lower() in loc.lower() for blacklisted in location_blacklist) and
                not re.search(r'\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|january|february|march|april|june|july|august|september|october|november|december)\b', loc, re.IGNORECASE)]
    
    if locations:
        unique_locations = list(set(locations))
        structured_data["Location"] = unique_locations if len(unique_locations) > 1 else unique_locations[0]
    
    return structured_data

@app.post("/parse_resume/")
async def parse_resume(file: UploadFile = File(...)):
    """API endpoint to parse resume files"""
    try:
        # Create temp directory
        temp_dir = Path("temp_uploads")
        temp_dir.mkdir(exist_ok=True)
        
        # Save uploaded file temporarily
        file_path = temp_dir / file.filename
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # Process the resume
        result = process_resume_file(str(file_path))
        
        # Clean up temp file
        file_path.unlink()
        
        return JSONResponse(content={"success": True, "data": result})
    
    except Exception as e:
        return JSONResponse(content={"success": False, "error": str(e)})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)