from fastapi import FastAPI, File, UploadFile
from fastapi.responses import JSONResponse
import shutil, os, re, json
from pathlib import Path
import spacy
import fitz
from PIL import Image
import pytesseract

# Load spaCy model once
model_path = "./model/nlp_ner_model"
nlp = spacy.load(model_path)

app = FastAPI(title="Resume Parser API")

def extract_text_from_pdf(pdf_path):
    text = ""
    doc = fitz.open(pdf_path)
    for page in doc:
        text += page.get_text()
    return text

def extract_text_from_image(image_path):
    img = Image.open(image_path)
    return pytesseract.image_to_string(img)

def extract_text_from_file(file_path):
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".pdf":
        return extract_text_from_pdf(file_path)
    elif ext in [".png", ".jpg", ".jpeg"]:
        return extract_text_from_image(file_path)
    elif ext == ".txt":
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    else:
        raise ValueError("Unsupported file type. Use PDF, PNG, JPG, or TXT.")

def process_resume_file(file_path):
    resume_txt = extract_text_from_file(file_path)
    structured_data = {}
    # spaCy NER
    doc = nlp(resume_txt)
    for ent in doc.ents:
        label = ent.label_.strip().title()
        text_val = ent.text.strip().replace("\n", " ")
        if label.lower() == "skills":
            skills = [s.strip() for s in re.split(r"[:,]", text_val) if s.strip()]
            text_val = skills
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

   # Regex-based extraction
    emails = re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", resume_txt)
    if emails: structured_data["Email"] = emails if len(emails) > 1 else emails[0]
    phones = re.findall(r"\b\d{7,15}\b", resume_txt)
    if phones: structured_data["Phone"] = phones if len(phones) > 1 else phones[0]
    years = re.findall(r"\b(19|20)\d{2}\b", resume_txt)
    if years: structured_data["Years"] = list(set(years))
    languages = re.findall(r"\b(English|French|Arabic|German|Spanish)\b", resume_txt, re.IGNORECASE)
    if languages: structured_data["Languages"] = list(set(languages))

    return structured_data

@app.post("/parse_resume/")
async def parse_resume(file: UploadFile = File(...)):
    try:
        temp_dir = Path("temp_uploads")
        temp_dir.mkdir(exist_ok=True)
        file_path = temp_dir / file.filename
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        result = process_resume_file(str(file_path))
        file_path.unlink()
        return JSONResponse(content={"success": True, "data": result})
    except Exception as e:
        return JSONResponse(content={"success": False, "error": str(e)})
