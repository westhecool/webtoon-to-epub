from bs4 import BeautifulSoup
import os
import shutil
from PIL import Image
import requests
from ebooklib import epub
import re
import io
import argparse

Image.MAX_IMAGE_PIXELS = 200000000 # We expect to get some really big images hopefully this is big enough

args = argparse.ArgumentParser()
args.description = 'Download and convert a whole webtoon series to epub.'
args.add_argument('link', help='Link to webtoon comic to download. (This should be the link to chapter list.)', type=str)
args.add_argument('--clean-up', help='Clean up the downloaded images after they are put in the epub.', type=bool, default=True, action=argparse.BooleanOptionalAction)
args.add_argument('--auto-crop', help='Automatically crop the images. (Read more about this in the README on the GitHub.)', type=bool, default=True, action=argparse.BooleanOptionalAction)
args.add_argument('--auto-crop-line-count', help='(See README on GitHub.)', type=int, default=30)
args.add_argument('--split-into-parts', help='Split the comic into parts.', type=bool, default=False, action=argparse.BooleanOptionalAction)
args.add_argument('--chapters-per-part', help='Chapters per part. (Default: 100)', type=int, default=100)
args = args.parse_args()

chapter_page_count_total = 0

def make_safe_filename_windows(filename):
    illegal_chars = r'<>:"/\|?*'
    for char in illegal_chars:
        filename = filename.replace(char, '_')
    return filename

def combineImagesVertically(image_paths):
    images = [Image.open(image) for image in image_paths]

    max_width = max(i.width for i in images)
    total_height = sum(i.height for i in images)
    combined_image = Image.new('RGB', (max_width, total_height), color='white')

    # Paste each image onto the new image
    y_offset = 0
    for img in images:
        combined_image.paste(img, (0, y_offset))
        y_offset += img.height

    return combined_image

def getNumericIndex(filename:str):
    return int(filename.split('.')[0])

def downloadChapter(link, title, chapterid):
    html = requests.get(link).text
    soup = BeautifulSoup(html, 'html.parser')
    imglist = soup.find(id='_imageList').findChildren('img')
    i = 0
    if not os.path.exists(f'data/{make_safe_filename_windows(title)}/{chapterid}'):
        os.makedirs(f'data/{make_safe_filename_windows(title)}/{chapterid}')
    for img in imglist:
        i += 1
        print(f'\rDownloading image {i}/{len(imglist)}', end='')
        img = requests.get(img['data-url'], headers={'Referer': link}).content
        image = Image.open(io.BytesIO(img))
        image = image.convert('RGB')
        image.save(f'data/{make_safe_filename_windows(title)}/{chapterid}/{i}.jpg')
    print('')

def getChapterList(link):
    global chapter_page_count_total
    html = requests.get(link).text
    soup = BeautifulSoup(html, 'html.parser')
    for l in soup.find('div', class_='paginate').findChildren('a'):
        i = re.sub(r'.*&page=', '', l['href'])
        if i == '#': # this is the page we are currently on
            continue
        i = int(i)
        if i > chapter_page_count_total:
            chapter_page_count_total = i
    chapter_list = []
    chapters = soup.find_all('li', class_='_episodeItem')
    for chapter in chapters:
        chapter_title = chapter.find('span', class_='subj').text
        chapter_link = chapter.find('a')['href']
        chapter_list.append((chapter_title, chapter_link))
    return chapter_list

