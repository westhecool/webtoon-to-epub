from bs4 import BeautifulSoup
import os
import shutil
import time
import requests
from ebooklib import epub
import re
import cv2
import numpy as np
import argparse
import threading

args = argparse.ArgumentParser()
args.description = 'Download and convert a whole webtoon series to epub.'
args.add_argument('link', help='Link to webtoon comic to download. (This should be the link to chapter list.)', type=str)
args.add_argument('--clean-up', help='Clean up the downloaded images after they are put in the epub.', type=bool, default=True, action=argparse.BooleanOptionalAction)
args.add_argument('--auto-crop', help='Automatically crop the images. (Read more about this in the README on the GitHub.)', type=bool, default=True, action=argparse.BooleanOptionalAction)
args.add_argument('--split-into-parts', help='Split the comic into parts.', type=bool, default=False, action=argparse.BooleanOptionalAction)
args.add_argument('--chapters-per-part', help='Chapters per part. (Default: 100)', type=int, default=100)
args.add_argument('--proxy', help='Proxy to use', type=str, default="")
args.add_argument('--threads', help='How many threads to use when downloading. (Default: 10)', type=int, default=10)
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

def convert_image_to_jpeg(binary, save_path, quality=90):
    # Convert binary content to NumPy array
    image_array = np.frombuffer(binary, dtype=np.uint8)

    # Decode the binary array into an image (keep original format)
    image = cv2.imdecode(image_array, cv2.IMREAD_UNCHANGED)

    if image is None:
        raise Exception("Failed to decode image.")

    # Determine the format and convert as needed
    image_rgb = None
    if len(image.shape) == 2: # Grayscale image
        image_rgb = cv2.cvtColor(image, cv2.COLOR_GRAY2RGB)
    elif len(image.shape) == 3:
        channels = image.shape[2]
        if channels == 3: # Color image (assume RGB)
            image_rgb = image # No conversion needed
            #image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB) # Convert BGR to RGB
        elif channels == 4: # Image with alpha channel
            image_rgb = cv2.cvtColor(image, cv2.COLOR_BGRA2RGB)
    else:
        raise Exception("Unexpected image format. Exiting.")

    cv2.imwrite(save_path, image_rgb, [cv2.IMWRITE_JPEG_QUALITY, quality])

def combine_images_vertically(image_paths):
    # Read all images from the paths
    images = [cv2.imread(image) for image in image_paths]
    
    # Ensure all images are read correctly
    if any(img is None for img in images):
        raise ValueError("One or more image paths are invalid or the images could not be read.")

    # Determine the maximum width and total height
    max_width = max(img.shape[1] for img in images)
    total_height = sum(img.shape[0] for img in images)

    # Create a blank canvas with the maximum width and total height
    combined_image = np.ones((total_height, max_width, 3), dtype=np.uint8) * 255 # White background

    # Paste each image onto the canvas
    y_offset = 0
    for img in images:
        height, width, _ = img.shape
        # Center-align the image horizontally
        x_offset = (max_width - width) // 2
        combined_image[y_offset:y_offset+height, x_offset:x_offset+width] = img
        y_offset += height

    return combined_image

def has_significant_white_content(image, white_pixel_threshold=500, intensity_threshold=15):
    # Determine if a image contains meaningful white content based on white pixels and intensity variation.

    # Convert image to grayscale
    gray_section = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # Check the number of white pixels
    white_pixels = np.sum(gray_section > 200) # Count pixels close to white

    # Check intensity variation
    intensity_variation = np.std(gray_section) # Standard deviation of pixel intensities

    # Keep image if it has enough white pixels or sufficient intensity variation
    return white_pixels >= white_pixel_threshold or intensity_variation > intensity_threshold

def has_significant_black_content(image, black_pixel_threshold=500, intensity_threshold=15):
    # Determine if a image contains meaningful black content based on black pixels and intensity variation.

    # Convert image to grayscale
    gray_section = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # Count black pixels (intensity close to 0)
    black_pixels = np.sum(gray_section < 50) # Count pixels close to black

    # Check intensity variation
    intensity_variation = np.std(gray_section) # Standard deviation of pixel intensities

    # Keep image if it has enough black pixels or sufficient intensity variation
    return black_pixels >= black_pixel_threshold or intensity_variation > intensity_threshold

def has_significant_content(section, background):
    if background == 'white':
        return has_significant_black_content(section)
    else:
        return has_significant_white_content(section)

