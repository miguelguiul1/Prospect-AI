"""Teste da seleção de classe do worker em `app/worker.py`.

Achado real desta sessão (não hipotético): `rq.Worker` padrão isola cada
job via `os.fork()` — inexistente no Windows. Rodando o worker de
produção pela primeira vez contra Redis real nesta sessão, ele crashou
com `AttributeError: module 'os' has no attribute 'fork'` no primeiro
job que tentou executar. `app.worker` agora seleciona `rq.SimpleWorker`
(sem fork, mesma classe que `tests/infra/test_real_worker.py` já usa) só
no Windows, preservando o isolamento por processo de `Worker` em produção
real (Linux).

**Por que isto testa `_select_worker_class` diretamente, não um
subprocesso com `sys.platform` forjado**: a primeira versão deste teste
usava subprocesso + `sys.platform` sobrescrito antes do `import rq` —
passou nesta máquina (Windows), mas quebrou no CI (Linux) com
`ModuleNotFoundError: No module named '_overlapped'`. Causa raiz (achado
real do CI, não hipotético): `sys.platform` é só uma string que o NOSSO
código lê — `asyncio` da biblioteca padrão decide `windows_events` vs
`unix_events` pelo SO real por outro caminho, e `_overlapped` (um módulo
compilado) só existe numa build real do Python para Windows. Forjar
`sys.platform` engana `app.worker`, mas não engana `asyncio` nem
qualquer outra dependência com detecção própria de plataforma — importar
`rq` (que acaba puxando `asyncio`) sob uma plataforma forjada é
inerentemente não-portável entre SOs reais diferentes. `rq` é importado
uma única vez aqui, no topo do arquivo, contra o SO real de verdade;
`_select_worker_class` só recebe strings e devolve uma classe já
importada — nunca reimporta nada."""
from __future__ import annotations

from app.worker import Worker, SimpleWorker, _select_worker_class


class TestWorkerClassSelection:
    def test_selects_simpleworker_for_windows_where_os_fork_does_not_exist(self) -> None:
        assert _select_worker_class("win32") is SimpleWorker

    def test_selects_worker_with_process_isolation_elsewhere(self) -> None:
        assert _select_worker_class("linux") is Worker
        assert _select_worker_class("darwin") is Worker
