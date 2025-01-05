import os
import re
from typing import List, Tuple, Optional, Dict
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
import fitz  # PyMuPDF
import shapely.geometry as sg
from shapely.geometry.base import BaseGeometry
from shapely.validation import explain_validity
import concurrent.futures

# This Default Prompt can be changed to other languages

DEFAULT_PROMPT = """Use markdown syntax to convert text recognized in images to markdown format output. You must:
1. Output in the same language as recognized in the image. For example, if English text is detected, the output must be in English.
2. Do not explain or output irrelevant text, output the image content directly. For example, do not output examples like "Here is the markdown text I generated from the image content:", instead output the markdown directly.
3. Content should not be wrapped in ```markdown ```, paragraph formulas should use $$ $$ format, inline formulas should use $ $ format, ignore long lines, ignore page numbers and other header/footer content.
Again, do not explain or output irrelevant text, output the image content directly. Be careful to use the $$ $$ format whenever you 
output latex.
"""
DEFAULT_RECT_PROMPT = """In the image, some areas are marked with red boxes and names (%s).
If the area is a table or image, use ![]() format to insert the name into the output content,
otherwise output the text content directly.
"""
DEFAULT_ROLE_PROMPT = """You are a PDF document parser, output the image content 
using markdown and latex syntax. Make a faithful word-forreproduction - do not summarise, do not rewrite, include everything.
"""


def _is_near(rect1: BaseGeometry, rect2: BaseGeometry, distance: float = 20) -> bool:
    """
    Check if two rectangles are near each other if the distance between them is less than the target.
    """
    return rect1.buffer(0.1).distance(rect2.buffer(0.1)) < distance


def _is_horizontal_near(rect1: BaseGeometry, rect2: BaseGeometry, distance: float = 100) -> bool:
    """
    Check if two rectangles are near horizontally if one of them is a horizontal line.
    """
    result = False
    if abs(rect1.bounds[3] - rect1.bounds[1]) < 0.1 or abs(rect2.bounds[3] - rect2.bounds[1]) < 0.1:
        if abs(rect1.bounds[0] - rect2.bounds[0]) < 0.1 and abs(rect1.bounds[2] - rect2.bounds[2]) < 0.1:
            result = abs(rect1.bounds[3] - rect2.bounds[3]) < distance
    return result


def _union_rects(rect1: BaseGeometry, rect2: BaseGeometry) -> BaseGeometry:
    """
    Union two rectangles.
    """
    return sg.box(*(rect1.union(rect2).bounds))


def _merge_rects(rect_list: List[BaseGeometry], distance: float = 20, horizontal_distance: Optional[float] = None) -> \
        List[BaseGeometry]:
    """
    Merge rectangles in the list if the distance between them is less than the target.
    """
    merged = True
    while merged:
        merged = False
        new_rect_list = []
        while rect_list:
            rect = rect_list.pop(0)
            for other_rect in rect_list:
                if _is_near(rect, other_rect, distance) or (
                        horizontal_distance and _is_horizontal_near(rect, other_rect, horizontal_distance)):
                    rect = _union_rects(rect, other_rect)
                    rect_list.remove(other_rect)
                    merged = True
            new_rect_list.append(rect)
        rect_list = new_rect_list
    return rect_list


def _adsorb_rects_to_rects(source_rects: List[BaseGeometry], target_rects: List[BaseGeometry], distance: float = 10) -> \
        Tuple[List[BaseGeometry], List[BaseGeometry]]:
    """
    Adsorb a set of rectangles to another set of rectangles.
    """
    new_source_rects = []
    for text_area_rect in source_rects:
        adsorbed = False
        for index, rect in enumerate(target_rects):
            if _is_near(text_area_rect, rect, distance):
                rect = _union_rects(text_area_rect, rect)
                target_rects[index] = rect
                adsorbed = True
                break
        if not adsorbed:
            new_source_rects.append(text_area_rect)
    return new_source_rects, target_rects


