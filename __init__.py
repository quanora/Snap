import os
import stat
import tarfile
import urllib.request
import platform
import subprocess
import threading

from aqt import mw
from aqt.qt import QAction, QTimer
from aqt.gui_hooks import main_window_did_init, profile_will_close


current_dir = os.path.dirname(os.path.abspath(__file__))

uv_dir = os.path.join(current_dir, ".snap")
uv_path = os.path.join(uv_dir, "uv")
uv_temp_path = os.path.join(uv_dir, "uv.new")

venv_path = os.path.join(current_dir, ".venv")
venv_python = os.path.join(venv_path, "bin", "python")

requirements_path = os.path.join(
    current_dir,
    "requirements.txt"
)

log_path = os.path.join(
    current_dir,
    "snap.log"
)

ocr_process = None
settings_process = None

settings_action = None

bootstrap_thread = None
bootstrap_done = False
bootstrap_error = None

bootstrap_timer = None


UV_VERSION = "0.12.16"


REQUIREMENTS = """webui2==2.5.8
easyocr
pynput
openai
pyobjc-framework-Vision
"""


def log(message):
    message = str(message)

    try:
        with open(
            log_path,
            "a",
            encoding="utf-8"
        ) as file:
            file.write(message + "\n")
    except Exception as e:
        print(f"Snap: could not write log: {e}")

    print(message, flush=True)


def reset_log():
    with open(
        log_path,
        "w",
        encoding="utf-8"
    ) as file:
        file.write("")


def create_requirements():
    current = ""

    if os.path.exists(requirements_path):
        with open(
            requirements_path,
            "r",
            encoding="utf-8"
        ) as file:
            current = file.read()

    if current == REQUIREMENTS:
        log("Snap: requirements.txt is up to date")
        return

    with open(
        requirements_path,
        "w",
        encoding="utf-8"
    ) as file:
        file.write(REQUIREMENTS)

    log("Snap: requirements.txt updated")


def get_uv_url():
    machine = platform.machine().lower()

    if machine in {"arm64", "aarch64"}:
        filename = "uv-aarch64-apple-darwin.tar.gz"

    elif machine in {"x86_64", "amd64"}:
        filename = "uv-x86_64-apple-darwin.tar.gz"

    else:
        raise RuntimeError(
            f"Unsupported Mac architecture: {machine}"
        )

    return (
        "https://github.com/astral-sh/uv/releases/download/"
        f"{UV_VERSION}/{filename}"
    )


def verify_uv_executable(path, label="uv"):
    if not os.path.isfile(path):
        log(f"Snap: {label} is missing or is not a regular file: {path}")
        return False

    try:
        mode = os.stat(path).st_mode

        # Restore execute permissions if they were lost when the addon
        # archive was created or extracted.
        if not (mode & stat.S_IXUSR):
            os.chmod(
                path,
                mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
            )
            log(f"Snap: restored executable permissions for {label}")

        result = subprocess.run(
            [path, "--version"],
            cwd=current_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=10
        )

        output = (result.stdout or "").strip()

        if result.returncode == 0 and output:
            log(f"Snap: {label} verified: {output.splitlines()[0]}")
            return True

        log(
            f"Snap: {label} verification failed: "
            f"exit={result.returncode}; output={output[:300]!r}"
        )
        return False

    except subprocess.TimeoutExpired:
        log(f"Snap: {label} verification timed out")
        return False

    except Exception as e:
        log(f"Snap: {label} cannot be executed: {e}")
        return False


