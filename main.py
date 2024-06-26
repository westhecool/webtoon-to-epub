from bs4 import BeautifulSoup
import os
import shutil
from PIL import Image
import time
import requests
from ebooklib import epub
import re
import io
import numpy as np
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
args.add_argument('--proxy', help='Proxy to use', type=str, default="")
args.add_argument('--max-image-size', help='Max virtual image size. (Default: 2000)', type=int, default=2000)
args = args.parse_args()

proxies = {}
if args.proxy:
    proxies = {'http': args.proxy, 'https': args.proxy}

chapter_page_count_total = 0

def image_color_similarity(image):   
    # Convert the image to grayscale and then to a NumPy array
    image_array = list(image.convert("L").getdata())

    average_similarity = np.mean(image_array) / 255 # 8 Bits per pixel

    # Return the average similarity as a percentage
    return average_similarity * 100

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
        img.close()

    return combined_image

def getNumericIndex(filename:str):
    return int(filename.split('.')[0])

def downloadChapter(link, title, chapterid):
    html = requests.get(link, proxies=proxies, timeout=5).text
    soup = BeautifulSoup(html, 'html.parser')
    imglist = soup.find(id='_imageList').findChildren('img')
    i = 0
    if not os.path.exists(f'data/{make_safe_filename_windows(title)}/{chapterid}'):
        os.makedirs(f'data/{make_safe_filename_windows(title)}/{chapterid}')
    for img in imglist:
        i += 1
        print(f'\rDownloading image {i}/{len(imglist)}', end='')
        def get():
            try:
                return requests.get(img['data-url'], headers={'Referer': link}, proxies=proxies, timeout=5).content
            except Exception as e:
                print(e)
                print('Retrying in 1 second...')
                time.sleep(1)
                return get()
        img = get()
        image = Image.open(io.BytesIO(img))
        image = image.convert('RGB')
        image.save(f'data/{make_safe_filename_windows(title)}/{chapterid}/{i}.jpg')
        image.close()
    print('')

def getChapterList(link):
    global chapter_page_count_total
    html = requests.get(link, proxies=proxies, timeout=5).text
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
    html = requests.get(link, proxies=proxies, timeout=5).text
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
            lastpercent = 0
            # Convert image to numpy array in grey scale
            image_array = np.array(image.convert('L').getdata(), np.uint8).reshape((height, width))
            for y in range(height):
                percent = int(((y + 1) / height) * 100)
                if percent > lastpercent:
                    print(f'\r{percent}% done', end='')
                    lastpercent = percent
                
                # get all the pixels in the line
                line = image_array[y]
                uniques, counts = np.unique(line, return_counts=True)

                # Find the index of the largest count
                max_index = np.argmax(counts)

                # Calculate the percentage for the largest element
                largest_percentage = (counts[max_index] * 100) / len(line)
                
                # Check if all pixels in the line have the same color
                if largest_percentage >= 95: # Check if at least 95% of the pixels in the line are the same color
                    if not wait:
                        line_count += 1
                        if line_count == args.auto_crop_line_count:
                            count += 1
                            segment = image.crop((0, lasty, width, y - args.auto_crop_line_count + 1))
                            lheight = segment.height
                            while lheight > args.max_image_size: # Check if the image is too tall
                                segment1 = segment.crop((0, 0, segment.width, args.max_image_size))
                                segment = segment.crop((0, args.max_image_size, segment.width, segment.height))
                                lheight = segment.height
                                if image_color_similarity(segment1) <= 99: # Check if the image is just white space
                                    segment1.save(f'data/{make_safe_filename_windows(title)}/{chapter_index}/{count}.jpg')
                                else:
                                    count -= 1
                                count += 1
                                #print('\nWarning: Image is too big, roughly spliting the image')
                            if image_color_similarity(segment) <= 99: # Check if the image is just white space
                                segment.save(f'data/{make_safe_filename_windows(title)}/{chapter_index}/{count}.jpg')
                            else:
                                count -= 1
                            lasty = y
                            line_count = 0
                            wait = True
                else:
                    line_count = 0
                    wait = False

            if y == height - 1 and not y == lasty: # save the remaining image only if there is any more to save
                count += 1
                segment = image.crop((0, lasty, width, y))
                lheight = segment.height
                while lheight > args.max_image_size: # Check if the image is too tall
                    segment1 = segment.crop((0, 0, segment.width, args.max_image_size))
                    segment = segment.crop((0, args.max_image_size, segment.width, segment.height))
                    lheight = segment.height
                    if image_color_similarity(segment1) <= 99: # Check if the image is just white space
                        segment1.save(f'data/{make_safe_filename_windows(title)}/{chapter_index}/{count}.jpg')
                    else:
                        count -= 1
                    count += 1
                    #print('\nWarning: Image is too big, roughly spliting the image')
                if image_color_similarity(segment) <= 99: # Check if the image is just white space
                    segment.save(f'data/{make_safe_filename_windows(title)}/{chapter_index}/{count}.jpg')
                else:
                    count -= 1
            print('')

        book_chapter = epub.EpubHtml(title=chapter[0], file_name=f'chapter{chapter_index}.xhtml')
        book_chapter.content = '<body style="margin: 0;">'

        imgs = sorted(os.listdir(f'data/{make_safe_filename_windows(title)}/{chapter_index}'), key=getNumericIndex)
        for img in imgs:
            print(f'\rAdding image {getNumericIndex(img)}/{len(imgs)} to comic', end='')
            f = open(f'data/{make_safe_filename_windows(title)}/{chapter_index}/{img}', 'rb')
            content = f.read()
            f.close()
            image = epub.EpubItem(file_name=f'chapter{chapter_index}/{img}', content=content)
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
                print(f'Saving comic part {part_count}')
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
        print('Saving comic')
        epub.write_epub(f'{make_safe_filename_windows(title)}.epub', book, {})
    elif chapter_index_parts != 0:
        part_count += 1

        # Add default NCX and Nav file
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())

        # Save the ePub
        print(f'Saving comic part {part_count}')
        epub.write_epub(f'{make_safe_filename_windows(title)} - Part {part_count}.epub', book, {})

    if args.clean_up:
        print('Cleaning up')
        shutil.rmtree(f'data/{make_safe_filename_windows(title)}')
    
    print('\n') # Add 2 empty lines at the end of a book

for link in args.link.split(','):
    def f():
        global chapter_page_count_total
        chapter_page_count_total = 0
        try:
            downloadComic(re.sub(r'&page=.*', '', link))
        except Exception as e:
            print('Failed to download comic.')
            print(e)
            print('Retrying in 5 seconds...')
            time.sleep(5)
            f()
    f()