def _parse_rects(page: fitz.Page) -> List[Tuple[float, float, float, float]]:
    """
    Parse drawings in the page and merge adjacent rectangles.
    """

    # Extract drawn content
    drawings = page.get_drawings()

    # Ignore horizontal lines shorter than 30
    is_short_line = lambda x: abs(x['rect'][3] - x['rect'][1]) < 1 and abs(x['rect'][2] - x['rect'][0]) < 30
    drawings = [drawing for drawing in drawings if not is_short_line(drawing)]

    # Convert to shapely rectangles
    rect_list = [sg.box(*drawing['rect']) for drawing in drawings]

    # Extract image areas
    images = page.get_image_info()
    image_rects = [sg.box(*image['bbox']) for image in images]

    # Merge drawings and images
    rect_list += image_rects

    merged_rects = _merge_rects(rect_list, distance=10, horizontal_distance=100)
    merged_rects = [rect for rect in merged_rects if explain_validity(rect) == 'Valid Geometry']

    # Process large and small text areas separately: merge large text with small, merge nearby small text
    is_large_content = lambda x: (len(x[4]) / max(1, len(x[4].split('\n')))) > 5
    small_text_area_rects = [sg.box(*x[:4]) for x in page.get_text('blocks') if not is_large_content(x)]
    large_text_area_rects = [sg.box(*x[:4]) for x in page.get_text('blocks') if is_large_content(x)]
    _, merged_rects = _adsorb_rects_to_rects(large_text_area_rects, merged_rects, distance=0.1) # Complete intersection
    _, merged_rects = _adsorb_rects_to_rects(small_text_area_rects, merged_rects, distance=5) # Nearby

    # Merge with self again
    merged_rects = _merge_rects(merged_rects, distance=10)

    # Filter out small rectangles
    merged_rects = [rect for rect in merged_rects if rect.bounds[2] - rect.bounds[0] > 20 and rect.bounds[3] - rect.bounds[1] > 20]

    return [rect.bounds for rect in merged_rects]


def _parse_pdf_to_images(pdf_path: str, output_dir: str = './') -> List[Tuple[str, List[str]]]:
    """
    Parse PDF to images and save to output_dir.
    """
    # Open PDF file
    pdf_document = fitz.open(pdf_path)
    image_infos = []

    for page_index, page in enumerate(pdf_document):
        logging.info(f'parse page: {page_index}')
        rect_images = []
        rects = _parse_rects(page)
        for index, rect in enumerate(rects):
            fitz_rect = fitz.Rect(rect)
            # Save page as image
            pix = page.get_pixmap(clip=fitz_rect, matrix=fitz.Matrix(4, 4))
            name = f'{page_index}_{index}.png'
            pix.save(os.path.join(output_dir, name))
            rect_images.append(name)
            # Draw red rectangle on page
            big_fitz_rect = fitz.Rect(fitz_rect.x0 - 1, fitz_rect.y0 - 1, fitz_rect.x1 + 1, fitz_rect.y1 + 1)
            # Hollow rectangle
            page.draw_rect(big_fitz_rect, color=(1, 0, 0), width=1)
            # Draw rectangle area (solid)
            # page.draw_rect(big_fitz_rect, color=(1, 0, 0), fill=(1, 0, 0))
            # Write rectangle index name in the top left corner, with some offset
            text_x = fitz_rect.x0 + 2
            text_y = fitz_rect.y0 + 10
            text_rect = fitz.Rect(text_x, text_y - 9, text_x + 80, text_y + 2)
            # Draw white background rectangle
            page.draw_rect(text_rect, color=(1, 1, 1), fill=(1, 1, 1))
            # Insert text with white background
            page.insert_text((text_x, text_y), name, fontsize=10, color=(1, 0, 0))
        page_image_with_rects = page.get_pixmap(matrix=fitz.Matrix(3, 3))
        page_image = os.path.join(output_dir, f'{page_index}.png')
        page_image_with_rects.save(page_image)
        image_infos.append((page_image, rect_images))

    pdf_document.close()
    return image_infos


def _gpt_parse_images(
        image_infos: List[Tuple[str, List[str]]],
        prompt_dict: Optional[Dict] = None,
        output_dir: str = './',
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: str = 'gpt-4o',
        verbose: bool = False,
        gpt_worker: int = 1,
        **args
) -> str:
    """
    Parse images to markdown content.
    """