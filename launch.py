import sys

if '--blackshark' in sys.argv[1:]:
    from pathlib import Path
    from rio_monitor.extensions import import_path
    from rio_monitor.settings import config_path
    # Packaged builds run the downloaded module; it arrives when switched on in Settings › Extensions.
    if not import_path('blackshark',Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent))/'assets',config_path().parent/'modules'):
        raise SystemExit('BlackShark module is not downloaded; switch it on in Settings > Extensions first.')
    from rio_blackshark.__main__ import main
    args=sys.argv[1:]
    args.remove('--blackshark')
    def collector():
        # Host telemetry for the explicit monitor action; the module never imports RIO.
        from rio_monitor.telemetry import Collector
        return Collector()
    raise SystemExit(main(args,collector=collector))
else:
    from rio_monitor.qt_app import main
    main()
