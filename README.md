# m3u8-downloader

## Install Python
Install Python at https://www.python.org/downloads/

## Install requirments
To install Python packages listed in a requirements.txt file, open your terminal or command prompt, navigate to the directory where the requirements.txt file is located, and execute the following command:

pip install -r requirements.txt

## Install FFmpeg
Install FFmpeg at https://ffmpeg.org/download.html

Make sure that the ffmpeg.exe path is in the PATH environment variable or just copy ffmpeg.exe to the script directory (for Windows)

## To download a single playlist, run the command

python download.py --m3u8 https://link_to_playlist.m3u8 --output-name "Output file name"  --resolution 360p

## To download all playlists on the page, run the command

python download.py --all https://link_to_page --resolution 360p

