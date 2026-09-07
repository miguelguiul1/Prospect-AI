"""Função de job mínima e IMPORTÁVEL POR CAMINHO DE MÓDULO (RQ exige isso —
não pode ser definida inline em um teste nem em `__main__`) usada só para
provar que o mecanismo enqueue→worker→execução funciona, antes de testar a
integração com o código real do projeto em `test_worker_integration.py`.
"""
from __future__ import annotations


def add(x: int, y: int) -> int:
    return x + y


def raise_value_error(message: str) -> None:
    raise ValueError(message)
