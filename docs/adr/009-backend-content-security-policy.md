# ADR-009: Content-Security-Policy restritiva no backend, com exceção só para `/docs`/`/redoc`

**Status**: Aceita (Prompt 10, seção 2.1)

## Contexto

A Fase 8.3 adicionou headers de segurança (`X-Content-Type-Options`,
`X-Frame-Options`, `Referrer-Policy`, `Strict-Transport-Security`) mas
deliberadamente **não** incluiu uma Content-Security-Policy, com a
justificativa de que "esta é uma API JSON, não uma aplicação que renderiza
HTML". O relatório final da Fase 8 listou isto como um risco remanescente
a resolver quando não dependesse de infraestrutura real — este não
depende, é puramente código.

Ao investigar para esta fase, uma inspeção direta de `GET /docs`
confirmou que o backend **de fato serve HTML**: o Swagger UI do FastAPI
(ligado por padrão, nunca desligado explicitamente em nenhuma fase) carrega
CSS/JS de `cdn.jsdelivr.net`, um favicon de `fastapi.tiangolo.com`, e
executa um `<script>` inline para inicializar `SwaggerUIBundle`. Uma CSP
`default-src 'none'` sem exceção quebraria essa página.

## Decisão

Duas políticas, escolhidas por prefixo de path em
`SecurityHeadersMiddleware`:

- **Toda rota da API** (o caso comum): `default-src 'none'; frame-ancestors
  'none'; base-uri 'none'` — mais restritivo que o `default-src 'self'`
  sugerido como ponto de partida, porque uma resposta JSON nunca precisa
  carregar nenhum sub-recurso próprio. Sem `unsafe-inline`/`unsafe-eval`
  em lugar nenhum.
- **`/docs` e `/redoc`**: uma política mais permissiva, mas explícita e
  escopada — permite `script-src`/`style-src` de `cdn.jsdelivr.net` (+
  `'unsafe-inline'`, necessário para o `<script>` inline que o próprio
  FastAPI gera) e `img-src` de `fastapi.tiangolo.com`. Aceitável porque
  este HTML é gerado pelo próprio FastAPI (nunca por dado de usuário) —
  não é uma superfície de XSS refletido.

Nenhuma CSP foi adicionada ao frontend Next.js nesta fase — decisão
separada (F8.3) não revisitada aqui; o Prompt 10 pediu explicitamente CSP
"no mesmo `SecurityHeadersMiddleware`", que é backend.

## Consequências

- Toda resposta da API real (não `/docs`/`/redoc`) agora tem defesa em
  profundidade adicional contra o caso residual de um navegador acabar
  renderizando uma resposta como documento HTML (CSP não afeta chamadas
  fetch/XHR normais, só documentos renderizados).
- Se `/docs`/`/redoc` forem desativados no futuro (`docs_url=None` em
  `FastAPI(...)`, útil em produção para não expor a documentação
  publicamente), a exceção de CSP para essas rotas deixa de ter efeito
  algum — não precisa ser removida, mas pode ser, sem risco.
- Testado em `tests/test_security_hardening.py::TestContentSecurityPolicy`
  (4 testes): a política restritiva em respostas normais e de erro, e a
  política permissiva escopada em `/docs`/`/redoc`.
