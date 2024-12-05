# Webtoon to .epub converter
A program to download a whole webtoon comic into a `.epub` file. (For use with an e-reader or similar.)<br>
Note: **!!This could break at any time because it relies on the current layout of Webtoon's website!!**

## Bug fixes only
I have decided to stop adding new features and improving this script. Webtoons are meant to be read vertically, while ebooks are not. I have tried to crop them to fit on pages, but this is not perfect and often leads to very long images that are impossible to read. Therefore, I will only be fixing bugs from now on.

## Installation
Using a venv:
```sh
git clone https://github.com/westhecool/webtoon-to-epub.git
cd webtoon-to-epub
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
```

## Usage
```sh
./venv/bin/python3 main.py [link to chapter list of Webtoon series]
```
The input **must** be a link to the chapter list of the webtoon series. Please do not use the mobile version of the site as it's not tested.

## Auto-Crop
Webtoon stores images in a very weird way where they are at a fixed size which often leads to comic panels getting cut right in half. You can use the argument `--auto-crop` to attempt to automatically crop the images. (Enabled by default.) This isn't perfect though, and may be buggy.

## Splitting A Comic Into Parts
You can use the option `--split-into-parts` (Not enabled by default.) to split the comic into multiple files. By default, it splits every 100 chapters into a different file. You can adjust it with the argument `--chapters-per-part N`.

## Tip: Converting to MOBI (Kindle e-reader supported format)
You can use the program [ebook-convert](https://command-not-found.com/ebook-convert) (Which is part of Calibre) to easily convert to `.mobi`:
```sh
ebook-convert input.epub output.mobi
```
