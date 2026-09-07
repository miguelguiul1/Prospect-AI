import type { NextConfig } from "next";

// Headers de segurança básicos (Fase 8.3 — achado R6 da auditoria F8.0:
// zero ocorrência de qualquer header de segurança em todo o frontend).
// Sem Content-Security-Policy própria: o app usa poucos scripts externos
// (nenhum, hoje) e uma CSP mal ajustada quebraria silenciosamente algo em
// produção sem o mesmo nível de teste que o resto do projeto tem — melhor
// não adicionar uma CSP não testada do que adicionar uma errada. Avaliar
// como item futuro quando houver superfície real (embeds, scripts de
// terceiro) que justifique o ajuste fino.
const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Strict-Transport-Security", value: "max-age=31536000; includeSubDomains" },
];

const nextConfig: NextConfig = {
  async headers() {
    return [
      {
        source: "/:path*",
        headers: securityHeaders,
      },
    ];
  },
};

export default nextConfig;