def crop_vertical_sections(image, output_folder, min_height=30, quality=90, background='white', _section_index=0, _recursion_depth=0):
    height, width, _ = image.shape

    # Convert image to grayscale
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # Apply thresholding based on the background color
    if background == 'white':
        _, binary = cv2.threshold(gray, 230, 255, cv2.THRESH_BINARY_INV)
    else: # Background is black
        _, binary = cv2.threshold(gray, 15, 255, cv2.THRESH_BINARY)

    # Sum along rows to detect vertical content
    vertical_sum = np.sum(binary, axis=1)

    # Find "content regions" where vertical_sum > 0
    content_regions = []
    in_content = False
    start_y = 0

    for y, value in enumerate(vertical_sum):
        if value > 0 and not in_content: # Start of a content region
            in_content = True
            start_y = y
        elif value == 0 and in_content: # End of a content region
            in_content = False
            end_y = y
            if (end_y - start_y) > min_height: # Only save if the region is tall enough
                content_regions.append((start_y, end_y))

    os.makedirs(output_folder, exist_ok=True)

    # Save each content region as a separate image
    last_end_y = 0
    for i, (start_y, end_y) in enumerate(content_regions):
        last_end_y = end_y
        cropped = image[start_y:end_y, :] # Crop full width
        if not has_significant_content(cropped, background): # Skip saving images if they don't have any significant content
            continue
        if cropped.shape[0] > 3000 and _recursion_depth < 1:
            _section_index = crop_vertical_sections(cropped, output_folder, min_height, quality, 'black', int(_section_index), _recursion_depth + 1) # Attempt to recrop big images with a black background instead
        else:
            _section_index += 1
            output_path = os.path.join(output_folder, f"{_section_index}.jpg")
            cv2.imwrite(output_path, cropped, [cv2.IMWRITE_JPEG_QUALITY, quality])

    if last_end_y < height: # Save any remaining content as a separate image
        cropped = image[last_end_y:, :] # Crop full width
        if not has_significant_content(cropped, background): # Skip saving images if they don't have any significant content
            return _section_index
        if cropped.shape[0] > 3000 and _recursion_depth < 1:
            _section_index = crop_vertical_sections(cropped, output_folder, min_height, quality, 'black', int(_section_index), _recursion_depth + 1) # Attempt to recrop big images with a black background instead
        else:
            _section_index += 1
            output_path = os.path.join(output_folder, f"{_section_index}.jpg")
            cv2.imwrite(output_path, cropped, [cv2.IMWRITE_JPEG_QUALITY, quality])

    return _section_index

def getNumericIndex(filename:str):
    return int(filename.split('.')[0])

def downloadChapter(link, title, chapterid):
    html = requests.get(link, proxies=proxies, timeout=5).text
    soup = BeautifulSoup(html, 'html.parser')
    imglist = soup.find(id='_imageList').findChildren('img')
    i = 0
    if not os.path.exists(f'data/{make_safe_filename_windows(title)}/{chapterid}'):
        os.makedirs(f'data/{make_safe_filename_windows(title)}/{chapterid}')
    running = 0
    for img in imglist:
        i += 1
        print(f'\rDownloading image {i}/{len(imglist)}', end='')
        def get(url, index):
            nonlocal running
            try:
                img = requests.get(url, headers={'Referer': link}, proxies=proxies, timeout=5).content
                convert_image_to_jpeg(img, f'data/{make_safe_filename_windows(title)}/{chapterid}/{index}.jpg')
                running -= 1
            except Exception as e:
                print(e)
                print('Retrying in 1 second...')
                time.sleep(1)
                get(url, index)
        running += 1
        threading.Thread(target=get, args=(str(img['data-url']), int(i))).start()
        while running >= args.threads:
            time.sleep(0.01)
    while running > 0:
        time.sleep(0.01)
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
        if chapter_title.endswith('BGM'): # This happens if the chapter includes background music
            chapter_title = chapter_title[:-3].strip()
        chapter_link = chapter.find('a')['href']
        chapter_list.append((chapter_title, chapter_link))
    return chapter_list

def downloadComic(link):
    print(f'Link: {link}')
    global chapter_page_count_total
    html = requests.get(link, proxies=proxies, timeout=5).text
    soup = BeautifulSoup(html, 'html.parser')
    info = soup.find('div', class_='info')
    title = info.find(class_='subj').encode_contents().decode('utf-8').replace('<br>', ' ').replace('<br/>', ' ').strip() # Fix for titles with newlines (<br>)
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
            print(f'Auto cropping chapter {chapter_index}: {chapter[0]}...', end='', flush=True)
            images = []
            for img in sorted(os.listdir(f'data/{make_safe_filename_windows(title)}/{chapter_index}'), key=getNumericIndex):
                images.append(f'data/{make_safe_filename_windows(title)}/{chapter_index}/{img}')
            image = combine_images_vertically(images)
            # Remove all images in the chapter folder
            for img in os.listdir(f'data/{make_safe_filename_windows(title)}/{chapter_index}'):
                os.remove(f'data/{make_safe_filename_windows(title)}/{chapter_index}/{img}')
            crop_vertical_sections(image, f'data/{make_safe_filename_windows(title)}/{chapter_index}') # Crop the image and save the sections
            print('done')

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