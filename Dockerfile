FROM python:3.7-slim

# Prevents Python from writing .pyc files and enables unbuffered logging
ENV PYTHONUNBUFFERED=1

# Install system dependencies needed by spacy, pillow, pytesseract, pymupdf
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    tesseract-ocr \
    libtesseract-dev \
    poppler-utils \
    libjpeg-dev \
    zlib1g-dev \
    libpng-dev \
    libfreetype6-dev \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first (to leverage Docker layer caching)
COPY requirements.txt .

# Upgrade pip + tools, then install dependencies
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r requirements.txt

# Copy app code
COPY . .

# Create uploads directory
RUN mkdir -p temp_uploads

# Expose port
EXPOSE 8000

# Run FastAPI app with uvicorn
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
