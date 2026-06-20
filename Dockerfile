FROM node:18-alpine

WORKDIR /app
COPY frontend/package*.json ./
RUN npm ci
COPY . .
RUN npm run build