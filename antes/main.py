"""
Módulo: antes/main.py
Ponto de entrada da versão ANTES (sistema com falhas de concorrência).
"""

from .servidor import ServidorAntes


def main():
    servidor = ServidorAntes()
    servidor.executar_todos()


if __name__ == "__main__":
    main()