def install_uv():
    os.makedirs(
        uv_dir,
        exist_ok=True
    )

    # Do not trust existence alone. The file may have lost its execute bit
    # during packaging, or it may be truncated/corrupted.
    if os.path.exists(uv_path):
        log(f"Snap: checking existing uv: {uv_path}")

        if verify_uv_executable(uv_path, "existing uv"):
            return

        log("Snap: existing uv is not usable; reinstalling it")

    url = get_uv_url()

    archive_path = os.path.join(
        uv_dir,
        "uv.tar.gz"
    )

    # Clean up incomplete artifacts from an earlier failed bootstrap.
    for path in (archive_path, uv_temp_path):
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError as e:
            raise RuntimeError(
                f"Cannot remove stale bootstrap file {path}: {e}"
            )

    log(f"Snap: downloading uv: {url}")

    try:
        with urllib.request.urlopen(url, timeout=60) as response:
            with open(archive_path, "wb") as output:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    output.write(chunk)

        if not os.path.isfile(archive_path) or os.path.getsize(archive_path) == 0:
            raise RuntimeError("Downloaded uv archive is empty")

        log("Snap: uv downloaded")

        with tarfile.open(
            archive_path,
            "r:gz"
        ) as archive:
            uv_member = None

            for member in archive.getmembers():
                if member.isfile() and (
                    member.name == "uv"
                    or member.name.endswith("/uv")
                ):
                    uv_member = member
                    break

            if uv_member is None:
                raise RuntimeError(
                    "uv executable was not found in the archive"
                )

            extracted = archive.extractfile(uv_member)

            if extracted is None:
                raise RuntimeError("Failed to extract uv")

            with extracted:
                with open(uv_temp_path, "wb") as output:
                    while True:
                        chunk = extracted.read(1024 * 1024)
                        if not chunk:
                            break
                        output.write(chunk)

        # Set the executable bit explicitly rather than relying on archive
        # permission metadata to survive packaging and extraction.
        os.chmod(uv_temp_path, 0o755)

        if not verify_uv_executable(uv_temp_path, "downloaded uv"):
            raise RuntimeError(
                "Downloaded uv failed its execution check"
            )

        # Atomic replacement avoids leaving a half-written uv binary in place.
        os.replace(
            uv_temp_path,
            uv_path
        )
        os.chmod(uv_path, 0o755)

        if not verify_uv_executable(uv_path, "installed uv"):
            raise RuntimeError(
                "Installed uv could not be executed after replacement"
            )

        log("Snap: uv installed and verified")

    finally:
        for path in (archive_path, uv_temp_path):
            try:
                if os.path.exists(path):
                    os.remove(path)
            except OSError as e:
                log(f"Snap: cleanup warning for {path}: {e}")


def install_dependencies():
    global bootstrap_done
    global bootstrap_error

    try:
        log("")
        log("===== SNAP BOOTSTRAP =====")

        log(
            f"Snap: architecture = {platform.machine()}"
        )

        log(
            f"Snap: addon directory = {current_dir}"
        )

        create_requirements()

        install_uv()

        if not os.path.exists(venv_python):
            log("Snap: creating Python 3.12 environment")

            result = subprocess.run(
                [
                    uv_path,
                    "venv",
                    "--python",
                    "3.12",
                    venv_path
                ],
                cwd=current_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=300
            )

            if result.stdout:
                log(result.stdout.rstrip())

            if result.returncode != 0:
                raise RuntimeError(
                    "Failed to create Python 3.12 environment "
                    f"(exit code {result.returncode})"
                )

        else:
            log("Snap: Python environment already exists")

        log("Snap: installing dependencies")

        result = subprocess.run(
            [
                uv_path,
                "pip",
                "install",
                "--python",
                venv_python,
                "-r",
                requirements_path
            ],
            cwd=current_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=1800
        )

        if result.stdout:
            log(result.stdout.rstrip())

        if result.returncode != 0:
            raise RuntimeError(
                "Failed to install dependencies "
                f"(exit code {result.returncode})"
            )

        log("Snap: dependencies are ready")
        bootstrap_done = True

    except Exception as e:
        bootstrap_error = str(e)
        log(f"Snap: installation error: {e}")


