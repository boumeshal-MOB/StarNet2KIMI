# BTM Topographic Adjustment — full-stack image
# Stage 1: build the React frontend
FROM node:20-slim AS frontend
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install --no-audit --no-fund
COPY . .
RUN npm run build

# Stage 2: Python backend + scientific core + built frontend
FROM python:3.12-slim
WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ backend/
COPY --from=frontend /app/dist ./dist

ENV BTM_DATABASE_URL=sqlite:////app/backend/data/btm_demo.sqlite
EXPOSE 8000

WORKDIR /app/backend
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
