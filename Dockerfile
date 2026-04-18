FROM node:22-alpine AS builder

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY tsconfig.json ./
COPY src ./src
COPY config ./config

RUN npm run build


FROM node:22-alpine AS runtime

WORKDIR /app

COPY package*.json ./
RUN npm ci --omit=dev

COPY --from=builder /app/dist ./dist
COPY --from=builder /app/config ./config

ENV NODE_ENV=production

EXPOSE 3000

CMD ["node", "dist/server.js"]
