"""`python -m auditly` opens the desktop app; `python -m auditly crawl …` runs the command line."""
import sys

CLI_WORDS = {"crawl", "sessions", "export", "compare", "audits", "-h", "--help", "--version"}


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] in CLI_WORDS:
        from .cli import main as cli_main
        return cli_main(sys.argv[1:])
    from .ui.app import run
    return run()


if __name__ == "__main__":
    sys.exit(main())
