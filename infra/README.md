# Infraestrutura

## Onde está o `docker-compose.yml`

O arquivo vive na **raiz do repositório**, não nesta pasta. Isso é uma
adaptação deliberada em relação à árvore de exemplo do prompt de
implementação da Fase 0 (que sugeria `infra/docker-compose.yml`): o Docker
Compose procura automaticamente por `docker-compose.yml` no diretório atual,
então mantê-lo na raiz permite `docker compose up` sem `-f infra/...`,
que é a experiência de "um comando só" que a Fase 0 pede.

Esta pasta (`infra/`) fica reservada para o que vier depois de um único
Compose de desenvolvimento — configuração de produção, scripts de
provisionamento, ou definições específicas de um provedor de hospedagem.
Nenhuma dessas coisas existe ainda na Fase 0.

## Serviços do ambiente de desenvolvimento

| Serviço  | Imagem            | Porta local |
|----------|-------------------|-------------|
| postgres | postgres:16-alpine| 5432        |
| redis    | redis:7-alpine    | 6379        |
| backend  | build local (`backend/Dockerfile`) | 8000 |

## Estado de validação

Este `docker-compose.yml` **não foi executado** durante a implementação da
Fase 0: a máquina usada não tem Docker instalado (ver README.md, seção
"Limitações conhecidas desta Fase 0"). A sintaxe foi revisada manualmente,
mas alguém com Docker disponível precisa rodar `docker compose up` e
confirmar que os três serviços sobem e o `backend` consegue migrar e
responder em `/health` antes de considerar este critério de conclusão
fechado.
