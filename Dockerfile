FROM node:22-alpine
WORKDIR /app
ENV NODE_ENV=production
COPY package*.json ./
COPY packages ./packages
COPY apps ./apps
COPY tsconfig.json tsconfig.base.json ./
COPY bpb-fork ./bpb-fork
RUN npm ci --include=dev && npm run build && npm prune --omit=dev
EXPOSE 3000
CMD ["node", "apps/api/dist/server.js"]
