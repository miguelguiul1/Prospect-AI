"""Teste da seleção de classe do worker em `app/worker.py`.

Achado real desta sessão (não hipotético): `rq.Worker` padrão isola cada
job via `os.fork()` — inexistente no Windows. Rodando o worker de
produção pela primeira vez contra Redis real nesta sessão, ele crashou
com `AttributeError: module 'os' has no attribute 'fork'` no primeiro
job que tentou executar. `app.worker` agora seleciona `rq.SimpleWorker`
(sem fork, mesma classe que `tests/infra/test_real_worker.py` já usa) só
no Windows, preservando o isolamento por processo de `Worker` em produção
real (Linux).

Via subprocesso, não monkeypatch de `sys.platform` no processo do pytest:
`_WorkerClass` é calculado uma vez, no import do módulo — testar as duas
plataformas no mesmo processo exigiria `importlib.reload` com o risco real
de vazar o estado de um teste para o outro (mesmo raciocínio de isolamento
de `tests/test_migrations_roundtrip.py`)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _worker_class_on(platform: str) -> str:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            f"import sys; sys.platform = {platform!r}; import app.worker; "
            "print(app.worker._WorkerClass.__name__)",
        ],
        cwd=str(BACKEND_DIR),
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, f"falhou para platform={platform!r}:\n{result.stdout}\n{result.stderr}"
    return result.stdout.strip()


class TestWorkerClassSelection:
    def test_uses_simpleworker_on_windows_where_os_fork_does_not_exist(self) -> None:
        assert _worker_class_on("win32") == "SimpleWorker"

    def test_uses_worker_with_process_isolation_elsewhere(self) -> None:
        assert _worker_class_on("linux") == "Worker"
