"""Identity Resolution: ligação entre Company e fontes externas.

Fase 0 cria apenas as entidades (`CompanySource`, `IdentityMergeLog`)
descritas na arquitetura v0.2, seção 07. Nenhuma regra de correspondência,
fusão automática ou fila de deduplicação é implementada — isso é escopo da
Fase 2 (Identity Resolution + deduplicação).
"""
