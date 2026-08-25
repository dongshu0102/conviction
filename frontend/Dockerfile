FROM node:22-slim AS deps
WORKDIR /app
# Both files copied, and npm ci (not npm install) used deliberately --
# a real, live build failure was traced directly to this gap tonight:
# without package-lock.json in the build context, npm install
# silently re-resolves every dependency version fresh from whatever's
# currently on the npm registry at build time, completely ignoring the
# exact, pinned versions in the committed lockfile. That made builds
# genuinely non-deterministic -- the same commit succeeded once, then
# failed later when a transitive dependency's specific pinned version
# had since been removed from the registry. npm ci strictly honors the
# lockfile and never re-resolves, which is exactly what CI/production
# builds need.
COPY package.json package-lock.json ./
RUN npm ci
FROM node:22-slim AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# Baked in at build time — this becomes part of the client bundle, since
# NEXT_PUBLIC_ vars are inlined during build, not read at runtime. If the
# API's URL ever changes, this image needs rebuilding, not just redeploying.
ARG NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
RUN npm run build
FROM node:22-slim AS runner
WORKDIR /app
ENV NODE_ENV=production
RUN useradd --create-home appuser
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
USER appuser
EXPOSE 8000
ENV PORT=8000
ENV HOSTNAME=0.0.0.0
CMD ["node", "server.js"]
