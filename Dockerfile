# Minimal Dockerfile for Render deployment
# Ensures FFmpeg is available alongside Python + app dependencies

FROM python:3.11-slim

# Install FFmpeg via apt-get (available in Debian/Ubuntu-based slim images)
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user for security
RUN useradd --create-home appuser
WORKDIR /home/appuser/app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# Create downloads directory
RUN mkdir -p downloads && chown appuser:appuser downloads

USER appuser

# Expose port expected by Render
EXPOSE 10000

# Production WSGI server (Render maps $PORT automatically)
CMD ["gunicorn", "--bind", "0.0.0.0:10000", "--workers", "2", "--timeout", "120", "app:app"]
