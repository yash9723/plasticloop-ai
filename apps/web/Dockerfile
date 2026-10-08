# Build context: repository root (needs pnpm workspace + packages/*)
FROM node:22-bookworm-slim AS base
ENV PNPM_HOME=/pnpm PATH=/pnpm:$PATH NEXT_TELEMETRY_DISABLED=1
RUN corepack enable
WORKDIR /repo

FROM base AS deps
COPY pnpm-lock.yaml pnpm-workspace.yaml package.json ./
COPY apps/web/package.json apps/web/
COPY packages/design-tokens/package.json packages/design-tokens/
COPY packages/shared-schemas/package.json packages/shared-schemas/
RUN pnpm install --frozen-lockfile --filter "@plasticloop/web..."

FROM deps AS build
ARG API_INTERNAL_URL=http://api:8000
ENV API_INTERNAL_URL=$API_INTERNAL_URL NODE_ENV=production
COPY packages packages
COPY apps/web apps/web
RUN pnpm --filter @plasticloop/web build

FROM node:22-bookworm-slim AS runner
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
WORKDIR /app
RUN groupadd --gid 10001 web && useradd --uid 10001 --gid web --no-create-home web
COPY --from=build --chown=web:web /repo/apps/web/.next/standalone ./
COPY --from=build --chown=web:web /repo/apps/web/.next/static ./apps/web/.next/static
COPY --from=build --chown=web:web /repo/apps/web/public ./apps/web/public
USER web
EXPOSE 3000
CMD ["node", "apps/web/server.js"]
