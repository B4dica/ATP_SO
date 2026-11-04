"""
Módulo: depois/main.py
Ponto de entrada da versão DEPOIS (banco de dados SQLite com controle de concorrência).
"""

from .servidor import ServidorDepois


def main():
    servidor = ServidorDepois()
    servidor.executar_todos()


if __name__ == "__main__":
    main()
