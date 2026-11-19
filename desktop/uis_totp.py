"""Store the ROG downloader's UIS TOTP seed using Windows user DPAPI."""

import getpass
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import warnings

from src.api.webvpn import SecondFactorError, totp_code


SECRET_FILE = Path(__file__).resolve().parents[1] / "local-data" / "rog" / "uis-totp.dpapi"


def _secure_string(script: str, value: str) -> str:
    # Pass data through a private pipe. Command lines contain only the fixed script.
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
             "$ErrorActionPreference = 'Stop'; " + script],
            input=value + "\n", capture_output=True, encoding="ascii",
            creationflags=subprocess.CREATE_NO_WINDOW, check=True, timeout=15,
        )
    except (OSError, subprocess.SubprocessError, UnicodeError):
        raise SecondFactorError("Windows could not access the iCourse TOTP store") from None
    return result.stdout.strip()


def load_totp_secret(path: Path = SECRET_FILE) -> str | None:
    if os.name != "nt" or not path.is_file():
        return None
    try:
        encrypted = path.read_text(encoding="ascii").strip()
    except (OSError, UnicodeError):
        raise SecondFactorError("Windows could not read the iCourse TOTP store") from None
    secret = _secure_string(
        "$secure = ConvertTo-SecureString ([Console]::ReadLine()); "
        "[Console]::WriteLine([Net.NetworkCredential]::new('', $secure).Password)",
        encrypted,
    )
    totp_code(secret)
    return secret


def save_totp_secret(value: str, path: Path = SECRET_FILE) -> None:
    secret = "".join(value.split()).upper().rstrip("=")
    totp_code(secret)
    encrypted = _secure_string(
        "$secure = ConvertTo-SecureString ([Console]::ReadLine()) -AsPlainText -Force; "
        "[Console]::WriteLine((ConvertFrom-SecureString $secure))",
        secret,
    )
    if not encrypted:
        raise SecondFactorError("Windows did not encrypt the iCourse TOTP seed")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = tempfile.NamedTemporaryFile(
        mode="w", encoding="ascii", dir=path.parent, delete=False,
    )
    pending = Path(temporary.name)
    try:
        with temporary:
            temporary.write(encrypted + "\n")
        pending.replace(path)
    finally:
        pending.unlink(missing_ok=True)


def main() -> None:
    if os.name != "nt":
        raise SystemExit("Run this command on the Windows PC that downloads iCourse videos.")
    if not sys.stdin.isatty():
        raise SystemExit("Open PowerShell on ROG and run the command in that terminal.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            value = getpass.getpass("Fudan UIS Base32 setup key (hidden): ")
        save_totp_secret(value)
    except getpass.GetPassWarning:
        raise SystemExit("Open PowerShell on ROG and run the command in that terminal.") from None
    except (OSError, SecondFactorError) as error:
        raise SystemExit(str(error)) from None
    print("iCourse TOTP key saved for this Windows user.")


if __name__ == "__main__":
    main()
