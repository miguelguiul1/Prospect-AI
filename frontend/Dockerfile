# Multi-stage — usa o build "standalone" do Next.js (habilitado em
# next.config.ts, Fase 8.4) para um runtime final enxuto, sem precisar do
# `node_modules` completo nem do código-fonte no container de produção.
#
# NOTA: esta imagem AINDA não foi construída nem executada em nenhuma
# sessão deste projeto — nenhuma máquina usada até aqui (Fases 0-8) tem
# Docker disponível. `npm run build` com `output: "standalone"` foi
# validado localmente (gera `.next/standalone/server.js` corretamente);
# o build da imagem em si permanece NÃO VALIDADO. Ver
# docs/production-readiness.md.

FROM node:22-slim AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:22-slim AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:22-slim AS runner
WORKDIR /app
ENV NODE_ENV=production \
    PORT=3000 \
    HOSTNAME=0.0.0.0

# Usuário não-root — mesma prática básica de segurança de qualquer imagem
# de produção, sem custo de complexidade adicional.
RUN addgroup --system --gid 1001 nodejs && adduser --system --uid 1001 nextjs

COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs
EXPOSE 3000

HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
  CMD node -e "require('http').get('http://localhost:3000/login', r => process.exit(r.statusCode < 500 ? 0 : 1)).on('error', () => process.exit(1))"

CMD ["node", "server.js"]
