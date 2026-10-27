#!/usr/bin/env bash

set -u

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${SCRIPT_DIR}/.venv"
VENV_PYTHON="${VENV_DIR}/bin/python"
TOOLS_DIR="${SCRIPT_DIR}/.tools"
UV_DIR="${TOOLS_DIR}/uv"
export UV_PYTHON_INSTALL_DIR="${TOOLS_DIR}/python"

environment_ready() {
    [[ -x "${VENV_PYTHON}" ]] &&
        "${VENV_PYTHON}" -c \
            'import sys, requests, selenium, webdriver_manager, yt_dlp, moodle_download; assert sys.version_info >= (3, 10)' \
            >/dev/null 2>&1
}

find_python() {
    local candidate
    for candidate in python3 python; do
        if command -v "${candidate}" >/dev/null 2>&1 &&
            "${candidate}" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1; then
            command -v "${candidate}"
            return 0
        fi
    done
    return 1
}

ensure_uv() {
    if command -v uv >/dev/null 2>&1; then
        command -v uv
        return 0
    fi
    if [[ -x "${UV_DIR}/uv" ]]; then
        printf '%s\n' "${UV_DIR}/uv"
        return 0
    fi
    if [[ -x "${UV_DIR}/bin/uv" ]]; then
        printf '%s\n' "${UV_DIR}/bin/uv"
        return 0
    fi

    mkdir -p "${UV_DIR}"
    if command -v curl >/dev/null 2>&1; then
        curl -LsSf https://astral.sh/uv/install.sh | env UV_UNMANAGED_INSTALL="${UV_DIR}" sh >/dev/null
    elif command -v wget >/dev/null 2>&1; then
        wget -qO- https://astral.sh/uv/install.sh | env UV_UNMANAGED_INSTALL="${UV_DIR}" sh >/dev/null
    else
        return 1
    fi

    if [[ -x "${UV_DIR}/uv" ]]; then
        printf '%s\n' "${UV_DIR}/uv"
        return 0
    fi
    if [[ -x "${UV_DIR}/bin/uv" ]]; then
        printf '%s\n' "${UV_DIR}/bin/uv"
        return 0
    fi
    return 1
}

if ! environment_ready; then
    printf '\n%s\n' '======================================================'
    printf '%s\n' '   Moodle Downloader - First-Time Setup & Environment'
    printf '%s\n\n' '======================================================'

    UV_BIN=""
    if [[ ! -x "${VENV_PYTHON}" ]]; then
        if SYSTEM_PYTHON="$(find_python)" && "${SYSTEM_PYTHON}" -m venv "${VENV_DIR}" >/dev/null 2>&1; then
            printf '%s\n' 'Created isolated Python environment in .venv ...'
        else
            printf '%s\n' 'No local Python 3.10+ with venv found. Downloading portable Python runtime via uv ...'
            if ! UV_BIN="$(ensure_uv)"; then
                printf '\n%s\n' 'ERROR: Could not find Python 3.10+ or download portable uv installer.' >&2
                printf '%s\n' 'Ensure curl/wget and an internet connection are available.' >&2
                exit 1
            fi
            if ! "${UV_BIN}" venv --python 3.12 "${VENV_DIR}"; then
                printf '\n%s\n' 'ERROR: Could not create portable Python virtual environment.' >&2
                exit 1
            fi
        fi
    fi

    printf '%s\n' 'Installing or updating dependencies ...'
    if [[ -n "${UV_BIN}" ]]; then
        INSTALL_CMD=("${UV_BIN}" pip install --python "${VENV_PYTHON}" -e "${SCRIPT_DIR}")
    elif "${VENV_PYTHON}" -m pip --version >/dev/null 2>&1; then
        INSTALL_CMD=("${VENV_PYTHON}" -m pip install --disable-pip-version-check -e "${SCRIPT_DIR}")
    elif UV_BIN="$(ensure_uv)"; then
        INSTALL_CMD=("${UV_BIN}" pip install --python "${VENV_PYTHON}" -e "${SCRIPT_DIR}")
    else
        printf '\n%s\n' 'ERROR: pip is unavailable and uv could not be downloaded.' >&2
        exit 1
    fi

    if ! "${INSTALL_CMD[@]}"; then
        printf '\n%s\n' 'ERROR: Python packages could not be installed.' >&2
        printf '%s\n' 'Check the messages above and your internet connection.' >&2
        exit 1
    fi

    if ! environment_ready; then
        printf '\n%s\n' 'ERROR: The installation is incomplete.' >&2
        exit 1
    fi

    printf '\n%s\n' 'Setup complete!'
fi

export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8
export PYTHONPATH="${SCRIPT_DIR}/src${PYTHONPATH:+:${PYTHONPATH}}"

exec "${VENV_PYTHON}" "${SCRIPT_DIR}/start.py" "$@"
