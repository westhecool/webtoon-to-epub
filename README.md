# Webtoon to .epub converter
A program to download a whole webtoon comic into a `.epub` file. (For use with a e-reader or similar.)<br>
Note: **!!This could break at any time because it relies on the current layout of Webtoon's website!!**

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
The input **must** be a link to the chapter list of the webtoon series.

## Auto-Crop
Webtoon stores images in a very weird way where they are at a fixed size which often leads to comic panels getting cut right in half. You can use the argument `--auto-crop` to attempt to automatically recrop the images. This isn't perfect though, and may be buggy. It works by detecting if there is a sequence of lines in a row that all have the same color. (For example: Say there are 30 (The default) white lines in a row then we can assume that this is a break in the comic panel.) If you want to you can try fine tuning how many lines before it splits, you can with the argument `--auto-crop-line-count N`.

## Tip: Converting to MOBI (Kindle e-reader supported format)
You can use the program [ebook-convert](https://command-not-found.com/ebook-convert) (Which is part of Calibre) to easily convert to `.mobi`:
```sh
ebook-convert input.epub output.mobi
```