# Copyright (C) 2021, Mindee.

# This program is licensed under the Apache License version 2.
# See LICENSE or go to <https://www.apache.org/licenses/LICENSE-2.0.txt> for full license details.

import numpy as np
import cv2
from pathlib import Path
import fitz
from weasyprint import HTML
from typing import List, Tuple, Optional, Any, Union, Sequence

__all__ = ['read_pdf', 'read_img', 'read_html', 'DocumentFile']


AbstractPath = Union[str, Path]
AbstractFile = Union[AbstractPath, bytes]
Bbox = Tuple[float, float, float, float]


def read_img(
    file: AbstractFile,
    output_size: Optional[Tuple[int, int]] = None,
    rgb_output: bool = True,
) -> np.ndarray:
    """Read an image file into numpy format

    Example::
        >>> from doctr.documents import read_img
        >>> page = read_img("path/to/your/doc.jpg")

    Args:
        file: the path to the image file
        output_size: the expected output size of each page in format H x W
        rgb_output: whether the output ndarray channel order should be RGB instead of BGR.
    Returns:
        the page decoded as numpy ndarray of shape H x W x 3
    """

    if isinstance(file, (str, Path)):
        if not Path(file).is_file():
            raise FileNotFoundError(f"unable to access {file}")
        img = cv2.imread(str(file), cv2.IMREAD_COLOR)
    elif isinstance(file, bytes):
        file = np.frombuffer(file, np.uint8)
        img = cv2.imdecode(file, cv2.IMREAD_COLOR)
    else:
        raise TypeError("unsupported object type for argument 'file'")

    # Validity check
    if img is None:
        raise ValueError("unable to read file.")
    # Resizing
    if isinstance(output_size, tuple):
        img = cv2.resize(img, output_size[::-1], interpolation=cv2.INTER_LINEAR)
    # Switch the channel order
    if rgb_output:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    return img


def read_pdf(file: AbstractFile, **kwargs: Any) -> fitz.Document:
    """Read a PDF file and convert it into an image in numpy format

    Example::
        >>> from doctr.documents import read_pdf
        >>> doc = read_pdf("path/to/your/doc.pdf")

    Args:
        file: the path to the PDF file
    Returns:
        the list of pages decoded as numpy ndarray of shape H x W x 3
    """

    fitz_args = {}

    if isinstance(file, (str, Path)):
        fitz_args['filename'] = file
    elif isinstance(file, bytes):
        fitz_args['stream'] = file
    else:
        raise TypeError("unsupported object type for argument 'file'")

    # Read pages with fitz and convert them to numpy ndarrays
    return fitz.open(**fitz_args, filetype="pdf", **kwargs)


def convert_page_to_numpy(
    page: fitz.fitz.Page,
    output_size: Optional[Tuple[int, int]] = None,
    rgb_output: bool = True,
) -> np.ndarray:
    """Convert a fitz page to a numpy-formatted image

    Args:
        page: the page of a file read with PyMuPDF
        output_size: the expected output size of each page in format H x W
        rgb_output: whether the output ndarray channel order should be RGB instead of BGR.

    Returns:
        the rendered image in numpy format
    """

    transform_matrix = None

    # If no output size is specified, keep the origin one
    if output_size is not None:
        scales = (output_size[1] / page.MediaBox[2], output_size[0] / page.MediaBox[3])
        transform_matrix = fitz.Matrix(*scales)

    # Generate the pixel map using the transformation matrix
    stream = page.getPixmap(matrix=transform_matrix).getImageData()
    # Decode it into a numpy
    img = cv2.imdecode(np.frombuffer(stream, dtype=np.uint8), cv2.IMREAD_UNCHANGED)

    # Switch the channel order
    if rgb_output:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

    return img


def read_html(url: str, **kwargs: Any) -> bytes:
    """Read a PDF file and convert it into an image in numpy format

    Example::
        >>> from doctr.documents import read_html
        >>> doc = read_html("https://www.yoursite.com")

    Args:
        url: URL of the target web page
    Returns:
        decoded PDF file as a bytes stream
    """

    return HTML(url, **kwargs).write_pdf()