def start_bootstrap():
    global bootstrap_thread

    bootstrap_thread = threading.Thread(
        target=install_dependencies,
        daemon=True
    )

    bootstrap_thread.start()


def check_bootstrap():
    global bootstrap_timer

    if not bootstrap_done and bootstrap_error is None:
        return

    bootstrap_timer.stop()
    bootstrap_timer = None

    if bootstrap_error is not None:
        if settings_action is not None:
            settings_action.setText(
                "Snap (Installation Error)"
            )
            settings_action.setEnabled(False)

        log("Snap: bootstrap failed")
        return

    log("Snap: bootstrap completed")

    if settings_action is not None:
        settings_action.setText("Snap")
        settings_action.setEnabled(True)

    start_ocr()


def start_ocr():
    global ocr_process

    if ocr_process is not None and ocr_process.poll() is None:
        log("Snap: OCR is already running")
        return

    ocr_path = os.path.join(
        current_dir,
        "ocr.py"
    )

    log(f"Snap: OCR path = {ocr_path}")

    if not os.path.exists(ocr_path):
        log("Snap: ocr.py was not found")
        log("Snap: current addon directory contents:")

        for name in os.listdir(current_dir):
            log(f"  {name}")

        return

    if not os.path.exists(venv_python):
        log("Snap: Python environment was not found")
        return

    try:
        log_file = open(
            log_path,
            "a",
            encoding="utf-8"
        )

        ocr_process = subprocess.Popen(
            [
                venv_python,
                ocr_path
            ],
            cwd=current_dir,
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=subprocess.STDOUT
        )

        log(f"Snap: OCR started, PID={ocr_process.pid}")

    except Exception as e:
        log(f"Snap: failed to start OCR: {e}")


def open_settings(_checked=False):
    global settings_process

    log("Snap: settings button clicked")

    if settings_process is not None and settings_process.poll() is None:
        log("Snap: settings are already running")
        return

    main_path = os.path.join(
        current_dir,
        "main.py"
    )

    log(f"Snap: main.py path = {main_path}")

    if not os.path.exists(main_path):
        log("Snap: main.py was not found")
        return

    if not os.path.exists(venv_python):
        log("Snap: Python environment is not ready")
        return

    try:
        log_file = open(
            log_path,
            "a",
            encoding="utf-8"
        )

        settings_process = subprocess.Popen(
            [
                venv_python,
                main_path
            ],
            cwd=current_dir,
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=subprocess.STDOUT
        )

        log(f"Snap: settings started, PID={settings_process.pid}")

    except Exception as e:
        log(f"Snap: failed to start settings: {e}")


def setup_menu():
    global settings_action

    menu = mw.form.menuTools

    settings_action = QAction(
        "Snap (Preparing...)",
        mw
    )

    settings_action.setEnabled(False)
    settings_action.triggered.connect(open_settings)
    menu.addAction(settings_action)

    log("Snap: menu item created")


def on_anki_start():
    global bootstrap_timer

    reset_log()

    log("===== SNAP START =====")
    setup_menu()
    start_bootstrap()

    bootstrap_timer = QTimer(mw)
    bootstrap_timer.timeout.connect(check_bootstrap)
    bootstrap_timer.start(500)


def on_anki_close():
    global ocr_process
    global settings_process

    log("Snap: Anki is closing")

    for name, process in [
        ("OCR", ocr_process),
        ("settings", settings_process)
    ]:
        if process is None or process.poll() is not None:
            continue

        try:
            process.terminate()

            try:
                process.wait(timeout=2)
                log(f"Snap: {name} stopped")

            except subprocess.TimeoutExpired:
                log(f"Snap: {name} did not stop, killing")
                process.kill()
                process.wait(timeout=2)
                log(f"Snap: {name} killed")

        except Exception as e:
            log(f"Snap: failed to stop {name}: {e}")


main_window_did_init.append(
    on_anki_start
)

profile_will_close.append(
    on_anki_close
)
