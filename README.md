# Webtoon to .epub converter
A program to download a whole webtoon comic into a `.epub` file. (For use with an e-reader or similar.)<br>
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
The input **must** be a link to the chapter list of the webtoon series. Please do not use the mobile version of the site as it's not tested.

## Auto-Crop
Webtoon stores images in a very weird way where they are at a fixed size which often leads to comic panels getting cut right in half. You can use the argument `--auto-crop` to attempt to automatically crop the images. (Enabled by default.) This isn't perfect though, and may be buggy. It works by reading the image in horizontal lines and if there is at least 95% of the same color in a line we're assuming that that is a break in the comic panel. (For example: Say there are 30 (The default) white lines in a row then we can assume that this is a break in the comic panel.) If you want to you can try fine-tuning how many lines before it splits, you can with the argument `--auto-crop-line-count N`.

## Splitting A Comic Into Parts
You can use the option `--split-into-parts` (Not enabled by default.) to split the comic into multiple files. By default, it splits every 100 chapters into a different file. You can adjust it with the argument `--chapters-per-part N`.

## Tip: Converting to MOBI (Kindle e-reader supported format)
You can use the program [ebook-convert](https://command-not-found.com/ebook-convert) (Which is part of Calibre) to easily convert to `.mobi`:
```sh
ebook-convert input.epub output.mobi
```
