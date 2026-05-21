from lemana_parser.cli import main


if __name__ == "__main__":
    import sys

    exit_code = main()
    if sys.stdin.isatty() and "--no-pause" not in sys.argv:
        input("\nНажми Enter для выхода...")
    sys.exit(exit_code)

