"""Opt-in web launcher; existing desktop startup remains the default."""
import argparse
import getpass
import ipaddress
import os
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser(description="Browser control for the CoC bot")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--lan", action="store_true", help="Разрешить доступ с устройств в локальной Wi-Fi-сети")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--origin", action="append", help="Exact browser origin, including port")
    parser.add_argument("--set-password", action="store_true")
    access = parser.add_mutually_exclusive_group()
    access.add_argument("--require-password", action="store_true",
                        help="Opt in to password protection instead of opening the dashboard directly")
    access.add_argument("--no-password", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--home", type=Path, help="Separate config/data root for testing")
    parser.add_argument("--secure-cookie", action="store_true", help="Required when serving over HTTPS")
    parser.add_argument("--screen-model", type=Path, help="Optional observer model (never controls actions)")
    args = parser.parse_args(argv)
    if args.home:
        os.environ["COC_BOT_HOME"] = str(args.home.resolve())
        os.environ.pop("COC_BOT_CONFIG", None)
    from coc_bot.config import project_root
    if args.set_password:
        from coc_bot.web.auth import set_password
        password = getpass.getpass("Browser password (at least 12 characters): ")
        if password != getpass.getpass("Confirm password: "):
            parser.error("Passwords do not match")
        set_password(project_root() / "data/web-auth.json", password)
        print("Browser password saved.")
        return
    try:
        loopback = args.host == "localhost" or ipaddress.ip_address(args.host).is_loopback
    except ValueError:
        parser.error("Host must be localhost or an IP address")
    if not args.require_password and not loopback:
        address = ipaddress.ip_address(args.host)
        if not address.is_private or address.is_unspecified or address.is_multicast or address.is_link_local:
            parser.error("Password-free mode must bind to a specific private LAN IP or localhost.")
    if args.lan and not loopback:
        parser.error("С --lan оставьте стандартный --host: адрес Wi-Fi определяется автоматически.")
    if not loopback and not args.origin:
        parser.error("LAN access needs an explicit --origin, preferably through an HTTPS reverse proxy.")
    if not 1 <= args.port <= 65535:
        parser.error("Port must be between 1 and 65535")
    from coc_bot.logging_utils import setup_logging
    from coc_bot.runtime.device_lease import DeviceLease
    from coc_bot.web.server import create_app
    import uvicorn
    setup_logging(debug=False, log_file=project_root() / "data/bot.log")
    origins = args.origin or [f"http://127.0.0.1:{args.port}", f"http://localhost:{args.port}"]
    lan_addresses=[]
    if args.lan:
        from coc_bot.web.network import discover_lan_addresses
        lan_addresses=discover_lan_addresses()
        origins=list(dict.fromkeys([*origins,*(f'http://{address}:{args.port}' for address in lan_addresses)]))
        for address in lan_addresses:
            print(f'Панель с телефона в этой сети: http://{address}:{args.port}',flush=True)
    if args.screen_model:
        from coc_bot.vision.screen_model import enable_observer
        enable_observer(args.screen_model)
    # Locks the server, not the Android device; engine jobs retain device leases.
    with DeviceLease("web-server:" + str(project_root())):
        app=create_app(origins=origins, secure_cookie=args.secure_cookie,
                       password_required=args.require_password)
        if args.lan:
            from coc_bot.web.network import listening_sockets
            with listening_sockets(['127.0.0.1',*lan_addresses],args.port) as sockets:
                uvicorn.Server(uvicorn.Config(app,port=args.port,workers=1,access_log=False)).run(sockets=sockets)
        else:
            uvicorn.run(app,host=args.host,port=args.port,workers=1,access_log=False)


if __name__ == "__main__":
    main()
