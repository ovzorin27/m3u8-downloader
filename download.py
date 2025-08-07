import os
import requests
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from datetime import datetime
import shutil
import argparse
import m3u8
import re
import browser_cookie3

# === Настройки ===
MAX_WORKERS = 8
LOG_FILE = "download.log"

# Строка User-Agent
# Можно узнать через сайты:
# https://www.whatismybrowser.com/, https://www.whatsmyua.info/, https://httpbin.org/user-agent
HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:141.0) Gecko/20100101 Firefox/141.0'
    )
}

# Изменить браузер:
# COOKIES = browser_cookie3.chrome()
COOKIES = browser_cookie3.firefox()

def log(message):
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now()}] {message}\n")

def parse_ts_segments(m3u8_text):
    lines = m3u8_text.splitlines()
    return [line.strip() for line in lines if line and not line.startswith("#")]

def download_segment(base_url, segment, session, output_dir):
    local_path = os.path.join(output_dir, segment)

    if os.path.exists(local_path):
        log(f"{segment} — уже существует, пропущен")
        return segment, True

    try:
        response = session.get(base_url + segment, timeout=10)
        if response.status_code == 200:
            with open(local_path, "wb") as f:
                f.write(response.content)
            return segment, True
        else:
            log(f"{segment} — ошибка HTTP {response.status_code}")
            return segment, False
    except Exception as e:
        log(f"{segment} — ошибка загрузки: {e}")
        return segment, False

def download_all_segments(base_url, segments, output_dir):
    session = requests.Session()
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        with tqdm(total=len(segments), desc="Загрузка сегментов", unit="файл") as pbar:
            futures = {
                executor.submit(download_segment, base_url, seg, session, output_dir): seg for seg in segments
            }
            for future in as_completed(futures):
                _, success = future.result()
                pbar.update(1)
    session.close()

def download_and_resolve_m3u8(master_url, desired_resolution="360p"):
    response = requests.get(master_url)
    response.raise_for_status()
    playlist = m3u8.loads(response.text)

    if playlist.is_variant:
        # Мастер-плейлист
        target_height = int(desired_resolution.replace("p", ""))
        best_match = None
        min_diff = float('inf')

        for pl in playlist.playlists:
            if pl.stream_info.resolution:
                _, height = pl.stream_info.resolution
                diff = abs(height - target_height)
                if diff < min_diff:
                    min_diff = diff
                    best_match = pl

        if not best_match:
            raise Exception(f"Не найдено качество {desired_resolution}")

        full_m3u8_url = requests.compat.urljoin(master_url, best_match.uri)
        response = requests.get(full_m3u8_url)
        response.raise_for_status()
        return response.text, full_m3u8_url
    else:
        # Это обычный медиаплейлист
        print("ℹ️ Плейлист не является мастер-плейлистом. Используем его напрямую.")
        return response.text, master_url

def check_ffmpeg_installed():
    """Проверка, установлен ли ffmpeg и доступен ли в PATH"""
    if shutil.which("ffmpeg") is None:
        print("❌ FFmpeg не найден в системе.")
        print("👉 Установи его с https://ffmpeg.org/download.html")
        print("   или добавь путь к ffmpeg.exe в переменную окружения PATH.")
        print("🔧 Локально можно использовать полный путь: C:/ffmpeg/bin/ffmpeg.exe")
        exit(1)

def merge_ts_to_mp4(output_filename, segments, output_dir):
    input_file = os.path.join(output_dir, "input.txt")
    with open(input_file, "w", encoding="utf-8") as f:
        for seg in segments:
            f.write(f"file '{seg}'\n")

    command = [
        "ffmpeg",
        "-f", "concat",
        "-safe", "0",
        "-i", input_file,
        "-c", "copy",
        output_filename
    ]

    print("\n▶ Объединение сегментов в:", output_filename)
    try:
        subprocess.run(command, check=True)
        print("✅ Объединение завершено.")
        log(f"Объединено в {output_filename}")
    except subprocess.CalledProcessError as e:
        print("❌ Ошибка объединения:", e)
        log(f"Ошибка объединения: {e}")
    os.remove(input_file)

def download_m3u8(url, output_name, resolution):
    print("📥 Скачиваем и распознаём вложенный m3u8...")
    m3u8_text, final_m3u8_url = download_and_resolve_m3u8(url, resolution)

    base_url = final_m3u8_url.rsplit("/", 1)[0] + "/"
    segments = parse_ts_segments(m3u8_text)
    print(f"🔗 Найдено сегментов: {len(segments)}")

    # Создание выходной папки по имени плейлиста и разрешения
    if not output_name:
        playlist_name = base_url.rstrip("/").split("/")[-1]
        output_name = playlist_name
    
    output_dir = output_name + "_" + resolution
    os.makedirs(output_dir, exist_ok=True)
    output_filename = output_name + "_" + resolution + ".mp4"

    download_all_segments(base_url, segments, output_dir)

    check_ffmpeg_installed()

    merge_ts_to_mp4(output_filename, segments, output_dir)

def download_all_m3u8(url, resolution):
    print("📥 Скачиваем и распознаём страницу...")

    data = extract_titles_and_m3u8_links(url)
    
    print(f"Найдено {len(data)} плейлистов")

    for title, link in data:
        print(f"📥 Скачиваем {title} ...")
        download_m3u8(link, title, resolution)

def extract_titles_and_m3u8_links(url):
    response = requests.get(url, headers=HEADERS, cookies=COOKIES)
    response.raise_for_status()
    html = response.text
    
    results = []

    # Ищем все .m3u8 ссылки
    m3u8_matches = list(re.finditer(r'https?://[^\s\'"<>]+\.m3u8(?:\?[^\'"<>]*)?', html))

    for match in m3u8_matches:
        m3u8_url = match.group(0)

        # Берем контекст вокруг найденной ссылки (например, ±500 символов)
        start = max(0, match.start() - 500)
        end = min(len(html), match.end() + 500)
        context = html[start:end]

        # Ищем title в этом фрагменте
        title_match = re.search(r"'title'\s*:\s*'([^']+)'", context) or \
                        re.search(r'"title"\s*:\s*"([^"]+)"', context)

        title = title_match.group(1) if title_match else '(без названия)'

        results.append((title, m3u8_url))

    return results

def main():
    parser = argparse.ArgumentParser(description="Массовая загрузка файлов по шаблону URL")
    parser.add_argument('--m3u8', help='URL плейлиста, например "https://big.norbekov.com/video/Event6654_7c1798dbc9304da7e1194b11b836e223/playlist.m3u8"')
    parser.add_argument('--output-name', default='', help='Имя файла на выходе')
    parser.add_argument('--resolution', default='360p', help='Разрешение, например 360p или 720p')
    parser.add_argument('--all', help='Скачать все плейлисты на странице')

    args = parser.parse_args()

    if args.m3u8:
        download_m3u8(args.m3u8, args.output_name, args.resolution)
    elif args.all:
        download_all_m3u8(args.all, args.resolution)
    else:
        parser.print_help

if __name__ == "__main__":
    main()
