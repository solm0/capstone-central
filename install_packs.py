import os
import shutil
import zipfile
from pathlib import Path

import requests
from packaging.version import Version

from packs import PACKS

# 1. GitHub Releases 조회
# 2. 언어별 최신 버전 선택
# 3. 현재 설치 버전 확인
# 4. 최신이면 skip
# 5. 낮은 버전이면 제거
# 6. zip 다운로드
# 7. ./data/static/{lang}/{version}/ 에 압축 해제

GITHUB_REPO = "solm0/capstone"

BASE_DIR = Path("./data/static")
TMP_DIR = Path("./tmp_packs")

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")


def github_headers():
    headers = {
        "Accept": "application/vnd.github+json",
    }

    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"

    return headers


def get_latest_release_asset(lang: str):
    """
    Fetch latest release metadata for a language pack.
    Example tag:
        ru-v1.0.0
    """

    releases_url = f"https://api.github.com/repos/{GITHUB_REPO}/releases"

    res = requests.get(releases_url, headers=github_headers(), timeout=30)
    res.raise_for_status()

    releases = res.json()

    matched = []

    prefix = f"{lang}-v"

    for release in releases:
        tag_name = release.get("tag_name", "")

        if not tag_name.startswith(prefix):
            continue

        version_str = tag_name.replace(prefix, "")

        try:
            version = Version(version_str)
        except Exception:
            continue

        matched.append((version, release))

    if not matched:
        return None

    matched.sort(key=lambda x: x[0], reverse=True)

    latest_version, latest_release = matched[0]

    assets = latest_release.get("assets", [])

    if not assets:
        raise RuntimeError(f"No assets found for {lang}")

    asset = assets[0]

    return {
        "version": str(latest_version),
        "download_url": asset["browser_download_url"],
        "filename": asset["name"],
    }


def get_installed_versions(lang: str):
    lang_dir = BASE_DIR / lang

    if not lang_dir.exists():
        return []

    versions = []

    for item in lang_dir.iterdir():
        if item.is_dir():
            try:
                versions.append(Version(item.name))
            except Exception:
                pass

    return sorted(versions, reverse=True)


def remove_old_versions(lang: str, keep_version: str):
    lang_dir = BASE_DIR / lang

    if not lang_dir.exists():
        return

    for item in lang_dir.iterdir():
        if not item.is_dir():
            continue

        if item.name != keep_version:
            print(f"Removing old version: {item}")
            shutil.rmtree(item, ignore_errors=True)


def download_file(url: str, target: Path):
    with requests.get(url, headers=github_headers(), stream=True, timeout=120) as r:
        r.raise_for_status()

        with open(target, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)


def install_pack(lang: str, version: str, zip_path: Path):
    target_dir = BASE_DIR / lang / version

    if target_dir.exists():
        shutil.rmtree(target_dir)

    target_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        zip_ref.extractall(target_dir)

    print(f"Installed {lang} v{version}")


def process_language(lang: str):
    print(f"\n=== Processing {lang} ===")

    latest = get_latest_release_asset(lang)

    if not latest:
        print(f"No release found for {lang}")
        return

    latest_version = Version(latest["version"])

    installed_versions = get_installed_versions(lang)

    if installed_versions:
        installed_latest = installed_versions[0]

        if installed_latest >= latest_version:
            print(f"{lang} already up to date ({installed_latest})")
            return

    remove_old_versions(lang, str(latest_version))

    TMP_DIR.mkdir(parents=True, exist_ok=True)

    zip_path = TMP_DIR / latest["filename"]

    print(f"Downloading: {latest['download_url']}")
    download_file(latest["download_url"], zip_path)

    install_pack(lang, str(latest_version), zip_path)

    zip_path.unlink(missing_ok=True)


def main():
    for pack in PACKS:
        lang = pack["lang"]

        try:
            process_language(lang)
        except Exception as e:
            print(f"Failed processing {lang}: {e}")


if __name__ == "__main__":
    main()