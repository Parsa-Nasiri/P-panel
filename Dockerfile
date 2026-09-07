FROM node:22-alpine AS build
WORKDIR /app
COPY package*.json ./
COPY packages/*/package.json ./packages/
COPY apps/*/package.json ./apps/
RUN npm ci
COPY . .
RUN npm run typecheck && npm run build

FROM node:22-alpine
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build /app/package*.json ./
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/packages ./packages
COPY --from=build /app/apps ./apps
CMD ["node", "apps/api/dist/server.js"]