def downloadComic(link):
    print(f'Link: {link}')
    global chapter_page_count_total
    html = requests.get(link).text
    soup = BeautifulSoup(html, 'html.parser')
    info = soup.find('div', class_='info')
    title = info.find(class_='subj').text.strip()
    genre = info.find(class_='genre').text.strip()
    try:
        author = info.find(class_='author').text.replace('author info', '').strip()
    except:
        author = info.find(class_='author_area').text.replace('author info', '').strip()
    author = re.sub(r'\s{2,}', ' ', author)
    chapter_page_count = 0
    chapter_page_count_total = len(soup.find('div', class_='paginate').findChildren('a'))

    print(f'Title: {title}')
    print(f'Genre: {genre}')
    print(f'Author: {author}')

    try:
        shutil.rmtree(f'data/{make_safe_filename_windows(title)}')
    except:
        pass

    chapters = []
    while chapter_page_count < chapter_page_count_total:
        chapter_page_count += 1
        print(f'\rFetching chapters from page {chapter_page_count}/{chapter_page_count_total}', end='')
        chapters.extend(getChapterList(f'{link}&page={chapter_page_count}'))
    print('')

    print(f'Chapter count: {len(chapters)}')

    print('')
    
    chapters = list(reversed(chapters)) # reverse the list because webtoon lists the newest chapters first
 
    book = epub.EpubBook()
    if args.split_into_parts:
        book.set_title(f'{title} - Part 1')
    else:
        book.set_title(title)
    book.add_author(author)
    book.spine = ['nav']

    chapter_index = 0
    chapter_index_parts = 0
    part_count = 0
    for chapter in chapters: # chapter[0] is the title, chapter[1] is the link
        chapter_index += 1
        chapter_index_parts += 1
        print(f'Downloading chapter {chapter_index}: {chapter[0]}')
        downloadChapter(chapter[1], title, chapter_index)
        
        if args.auto_crop:
            print(f'Auto cropping chapter {chapter_index}: {chapter[0]}')
            images = []
            for img in sorted(os.listdir(f'data/{make_safe_filename_windows(title)}/{chapter_index}'), key=getNumericIndex):
                images.append(f'data/{make_safe_filename_windows(title)}/{chapter_index}/{img}')
            image = combineImagesVertically(images)
            # Remove all images in the chapter folder
            for img in os.listdir(f'data/{make_safe_filename_windows(title)}/{chapter_index}'):
                os.remove(f'data/{make_safe_filename_windows(title)}/{chapter_index}/{img}')
            lasty = 0
            line_count = 0
            count = 0
            wait = False
            width, height = image.size

            for y in range(height):
                print(f'\rLine {y + 1}/{height}', end='')
                line = [image.getpixel((x, y)) for x in range(width)]

                # Check if all pixels in the line have the same color
                if len(set(line)) == 1:
                    if not wait:
                        line_count += 1
                        if line_count == args.auto_crop_line_count:
                            count += 1
                            segment = image.crop((0, lasty, width, y))
                            segment.save(f'data/{make_safe_filename_windows(title)}/{chapter_index}/{count}.jpg')
                            lasty = y
                            line_count = 0
                            wait = True
                    #print(f'Line {y + 1}: All pixels have the same color')
                else:
                    line_count = 0
                    wait = False
                    #print(f'Line {y + 1}: Pixels have different colors')
                if y == height - 1: # save the remaining image
                    count += 1
                    segment = image.crop((0, lasty, width, y))
                    segment.save(f'data/{make_safe_filename_windows(title)}/{chapter_index}/{count}.jpg')
            print('')

        book_chapter = epub.EpubHtml(title=chapter[0], file_name=f'chapter{chapter_index}.xhtml')
        book_chapter.content = '<body style="margin: 0;">'

        imgs = sorted(os.listdir(f'data/{make_safe_filename_windows(title)}/{chapter_index}'), key=getNumericIndex)
        for img in imgs:
            print(f'\rAdding image {getNumericIndex(img)}/{len(imgs)} to book', end='')
            image = epub.EpubItem(file_name=f'chapter{chapter_index}/{img}', content=open(f'data/{make_safe_filename_windows(title)}/{chapter_index}/{img}', 'rb').read())
            book.add_item(image)
            book_chapter.content += f'<img style="height: 100%;" src="chapter{chapter_index}/{img}"/>'
        print('')

        book_chapter.content += '</body>'

        # Add chapter to the book
        book.add_item(book_chapter)
        book.toc.append(epub.Link(f'chapter{chapter_index}.xhtml', chapter[0], f'chapter{chapter_index}'))

        book.spine.append(book_chapter)

        print('') # Add empty line at the end of a chapter
        if args.split_into_parts:
            if chapter_index_parts == args.chapters_per_part:
                chapter_index_parts = 0
                part_count += 1

                # Add default NCX and Nav file
                book.add_item(epub.EpubNcx())
                book.add_item(epub.EpubNav())

                # Save the ePub
                print(f'Saving book part {part_count}')
                epub.write_epub(f'{make_safe_filename_windows(title)} - Part {part_count}.epub', book, {})

                book = epub.EpubBook()
                book.set_title(f'{title} - Part {part_count + 1}')
                book.add_author(author)
                book.spine = ['nav']
                
                print('')
        
    if not args.split_into_parts:
        # Add default NCX and Nav file
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())

        # Save the ePub
        print('Saving book')
        epub.write_epub(f'{make_safe_filename_windows(title)}.epub', book, {})
    elif chapter_index_parts != 0:
        part_count += 1

        # Add default NCX and Nav file
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())

        # Save the ePub
        print(f'Saving book part {part_count}')
        epub.write_epub(f'{make_safe_filename_windows(title)} - Part {part_count}.epub', book, {})

    if args.clean_up:
        print('Cleaning up')
        shutil.rmtree(f'data/{make_safe_filename_windows(title)}')
    
    print('\n') # Add 2 empty lines at the end of a book

for link in args.link.split(','):
    chapter_page_count_total = 0
    downloadComic(re.sub(r'&page=.*', '', link))