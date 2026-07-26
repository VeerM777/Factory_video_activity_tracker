# ==========================================
# Stage 1: Build the React Frontend
# ==========================================
FROM node:22-alpine AS frontend-builder
WORKDIR /app/frontend

# Copy frontend package files
COPY frontend/package*.json ./
RUN npm install


# Copy the rest of the frontend source
COPY frontend/ ./
# Build the production React static bundle (outputs to /app/frontend/dist)
RUN npm run build

# ==========================================
# Stage 2: Build the Python FastAPI Backend
# ==========================================
FROM python:3.11-slim AS production

# Install system dependencies (OpenCV requires libglib2.0-0, though we use headless)
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libxcb1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy backend requirements
COPY backend/requirements.txt ./backend/
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy backend source code and config
COPY backend/ ./backend/
COPY data/ ./data/

# Copy compiled frontend from Stage 1 into the production image
# FastAPI in backend/app/main.py is configured to serve this directory
COPY --from=frontend-builder /app/frontend/dist /app/frontend/dist

# Expose Railway's dynamic PORT
EXPOSE $PORT

# Start the uvicorn server serving both backend API and frontend static files
CMD ["sh", "-c", "cd backend && python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
