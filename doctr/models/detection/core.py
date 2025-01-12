# Copyright (C) 2021, Mindee.

# This program is licensed under the Apache License version 2.
# See LICENSE or go to <https://www.apache.org/licenses/LICENSE-2.0.txt> for full license details.

import tensorflow as tf
from tensorflow import keras
import numpy as np
import cv2
from typing import Union, List, Tuple, Any, Optional, Dict
from ..preprocessor import PreProcessor
from doctr.utils.repr import NestedObject

__all__ = ['DetectionPreProcessor', 'DetectionModel', 'DetectionPostProcessor', 'DetectionPredictor']


class DetectionPreProcessor(PreProcessor):
    """Implements a detection preprocessor

        Example::
        >>> from doctr.documents import read_pdf
        >>> from doctr.models import RecoPreprocessor
        >>> processor = RecoPreprocessor(output_size=(600, 600), batch_size=8)
        >>> processed_doc = processor([read_pdf("path/to/your/doc.pdf")])

    Args:
        output_size: expected size of each page in format (H, W)
        batch_size: the size of page batches
        mean: mean value of the training distribution by channel
        std: standard deviation of the training distribution by channel
        interpolation: one of 'bilinear', 'nearest', 'bicubic', 'area', 'lanczos3', 'lanczos5'

    """

    def __init__(
        self,
        output_size: Tuple[int, int],
        batch_size: int = 1,
        mean: Tuple[float, float, float] = (.5, .5, .5),
        std: Tuple[float, float, float] = (1., 1., 1.),
        interpolation: str = 'bilinear'
    ) -> None:

        super().__init__(output_size, batch_size, mean, std, interpolation)

    def resize(
        self,
        x: tf.Tensor,
    ) -> tf.Tensor:
        """Resize images using tensorflow backend.

        Args:
            x: image as a tf.Tensor

        Returns:
            the processed image after being resized
        """

        return tf.image.resize(x, self.output_size, method=self.interpolation)


class DetectionModel(keras.Model, NestedObject):
    """Implements abstract DetectionModel class"""

    def __init__(self, *args: Any, cfg: Optional[Dict[str, Any]] = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.cfg = cfg

    def call(
        self,
        x: tf.Tensor,
        **kwargs: Any,
    ) -> Union[List[tf.Tensor], tf.Tensor]:
        raise NotImplementedError


class DetectionPostProcessor(NestedObject):
    """Abstract class to postprocess the raw output of the model

    Args:
        min_size_box (int): minimal length (pix) to keep a box
        max_candidates (int): maximum boxes to consider in a single page
        box_thresh (float): minimal objectness score to consider a box
    """

    def __init__(
        self,
        min_size_box: int = 5,
        box_thresh: float = 0.5,
        bin_thresh: float = 0.5
    ) -> None:

        self.min_size_box = min_size_box
        self.box_thresh = box_thresh
        self.bin_thresh = bin_thresh

    def extra_repr(self) -> str:
        return f"box_thresh={self.box_thresh}, max_candidates={self.max_candidates}"

    @staticmethod
    def box_score(
        pred: np.ndarray,
        points: np.ndarray
    ) -> float:
        """Compute the confidence score for a polygon : mean of the p values on the polygon

        Args:
            pred (np.ndarray): p map returned by the model

        Returns:
            polygon objectness
        """
        h, w = pred.shape[:2]
        xmin = np.clip(np.floor(points[:, 0].min()).astype(np.int), 0, w - 1)
        xmax = np.clip(np.ceil(points[:, 0].max()).astype(np.int), 0, w - 1)
        ymin = np.clip(np.floor(points[:, 1].min()).astype(np.int), 0, h - 1)
        ymax = np.clip(np.ceil(points[:, 1].max()).astype(np.int), 0, h - 1)

        return pred[ymin:ymax + 1, xmin:xmax + 1].mean()

    def bitmap_to_boxes(
        self,
        pred: np.ndarray,
        bitmap: np.ndarray,
    ) -> List[List[float]]:
        raise NotImplementedError

    def __call__(
        self,
        x: Dict[str, tf.Tensor],
    ) -> List[np.ndarray]:
        """Performs postprocessing for a list of model outputs

        Args:
            x: dictionary of the model output

        returns:
            list of N tensors (for each input sample), with each tensor of shape (*, 5).
        """
        p = x["proba_map"]
        p = tf.squeeze(p, axis=-1)  # remove last dim
        bitmap = tf.cast(p > self.bin_thresh, tf.float32)

        p = tf.unstack(p, axis=0)
        bitmap = tf.unstack(bitmap, axis=0)

        boxes_batch = []

        for p_, bitmap_ in zip(p, bitmap):
            p_ = p_.numpy()
            bitmap_ = bitmap_.numpy()
            # perform opening (erosion + dilatation)
            kernel = np.ones((3, 3), np.uint8)
            bitmap_ = cv2.morphologyEx(bitmap_, cv2.MORPH_OPEN, kernel)
            boxes = self.bitmap_to_boxes(pred=p_, bitmap=bitmap_)
            boxes_batch.append(boxes)

        return boxes_batch


class DetectionPredictor(NestedObject):
    """Implements an object able to localize text elements in a document

    Args:
        pre_processor: transform inputs for easier batched model inference
        model: core detection architecture
        post_processor: post process model outputs
    """

    _children_names: List[str] = ['pre_processor', 'model', 'post_processor']

    def __init__(
        self,
        pre_processor: DetectionPreProcessor,
        model: DetectionModel,
        post_processor: DetectionPostProcessor,
    ) -> None:

        self.pre_processor = pre_processor
        self.model = model
        self.post_processor = post_processor

    def __call__(
        self,
        pages: List[np.ndarray],
        **kwargs: Any,
    ) -> List[np.ndarray]:

        # Dimension check
        if any(page.ndim != 3 for page in pages):
            raise ValueError("incorrect input shape: all pages are expected to be multi-channel 2D images.")

        processed_batches = self.pre_processor(pages)
        out = [self.model(batch, **kwargs) for batch in processed_batches]
        out = [self.post_processor(batch) for batch in out]
        out = [boxes for batch in out for boxes in batch]

        return out
