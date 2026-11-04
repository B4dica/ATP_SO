"""
Módulo: depois/main.py
Ponto de entrada da versão DEPOIS (sistema refatorado e seguro).
"""

from .servidor import ServidorDepois


def main():
    servidor = ServidorDepois()
    servidor.executar_todos()


if __name__ == "__main__":
    main()
