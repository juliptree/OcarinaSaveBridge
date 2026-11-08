import sys

if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--synthetic-smoke':
        try:
            from bridge.smoke import run
            run(sys.argv[2])
        except Exception:
            import traceback
            from pathlib import Path
            Path(sys.argv[2] + '.error.txt').write_text(traceback.format_exc())
            sys.exit(1)
    else:
        from bridge.gui import main
        sys.exit(main())