class PDF:
    """PDF document template

    Args:
        doc: input PDF document
    """
    def __init__(self, doc: fitz.Document) -> None:
        self.doc = doc

    def as_images(self, **kwargs) -> List[np.ndarray]:
        """Convert all document pages to images

        Example::
            >>> from doctr.documents import DocumentFile
            >>> pages = DocumentFile.from_pdf("path/to/your/doc.pdf").as_images()

        Args:
            kwargs: keyword arguments of `convert_page_to_numpy`
        Returns:
            the list of pages decoded as numpy ndarray of shape H x W x 3
        """
        return [convert_page_to_numpy(page, **kwargs) for page in self.doc]

    def get_page_words(self, idx, **kwargs) -> List[Tuple[Bbox, str]]:
        """Get the annotations for all words of a given page"""

        # xmin, ymin, xmax, ymax, value, block_idx, line_idx, word_idx
        return [(info[:4], info[4]) for info in self.doc[idx].getTextWords(**kwargs)]

    def get_words(self, **kwargs) -> List[List[Tuple[Bbox, str]]]:
        """Get the annotations for all words in the document

        Example::
            >>> from doctr.documents import DocumentFile
            >>> words = DocumentFile.from_pdf("path/to/your/doc.pdf").get_words()

        Args:
            kwargs: keyword arguments of `fitz.Page.getTextWords`
        Returns:
            the list of pages annotations, represented as a list of tuple (bounding box, value)
        """
        return [self.get_page_words(idx, **kwargs) for idx in range(len(self.doc))]

    def get_page_artefacts(self, idx) -> List[Tuple[float, float, float, float]]:
        return [tuple(self.doc[idx].getImageBbox(artefact)) for artefact in self.doc[idx].get_images(full=True)]

    def get_artefacts(self) -> List[List[Tuple[float, float, float, float]]]:
        """Get the artefacts for the entire document

        Example::
            >>> from doctr.documents import DocumentFile
            >>> artefacts = DocumentFile.from_pdf("path/to/your/doc.pdf").get_artefacts()

        Returns:
            the list of pages artefacts, represented as a list of bounding boxes
        """

        return [self.get_page_artefacts(idx) for idx in range(len(self.doc))]


class DocumentFile:
    """Read a document from multiple extensions"""

    @classmethod
    def from_pdf(cls, file: AbstractFile, **kwargs) -> PDF:
        """Read a PDF file

        Example::
            >>> from doctr.documents import DocumentFile
            >>> doc = DocumentFile.from_pdf("path/to/your/doc.pdf")

        Args:
            file: the path to the PDF file or a binary stream
        Returns:
            a PDF document
        """

        doc = read_pdf(file, **kwargs)

        return PDF(doc)

    @classmethod
    def from_url(cls, url: str, **kwargs) -> PDF:
        """Interpret a web page as a PDF document

        Example::
            >>> from doctr.documents import DocumentFile
            >>> doc = DocumentFile.from_url("https://www.yoursite.com")

        Args:
            url: the URL of the target web page
        Returns:
            a PDF document
        """
        pdf_stream = read_html(url)
        return cls.from_pdf(pdf_stream, **kwargs)

    @classmethod
    def from_images(cls, files: Union[Sequence[AbstractFile], AbstractFile], **kwargs) -> List[np.ndarray]:
        """Read an image file (or a collection of image files) and convert it into an image in numpy format

        Example::
            >>> from doctr.documents import DocumentFile
            >>> pages = DocumentFile.from_images(["path/to/your/page1.png", "path/to/your/page2.png"])

        Args:
            files: the path to the image file or a binary stream, or a collection of those
        Returns:
            the list of pages decoded as numpy ndarray of shape H x W x 3
        """
        if isinstance(files, (str, Path, bytes)):
            files = [files]

        return [read_img(file, **kwargs) for file in files]
